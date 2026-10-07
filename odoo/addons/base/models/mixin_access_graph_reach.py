from __future__ import annotations

import hashlib
import typing
from itertools import starmap

from odoo import models
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

from .mixin_access_graph import path_ids

_debug = DebugLog(__name__)

if typing.TYPE_CHECKING:
    from .mixin_access_graph import AccessGraph

# who a row names: a partner's grant, a group's grant, or a user owning a node
PARTNER, GROUP, USER = 0, 1, 2
# a row of the node's own graph, every adopter's; adopters number theirs above
OWN = 0

REACH_COLUMNS = (
    "resource_id",
    "key",
    "kind",
    "pid",
    "via",
    "rank",
    "grant_company_id",
    "node_company_id",
    "resource_company_id",
    "resource_user_id",
    "date_to",
    "grant_id",
)


def principal_key(kind: int, principal_id: int) -> int:
    return principal_id * 4 + kind


class MixinAccessGraph(models.AbstractModel):
    # The reach table: every way a principal reaches a node, one row each,
    # derived from the tree and the grants and kept exact by the database, as
    # an index is: statement triggers on the node and grant tables re-derive
    # what a statement touched and what reads it (the subtree, the shortcuts
    # to it) before the statement returns, whoever wrote it, the ORM or raw
    # SQL. Who the user is -- their groups, the companies in use, the clock
    # -- stays a query-time input, so a membership change, a company switch
    # or an expiry writes nothing
    _inherit = "mixin.access.graph"

    def init(self) -> None:
        super().init()
        if self._access_graph is not None and not self._abstract:
            self.pool.post_init(self._access_reach_install)

    # -- declaration, overridden by adopters ---------------------------------

    def _access_reach_table(self) -> str:
        return f"{self._table}_access_reach"

    def _access_reach_tracked_columns(self) -> list[str]:
        # the node columns a row is derived from. A change to one re-derives
        # the node and what reads it (_access_reach_readers). A move rewrites
        # the parent_path of every node it carries in one statement, which
        # re-derives the subtree once: the scope a node inherits is read from
        # parent_path and the boundaries on it, not from access_scope_path,
        # which the ORM recomputes in many later statements
        graph = self._access_graph
        columns = [
            graph.parent,
            "parent_path",
            *self._access_reach_deep_columns(),
        ]
        if anchor := self._access_reach_company_column():
            columns.append(anchor)
        return columns

    def _access_reach_deep_columns(self) -> list[str]:
        # the node columns whose change reaches the whole subtree: what a node
        # passes down to every node below it
        graph = self._access_graph
        return [
            *((graph.owner,) if graph.owner else ()),
            *((graph.container[0],) if graph.container else ()),
            *((graph.boundary,) if graph.boundary else ()),
        ]

    def _access_reach_own_via(self) -> SQL:
        # the via of a node's own graph rows, over the refreshed node "scope"
        return SQL("%s", OWN)

    def _access_reach_graph_needs(self) -> list[SQL]:
        # the nodes, beyond those refreshed, whose graph rows the derived rows
        # read: selects of ids over the refreshed nodes "scope"
        return []

    def _access_reach_ctes(self) -> list[tuple[str, SQL]]:
        # common table expressions the derived rows read, after "graph"
        return []

    def _access_reach_derived(self) -> list[SQL]:
        # the adopter's own ways of reaching: selects of REACH_COLUMNS over
        # "scope" (the refreshed nodes, whole rows) and "graph" (the own-graph
        # tuples of every node needed)
        return []

    def _access_reach_readers(self, affected: SQL) -> list[SQL]:
        # the nodes whose rows read a node of `affected` (an int4[]) other
        # than through the scope its descendants inherit: selects of ids
        return []

    def _access_reach_graph_vias(self) -> tuple[int, ...]:
        # the vias the graph's own reach (_access_graph_domain) counts
        return (OWN,)

    # -- the query ------------------------------------------------------------

    def _access_reach_subquery(
        self,
        role: str,
        *,
        vias: typing.Iterable[int] | None = None,
        groups: typing.Iterable[int] | None = None,
        exclude_groups: typing.Iterable[int] = (),
        partner: bool = True,
        owner: bool = True,
        owner_vias: typing.Iterable[int] = (),
        alternatives: typing.Iterable[tuple[list[int], SQL]] = (),
    ) -> SQL:
        # the ids of the nodes the current user reaches at the role or above
        # through the rows of `vias`: one principal column, so that what the
        # planner estimates is what it reads. A group counts in the companies
        # in use it is held in (those its membership is limited to, else all),
        # on nodes of those companies or of none, and its grant limited to a
        # company counts while that company is one of them; a partner's grant
        # and an owner count on a node of a company in use, of none, or of one
        # the user is not in. `owner_vias` are rows the node's own user
        # (resource_user_id) holds at every role; `alternatives` are further
        # (principal keys, condition) pairs the adopter reaches through
        graph: AccessGraph = self._access_graph
        user = self.env.user
        rank = graph.roles.index(role) + 1
        excluded = set(exclude_groups)
        if groups is None:
            scopes = {
                gid: companies
                for gid, companies in user._get_group_scopes().items()
                if gid not in excluded
            }
        else:
            scopes = dict.fromkeys(set(groups) - excluded)
        in_use = sorted(self.env.companies.ids)
        member_of = user.with_context(active_test=False).company_ids.ids
        bands: dict[tuple[int, ...], list[int]] = {}
        for gid, companies in sorted(scopes.items()):
            counted = set(in_use) if companies is None else set(in_use) & set(companies)
            if counted:
                bands.setdefault(tuple(sorted(counted)), []).append(gid)
        anchored = self._access_reach_company_column() is not None
        keys = [principal_key(GROUP, gid) for gids in bands.values() for gid in gids]
        if partner:
            keys.append(principal_key(PARTNER, user.partner_id.id))
        if owner and graph.owner:
            keys.append(principal_key(USER, user.id))

        def personal(column: str) -> SQL:
            return SQL(
                "(%(c)s IS NULL OR %(c)s = ANY(%(in_use)s) OR NOT %(c)s = ANY(%(member_of)s))",
                c=SQL.identifier(column),
                in_use=in_use,
                member_of=member_of,
            )

        def band(companies: tuple[int, ...], gids: list[int]) -> SQL:
            terms = [] if len(bands) == 1 else [SQL("pid = ANY(%s)", gids)]
            terms.append(
                SQL(
                    "(grant_company_id IS NULL OR grant_company_id = ANY(%s))",
                    list(companies),
                )
            )
            if anchored:
                terms.append(
                    SQL(
                        "(node_company_id IS NULL OR node_company_id = ANY(%s))",
                        list(companies),
                    )
                )
            return SQL("(%s)", SQL(" AND ").join(terms))

        held = SQL("rank >= %s", rank)
        if owner_vias := list(owner_vias):
            held = SQL(
                "(%s OR (via = ANY(%s) AND resource_user_id = %s))",
                held,
                owner_vias,
                user.id,
            )
        principal = [
            SQL(
                "(kind <> %s AND %s)",
                GROUP,
                personal("node_company_id") if anchored else SQL("TRUE"),
            )
        ]
        if bands:
            principal.append(
                SQL(
                    "(kind = %s AND (%s))",
                    GROUP,
                    SQL(" OR ").join(starmap(band, bands.items())),
                )
            )
        reached = [
            SQL(
                """(via = ANY(%(vias)s) AND %(held)s
                    AND (date_to IS NULL OR date_to > now() AT TIME ZONE 'UTC')
                    AND (resource_company_id IS NULL OR %(resource_company)s)
                    AND (%(principal)s))""",
                vias=list(
                    vias if vias is not None else self._access_reach_graph_vias()
                ),
                held=held,
                resource_company=personal("resource_company_id"),
                principal=SQL(" OR ").join(principal),
            )
        ]
        for alternative_keys, alternative in alternatives:
            keys.extend(alternative_keys)
            reached.append(alternative)
        _debug.pipeline(
            "access_reach.subquery",
            model=self._name,
            role=role,
            bands=len(bands),
            principals=len(keys),
            alternatives=len(reached) - 1,
        )
        return SQL(
            "SELECT resource_id FROM %s WHERE key = ANY(%s) AND (%s)",
            SQL.identifier(self._access_reach_table()),
            sorted(set(keys)),
            SQL(" OR ").join(reached),
        )

    # -- generation -----------------------------------------------------------

    def _access_reach_company_column(self) -> str | None:
        # the node's own column holding its company: a row carries it, so an
        # anchor reached through a relation would go stale with no trigger
        anchor = self._access_company_anchor()
        if anchor and "." in anchor:
            raise ValueError(
                f"{self._name}: the access graph needs its company anchor on the "
                f"node itself, not through {anchor!r}"
            )
        return anchor

    def _access_reach_scope_ctes(self, node_company: SQL) -> list[tuple[str, SQL]]:
        # "node_scope": each needed node with the nodes whose grants reach it,
        # its ancestors up to the nearest boundary and itself, read off its
        # parent_path (as access_scope_path states them). Set-wise: every path
        # unnested once, each node's cut found by one join
        graph: AccessGraph = self._access_graph
        table = SQL.identifier(self._table)
        steps = SQL(
            """SELECT node_row.id AS node_id, %(company)s AS company_id,
                      step.id AS step_id, step.depth
                 FROM %(table)s AS node_row
                 JOIN needed ON needed.id = node_row.id
                CROSS JOIN LATERAL unnest(%(path)s) WITH ORDINALITY AS step(id, depth)""",
            company=node_company,
            table=table,
            path=path_ids(SQL.identifier("node_row", "parent_path")),
        )
        if not graph.boundary:
            return [
                ("node_step", steps),
                (
                    "node_scope",
                    SQL("SELECT node_id, company_id, step_id FROM node_step"),
                ),
            ]
        return [
            ("node_step", steps),
            (
                "node_cut",
                SQL(
                    """SELECT node_step.node_id, max(node_step.depth) AS depth
                         FROM node_step JOIN %s AS above ON above.id = node_step.step_id
                        WHERE node_step.depth = 1 OR above.%s
                     GROUP BY node_step.node_id""",
                    table,
                    SQL.identifier(graph.boundary),
                ),
            ),
            (
                "node_scope",
                SQL(
                    """SELECT node_step.node_id, node_step.company_id, node_step.step_id
                         FROM node_step JOIN node_cut ON node_cut.node_id = node_step.node_id
                        WHERE node_step.depth >= node_cut.depth"""
                ),
            ),
        ]

    def _access_reach_rows(self, node_filter: SQL, grants: SQL | None = None) -> SQL:
        # INSERT the rows of the nodes `node_filter` (on alias "node_row")
        # selects; with `grants` (an int4[]), only the rows those grants are
        # the source of
        graph: AccessGraph = self._access_graph
        grant_model = self.env[self._fields[graph.grants].comodel_name]
        names = type(grant_model)._access_grant_names
        table = SQL.identifier(self._table)
        company_column = self._access_reach_company_column()
        node_company = (
            SQL.identifier("node_row", company_column)
            if company_column
            else SQL("NULL::int4")
        )
        if graph.container:
            cfield, cvalue = graph.container
            is_container = SQL("%s = %s", SQL.identifier("held_by", cfield), cvalue)
        else:
            is_container = SQL("TRUE")
        top = len(graph.roles)
        scope_join = SQL(
            """JOIN %(table)s AS held_by
                 ON held_by.id = node.step_id
                AND (held_by.id = node.node_id OR %(is_container)s)""",
            table=table,
            is_container=is_container,
        )
        graph_rows = [
            SQL(
                """SELECT node.node_id AS resource_id,
                          (CASE WHEN grant_row.partner_id IS NULL THEN %(group)s ELSE %(partner)s END)::int2 AS kind,
                          coalesce(grant_row.partner_id, grant_row.group_id) AS pid,
                          array_position(%(roles)s::varchar[], grant_row.%(role)s::varchar)::int2 AS rank,
                          grant_row.company_id AS grant_company_id,
                          node.company_id AS node_company_id,
                          grant_row.date_to,
                          grant_row.id AS grant_id
                     FROM node_scope AS node %(scope_join)s
                     JOIN %(grant_table)s AS grant_row
                       ON grant_row.%(resource)s = held_by.id
                      AND %(grants)s""",
                group=GROUP,
                partner=PARTNER,
                roles=list(graph.roles),
                role=SQL.identifier(names.role),
                scope_join=scope_join,
                grant_table=SQL.identifier(grant_model._table),
                resource=SQL.identifier(names.resource),
                grants=SQL("TRUE")
                if grants is None
                else SQL("grant_row.id = ANY(%s)", grants),
            )
        ]
        if graph.owner and grants is None:
            graph_rows.append(
                SQL(
                    """SELECT node.node_id, %(user)s::int2, held_by.%(owner)s, %(top)s::int2,
                              NULL::int4, node.company_id, NULL::timestamp, NULL::int4
                         FROM node_scope AS node %(scope_join)s
                        WHERE held_by.%(owner)s IS NOT NULL""",
                    user=USER,
                    owner=SQL.identifier(graph.owner),
                    top=top,
                    scope_join=scope_join,
                )
            )
        needs = SQL(" UNION ").join(
            [SQL("SELECT id FROM scope"), *self._access_reach_graph_needs()]
        )
        ctes = [
            (
                "scope",
                SQL(
                    "SELECT node_row.* FROM %s AS node_row WHERE %s", table, node_filter
                ),
            ),
            ("needed", needs),
            *self._access_reach_scope_ctes(node_company),
            ("graph", SQL(" UNION ").join(graph_rows)),
            *self._access_reach_ctes(),
        ]
        own = SQL(
            """SELECT graph.resource_id, graph.pid::int8 * 4 + graph.kind, graph.kind,
                      graph.pid, (%s)::int2, graph.rank, graph.grant_company_id,
                      graph.node_company_id, NULL::int4, NULL::int4, graph.date_to,
                      graph.grant_id
                 FROM graph JOIN scope ON scope.id = graph.resource_id""",
            self._access_reach_own_via(),
        )
        columns = SQL(", ").join(SQL.identifier(column) for column in REACH_COLUMNS)
        rows = SQL(" UNION ALL ").join([own, *self._access_reach_derived()])
        if grants is not None:
            # the ways of reaching that come from no grant are no grant's
            rows = SQL(
                "SELECT * FROM (%s) AS derived (%s) WHERE derived.grant_id IS NOT NULL",
                rows,
                columns,
            )
        return SQL(
            "WITH %s INSERT INTO %s (%s) %s",
            SQL(", ").join(
                SQL("%s AS (%s)", SQL.identifier(name), body) for name, body in ctes
            ),
            SQL.identifier(self._access_reach_table()),
            columns,
            rows,
        )

    def _access_reach_closure(self) -> SQL:
        # the body of a function of (ids, deep) returning the nodes whose rows
        # a change to `ids` may change: the nodes and, until none is new, what
        # reads them (_access_reach_readers); deep, also every node below each
        # of those, which inherits their scope. Walked a level at a time down
        # the parent's index
        graph: AccessGraph = self._access_graph
        readers = self._access_reach_readers(SQL("level"))
        read = (
            SQL(
                "level := ARRAY(%s EXCEPT SELECT unnest(found));",
                SQL(" UNION ").join(readers),
            )
            if readers
            else SQL("level := '{}';")
        )
        return SQL(
            """DECLARE
                   found int4[] := ids;
                   level int4[] := ids;
                   below int4[];
               BEGIN
                   LOOP
                       IF deep THEN
                           below := level;
                           LOOP
                               below := ARRAY(SELECT id FROM %(table)s
                                               WHERE %(parent)s = ANY(below));
                               EXIT WHEN cardinality(below) = 0;
                               found := found || below;
                               level := level || below;
                           END LOOP;
                       END IF;
                       %(read)s
                       EXIT WHEN cardinality(level) = 0;
                       found := found || level;
                   END LOOP;
                   RETURN ARRAY(SELECT DISTINCT unnest(found));
               END""",
            table=SQL.identifier(self._table),
            parent=SQL.identifier(graph.parent),
            read=read,
        )

    def _access_reach_ddl(self) -> SQL:
        graph: AccessGraph = self._access_graph
        grant_model = self.env[self._fields[graph.grants].comodel_name]
        names = type(grant_model)._access_grant_names
        reach = self._access_reach_table()
        table = SQL.identifier(self._table)
        grant_table = SQL.identifier(grant_model._table)
        resource = SQL.identifier(names.resource)
        tracked = sorted(set(self._access_reach_tracked_columns()))

        def name(suffix: str) -> SQL:
            return SQL.identifier(f"{reach}_{suffix}")

        changed = SQL(" OR ").join(
            SQL(
                "new_row.%s IS DISTINCT FROM old_row.%s",
                SQL.identifier(column),
                SQL.identifier(column),
            )
            for column in tracked
        )
        deep_changed = SQL(" OR ").join(
            [
                SQL(
                    "new_row.%s IS DISTINCT FROM old_row.%s",
                    SQL.identifier(column),
                    SQL.identifier(column),
                )
                for column in sorted(set(self._access_reach_deep_columns()))
            ]
            or [SQL("FALSE")]
        )
        return SQL(
            """
            CREATE TABLE IF NOT EXISTS %(reach)s (
                resource_id int4 NOT NULL,
                key int8 NOT NULL,
                kind int2 NOT NULL,
                pid int4 NOT NULL,
                via int2 NOT NULL,
                rank int2 NOT NULL,
                grant_company_id int4,
                node_company_id int4,
                resource_company_id int4,
                resource_user_id int4,
                date_to timestamp,
                grant_id int4
            );
            CREATE INDEX IF NOT EXISTS %(key_index)s ON %(reach)s (key) INCLUDE (
                resource_id, kind, pid, via, rank, grant_company_id, node_company_id,
                resource_company_id, resource_user_id, date_to);
            CREATE INDEX IF NOT EXISTS %(resource_index)s ON %(reach)s (resource_id);
            CREATE INDEX IF NOT EXISTS %(grant_index)s ON %(reach)s (grant_id)
                WHERE grant_id IS NOT NULL;

            CREATE OR REPLACE FUNCTION %(closure_fn)s(ids int4[], deep boolean) RETURNS int4[]
            LANGUAGE plpgsql STABLE AS $body$ %(closure)s $body$;

            -- re-derive the rows of the nodes a change touched, and of what
            -- reads them. The nodes are locked first, in order: a concurrent
            -- refresh of any of them waits, and under repeatable read fails
            -- to serialize and is retried, so no transaction commits rows
            -- derived from a state that misses another's change
            -- reach: 'node' the nodes alone, 'shallow' or 'deep' their closure
            CREATE OR REPLACE FUNCTION %(refresh_fn)s(touched int4[], reach text)
            RETURNS void LANGUAGE plpgsql AS $body$
            DECLARE
                ids int4[];
            BEGIN
                IF touched IS NULL OR cardinality(touched) = 0 THEN
                    RETURN;
                END IF;
                ids := CASE reach WHEN 'node' THEN touched
                       ELSE %(closure_fn)s(touched, reach = 'deep') END;
                PERFORM 1 FROM %(table)s WHERE id = ANY(ids) ORDER BY id FOR NO KEY UPDATE;
                DELETE FROM %(reach)s WHERE resource_id = ANY(ids);
                %(refresh_rows)s;
            END
            $body$;

            CREATE OR REPLACE FUNCTION %(node_inserted_fn)s() RETURNS trigger
            LANGUAGE plpgsql AS $body$
            BEGIN
                -- nothing reads a node the statement created
                PERFORM %(refresh_fn)s(ARRAY(SELECT id FROM new_rows), 'node');
                RETURN NULL;
            END
            $body$;

            -- the transition tables carry no statistics: joined by a nested
            -- loop, a batch of a thousand rows compares a million pairs
            CREATE OR REPLACE FUNCTION %(node_updated_fn)s() RETURNS trigger
            LANGUAGE plpgsql SET enable_nestloop = off AS $body$
            DECLARE
                deep_ids int4[];
                shallow_ids int4[];
            BEGIN
                SELECT array_agg(new_row.id) FILTER (WHERE %(deep_changed)s),
                       array_agg(new_row.id) FILTER (WHERE NOT (%(deep_changed)s))
                  INTO deep_ids, shallow_ids
                  FROM new_rows AS new_row
                  JOIN old_rows AS old_row ON old_row.id = new_row.id
                 WHERE %(changed)s;
                PERFORM %(refresh_fn)s(deep_ids, 'deep');
                PERFORM %(refresh_fn)s(shallow_ids, 'shallow');
                RETURN NULL;
            END
            $body$;

            -- the deleted nodes' rows go with them; what read them is re-derived
            CREATE OR REPLACE FUNCTION %(node_deleted_fn)s() RETURNS trigger
            LANGUAGE plpgsql AS $body$
            BEGIN
                PERFORM %(refresh_fn)s(ARRAY(SELECT id FROM old_rows), 'shallow');
                RETURN NULL;
            END
            $body$;

            -- a grant is the source of its rows, each carrying its id: what
            -- one grant reaches is added and removed alone, the subtree's
            -- other rows untouched
            CREATE OR REPLACE FUNCTION %(add_grants_fn)s(touched int4[], grants int4[])
            RETURNS void LANGUAGE plpgsql AS $body$
            DECLARE
                ids int4[];
            BEGIN
                IF grants IS NULL OR cardinality(grants) = 0 THEN
                    RETURN;
                END IF;
                ids := %(closure_fn)s(touched, true);
                PERFORM 1 FROM %(table)s WHERE id = ANY(ids) ORDER BY id FOR NO KEY UPDATE;
                %(grant_rows)s;
            END
            $body$;

            CREATE OR REPLACE FUNCTION %(grant_changed_fn)s() RETURNS trigger
            LANGUAGE plpgsql AS $body$
            BEGIN
                IF TG_OP IN ('UPDATE', 'DELETE') THEN
                    PERFORM 1 FROM %(table)s
                     WHERE id IN (SELECT %(resource)s FROM old_rows)
                     ORDER BY id FOR NO KEY UPDATE;
                    DELETE FROM %(reach)s WHERE grant_id IN (SELECT id FROM old_rows);
                END IF;
                IF TG_OP IN ('INSERT', 'UPDATE') THEN
                    PERFORM %(add_grants_fn)s(
                        ARRAY(SELECT %(resource)s FROM new_rows),
                        ARRAY(SELECT id FROM new_rows));
                END IF;
                RETURN NULL;
            END
            $body$;

            DROP TRIGGER IF EXISTS %(node_inserted)s ON %(table)s;
            CREATE TRIGGER %(node_inserted)s AFTER INSERT ON %(table)s
                REFERENCING NEW TABLE AS new_rows
                FOR EACH STATEMENT EXECUTE FUNCTION %(node_inserted_fn)s();
            DROP TRIGGER IF EXISTS %(node_updated)s ON %(table)s;
            CREATE TRIGGER %(node_updated)s AFTER UPDATE ON %(table)s
                REFERENCING NEW TABLE AS new_rows OLD TABLE AS old_rows
                FOR EACH STATEMENT EXECUTE FUNCTION %(node_updated_fn)s();
            DROP TRIGGER IF EXISTS %(node_deleted)s ON %(table)s;
            CREATE TRIGGER %(node_deleted)s AFTER DELETE ON %(table)s
                REFERENCING OLD TABLE AS old_rows
                FOR EACH STATEMENT EXECUTE FUNCTION %(node_deleted_fn)s();
            DROP TRIGGER IF EXISTS %(grant_inserted)s ON %(grant_table)s;
            CREATE TRIGGER %(grant_inserted)s AFTER INSERT ON %(grant_table)s
                REFERENCING NEW TABLE AS new_rows
                FOR EACH STATEMENT EXECUTE FUNCTION %(grant_changed_fn)s();
            DROP TRIGGER IF EXISTS %(grant_updated)s ON %(grant_table)s;
            CREATE TRIGGER %(grant_updated)s AFTER UPDATE ON %(grant_table)s
                REFERENCING NEW TABLE AS new_rows OLD TABLE AS old_rows
                FOR EACH STATEMENT EXECUTE FUNCTION %(grant_changed_fn)s();
            DROP TRIGGER IF EXISTS %(grant_deleted)s ON %(grant_table)s;
            CREATE TRIGGER %(grant_deleted)s AFTER DELETE ON %(grant_table)s
                REFERENCING OLD TABLE AS old_rows
                FOR EACH STATEMENT EXECUTE FUNCTION %(grant_changed_fn)s();
            """,
            reach=SQL.identifier(reach),
            table=table,
            grant_table=grant_table,
            resource=resource,
            key_index=name("key_index"),
            resource_index=name("resource_index"),
            grant_index=name("grant_index"),
            add_grants_fn=name("add_grants"),
            grant_rows=self._access_reach_rows(
                SQL("node_row.id = ANY(ids)"), grants=SQL("grants")
            ),
            closure_fn=name("closure"),
            closure=self._access_reach_closure(),
            refresh_fn=name("refresh"),
            refresh_rows=self._access_reach_rows(SQL("node_row.id = ANY(ids)")),
            node_inserted_fn=name("node_inserted"),
            node_updated_fn=name("node_updated"),
            node_deleted_fn=name("node_deleted"),
            grant_changed_fn=name("grant_changed"),
            node_inserted=name("node_inserted"),
            node_updated=name("node_updated"),
            node_deleted=name("node_deleted"),
            grant_inserted=name("grant_inserted"),
            grant_updated=name("grant_updated"),
            grant_deleted=name("grant_deleted"),
            changed=changed,
            deep_changed=deep_changed,
        )

    # -- lifecycle --------------------------------------------------------------

    def _access_reach_install(self) -> None:
        # create the table, its functions and triggers, and derive every row,
        # whenever what derives them changed since the last install: the
        # functions and triggers of the previous version go first, whatever
        # their shape was
        cr = self.env.cr
        reach = self._access_reach_table()
        self.pool.register_relation_table(self._name, reach, self._original_module)
        ddl = self._access_reach_ddl()
        rows = self._access_reach_rows(SQL("TRUE"))
        signature = hashlib.sha256(
            repr((ddl.code, ddl.params, rows.code, rows.params)).encode()
        ).hexdigest()
        cr.execute(
            SQL(
                """SELECT obj_description(to_regclass(%s), 'pg_class')""",
                reach,
            )
        )
        if cr.fetchone()[0] == signature:
            return
        with _debug.perf("access_reach.rebuild", cr=cr, model=self._name):
            cr.execute(
                SQL(
                    """SELECT DISTINCT proname FROM pg_proc
                        WHERE proname LIKE %s AND pronamespace = current_schema()::regnamespace""",
                    reach.replace("_", r"\_") + r"\_%",
                )
            )
            for (function,) in cr.fetchall():
                cr.execute(SQL("DROP FUNCTION %s CASCADE", SQL.identifier(function)))
            # the scope chain's GIN index served the live condition, which
            # read the chain per row; nothing reads it through an index now
            cr.execute(
                SQL(
                    "DROP INDEX IF EXISTS %s",
                    SQL.identifier(f"{self._table}_access_scope_chain_idx"),
                )
            )
            cr.execute(SQL("DROP TABLE IF EXISTS %s", SQL.identifier(reach)))
            cr.execute(ddl.inlined(cr))
            cr.execute(rows)
            cr.execute(SQL("ANALYZE %s", SQL.identifier(reach)))
            cr.execute(
                SQL(
                    "COMMENT ON TABLE %s IS %s",
                    SQL.identifier(reach),
                    SQL.literal(signature),
                )
            )
