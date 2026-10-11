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

PARTNER, GROUP, USER = 0, 1, 2
OWN = 0

REACH_COLUMNS = (
    "resource_id",
    "key",
    "via",
    "rank",
    "node_company_id",
    "resource_company_id",
    "resource_user_id",
    "grant_id",
    "grant_resource_id",
)


def principal_key(kind: int, principal_id: int) -> int:
    return principal_id * 4 + kind


class MixinAccessGraph(models.AbstractModel):
    _inherit = "mixin.access.graph"

    def init(self) -> None:
        super().init()
        if self._access_graph is not None and not self._abstract:
            reach = self._access_reach_table()
            for table in (reach, f"{reach}_lock"):
                self.pool.register_relation_table(
                    self._name, table, self._original_module
                )
            self.pool.post_init(self._access_reach_install)


    def _access_reach_table(self) -> str:
        return f"{self._table}_access_reach"

    def _access_reach_tracked_columns(self) -> list[str]:
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
        graph = self._access_graph
        return [
            *((graph.owner,) if graph.owner else ()),
            *((graph.container[0],) if graph.container else ()),
            *((graph.boundary,) if graph.boundary else ()),
        ]

    def _access_reach_own_via(self) -> SQL:
        return SQL("%s", OWN)

    def _access_reach_graph_needs(self) -> list[SQL]:
        return []

    def _access_reach_ctes(self) -> list[tuple[str, SQL]]:
        return []

    def _access_reach_derived(self) -> list[SQL]:
        return []

    def _access_reach_readers(self, affected: SQL) -> list[SQL]:
        return []

    def _access_reach_graph_vias(self) -> tuple[int, ...]:
        return (OWN,)


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
        keys = sorted(set(keys))
        grant_model = self.env[self._fields[graph.grants].comodel_name]
        names = type(grant_model)._access_grant_names
        return SQL(
            """SELECT resource_id FROM (
                   SELECT resource_id, (key %% 4)::int2 AS kind, (key / 4)::int4 AS pid,
                          via, rank, NULL::int4 AS grant_company_id, node_company_id,
                          resource_company_id, resource_user_id, NULL::timestamp AS date_to
                     FROM %(reach)s WHERE key = ANY(%(keys)s)
                   UNION ALL
                   SELECT reach.resource_id,
                          (CASE WHEN grant_row.partner_id IS NULL THEN %(group)s ELSE %(partner)s END)::int2,
                          coalesce(grant_row.partner_id, grant_row.group_id), reach.via,
                          coalesce(reach.rank, array_position(%(roles)s::varchar[], grant_row.%(role)s::varchar)::int2),
                          grant_row.company_id, reach.node_company_id, reach.resource_company_id,
                          reach.resource_user_id, grant_row.date_to
                     FROM %(grant_table)s AS grant_row
                     JOIN %(reach)s AS reach ON reach.grant_id = grant_row.id
                    WHERE grant_row.partner_id = ANY(%(partners)s)
                       OR grant_row.group_id = ANY(%(groups)s)
               ) AS reach WHERE %(reached)s""",
            reach=SQL.identifier(self._access_reach_table()),
            keys=keys,
            group=GROUP,
            partner=PARTNER,
            roles=list(graph.roles),
            role=SQL.identifier(names.role),
            grant_table=SQL.identifier(grant_model._table),
            partners=[key // 4 for key in keys if key % 4 == PARTNER],
            groups=[key // 4 for key in keys if key % 4 == GROUP],
            reached=SQL(" OR ").join(reached),
        )


    def _access_reach_company_column(self) -> str | None:
        anchor = self._access_company_anchor()
        if anchor and "." in anchor:
            raise ValueError(
                f"{self._name}: the access graph needs its company anchor on the "
                f"node itself, not through {anchor!r}"
            )
        return anchor

    def _access_reach_scope_ctes(self, node_company: SQL) -> list[tuple[str, SQL]]:
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
                """SELECT node.node_id AS resource_id, NULL::int8 AS key, NULL::int2 AS rank,
                          node.company_id AS node_company_id, grant_row.id AS grant_id,
                          grant_row.%(resource)s AS grant_resource_id
                     FROM node_scope AS node %(scope_join)s
                     JOIN %(grant_table)s AS grant_row
                       ON grant_row.%(resource)s = held_by.id
                      AND %(grants)s""",
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
                    """SELECT node.node_id, held_by.%(owner)s::int8 * 4 + %(user)s, %(top)s::int2,
                              node.company_id, NULL::int4, NULL::int4
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
            """SELECT graph.resource_id, graph.key, (%s)::int2, graph.rank,
                      graph.node_company_id, NULL::int4, NULL::int4, graph.grant_id,
                      graph.grant_resource_id
                 FROM graph JOIN scope ON scope.id = graph.resource_id""",
            self._access_reach_own_via(),
        )
        columns = SQL(", ").join(SQL.identifier(column) for column in REACH_COLUMNS)
        rows = SQL(" UNION ALL ").join([own, *self._access_reach_derived()])
        if grants is not None:
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

    def _access_reach_reads(self) -> SQL:
        graph: AccessGraph = self._access_graph
        return SQL(
            """WITH scope AS (
                   SELECT node_row.* FROM %(table)s AS node_row
                    WHERE node_row.id = ANY(touched)
               )
               %(reads)s""",
            table=SQL.identifier(self._table),
            reads=SQL(" UNION ").join(
                [
                    SQL("SELECT %s FROM scope", SQL.identifier(graph.parent)),
                    *self._access_reach_graph_needs(),
                ]
            ),
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
            -- a row names its principal, or the grant that does: the grant
            -- is read through its node too, so that moving it is a change of
            -- the key a concurrent row's check locks
            CREATE UNIQUE INDEX IF NOT EXISTS %(grant_key)s ON %(grant_table)s (id, %(resource)s);
            CREATE TABLE IF NOT EXISTS %(reach)s (
                resource_id int4 NOT NULL,
                key int8,
                via int2 NOT NULL,
                rank int2,
                node_company_id int4,
                resource_company_id int4,
                resource_user_id int4,
                grant_id int4,
                grant_resource_id int4,
                CONSTRAINT %(principal_check)s CHECK ((key IS NULL) = (grant_id IS NOT NULL)),
                CONSTRAINT %(rank_check)s CHECK (rank IS NOT NULL OR grant_id IS NOT NULL),
                CONSTRAINT %(grant_fkey)s FOREIGN KEY (grant_id, grant_resource_id)
                    REFERENCES %(grant_table)s (id, %(resource)s) MATCH FULL
                    ON DELETE CASCADE ON UPDATE CASCADE
            );
            CREATE INDEX IF NOT EXISTS %(key_index)s ON %(reach)s (key) INCLUDE (
                resource_id, via, rank, node_company_id, resource_company_id,
                resource_user_id) WHERE key IS NOT NULL;
            CREATE INDEX IF NOT EXISTS %(resource_index)s ON %(reach)s (resource_id);
            CREATE INDEX IF NOT EXISTS %(grant_index)s ON %(reach)s (grant_id) INCLUDE (
                resource_id, via, rank, node_company_id, resource_company_id,
                resource_user_id) WHERE grant_id IS NOT NULL;

            -- the node lock (the class's comment): a row per node, written
            CREATE TABLE IF NOT EXISTS %(lock)s (
                node_id int4 PRIMARY KEY REFERENCES %(table)s (id) ON DELETE CASCADE
            );

            CREATE OR REPLACE FUNCTION %(lock_fn)s(ids int4[]) RETURNS void
            LANGUAGE sql AS $body$
                INSERT INTO %(lock)s (node_id)
                SELECT id FROM %(table)s WHERE id = ANY(ids) ORDER BY id
                ON CONFLICT (node_id) DO UPDATE SET node_id = excluded.node_id
            $body$;

            CREATE OR REPLACE FUNCTION %(closure_fn)s(ids int4[], deep boolean) RETURNS int4[]
            LANGUAGE plpgsql STABLE AS $body$ %(closure)s $body$;

            -- re-derive the rows of the nodes a statement changed and of what
            -- reads them: `deep` with their subtrees, `shallow` without,
            -- `created` alone, nothing reading a node the statement created
            CREATE OR REPLACE FUNCTION %(refresh_fn)s(
                deep int4[], shallow int4[], created int4[])
            RETURNS void LANGUAGE plpgsql AS $body$
            DECLARE
                touched int4[] := deep || shallow || created;
                ids int4[] := '{}';
            BEGIN
                IF cardinality(touched) = 0 THEN
                    RETURN;
                END IF;
                IF cardinality(deep) > 0 THEN
                    ids := %(closure_fn)s(deep, true);
                END IF;
                IF cardinality(shallow) > 0 THEN
                    ids := ids || %(closure_fn)s(shallow, false);
                END IF;
                PERFORM %(lock_fn)s(ids || ARRAY(%(reads)s));
                ids := ids || created;
                DELETE FROM %(reach)s WHERE resource_id = ANY(ids);
                %(refresh_rows)s;
            END
            $body$;

            CREATE OR REPLACE FUNCTION %(node_inserted_fn)s() RETURNS trigger
            LANGUAGE plpgsql AS $body$
            BEGIN
                PERFORM %(refresh_fn)s('{}', '{}', ARRAY(SELECT id FROM new_rows));
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
                SELECT coalesce(array_agg(new_row.id) FILTER (WHERE %(deep_changed)s), '{}'),
                       coalesce(array_agg(new_row.id) FILTER (WHERE NOT (%(deep_changed)s)), '{}')
                  INTO deep_ids, shallow_ids
                  FROM new_rows AS new_row
                  JOIN old_rows AS old_row ON old_row.id = new_row.id
                 WHERE %(changed)s;
                PERFORM %(refresh_fn)s(deep_ids, shallow_ids, '{}');
                RETURN NULL;
            END
            $body$;

            -- the deleted nodes' rows go with them; what read them is re-derived
            CREATE OR REPLACE FUNCTION %(node_deleted_fn)s() RETURNS trigger
            LANGUAGE plpgsql AS $body$
            BEGIN
                PERFORM %(refresh_fn)s('{}', ARRAY(SELECT id FROM old_rows), '{}');
                RETURN NULL;
            END
            $body$;

            -- a grant is the source of its rows, each carrying its id: what
            -- the grants reach is derived alone, the subtree's other rows
            -- untouched, and a grant's foreign key removes them with it
            CREATE OR REPLACE FUNCTION %(derive_grants_fn)s(touched int4[], grants int4[])
            RETURNS void LANGUAGE plpgsql AS $body$
            DECLARE
                ids int4[];
            BEGIN
                IF cardinality(grants) = 0 THEN
                    RETURN;
                END IF;
                ids := %(closure_fn)s(touched, true);
                PERFORM %(lock_fn)s(ids);
                DELETE FROM %(reach)s WHERE grant_id = ANY(grants);
                %(grant_rows)s;
            END
            $body$;

            CREATE OR REPLACE FUNCTION %(grant_inserted_fn)s() RETURNS trigger
            LANGUAGE plpgsql AS $body$
            BEGIN
                PERFORM %(derive_grants_fn)s(
                    ARRAY(SELECT %(resource)s FROM new_rows),
                    ARRAY(SELECT id FROM new_rows));
                RETURN NULL;
            END
            $body$;

            CREATE OR REPLACE FUNCTION %(grant_moved_fn)s() RETURNS trigger
            LANGUAGE plpgsql AS $body$
            BEGIN
                PERFORM %(derive_grants_fn)s(ARRAY[NEW.%(resource)s], ARRAY[NEW.id]);
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
                FOR EACH STATEMENT EXECUTE FUNCTION %(grant_inserted_fn)s();
            DROP TRIGGER IF EXISTS %(grant_moved)s ON %(grant_table)s;
            CREATE TRIGGER %(grant_moved)s AFTER UPDATE OF %(resource)s ON %(grant_table)s
                FOR EACH ROW WHEN (OLD.%(resource)s IS DISTINCT FROM NEW.%(resource)s)
                EXECUTE FUNCTION %(grant_moved_fn)s();
            """,
            reach=SQL.identifier(reach),
            table=table,
            grant_table=grant_table,
            resource=resource,
            key_index=name("key_index"),
            resource_index=name("resource_index"),
            grant_index=name("grant_index"),
            lock=name("lock"),
            lock_fn=name("lock_nodes"),
            reads=self._access_reach_reads(),
            derive_grants_fn=name("derive_grants"),
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
            grant_inserted_fn=name("grant_inserted"),
            grant_moved_fn=name("grant_moved"),
            node_inserted=name("node_inserted"),
            node_updated=name("node_updated"),
            node_deleted=name("node_deleted"),
            grant_inserted=name("grant_inserted"),
            grant_moved=name("grant_moved"),
            grant_key=SQL.identifier(f"{grant_model._table}_reach_key"),
            principal_check=name("principal_check"),
            rank_check=name("rank_check"),
            grant_fkey=name("grant_fkey"),
            changed=changed,
            deep_changed=deep_changed,
        )


    def _access_reach_install(self) -> None:
        cr = self.env.cr
        reach = self._access_reach_table()
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
            cr.execute(
                SQL(
                    "DROP INDEX IF EXISTS %s",
                    SQL.identifier(f"{self._table}_access_scope_chain_idx"),
                )
            )
            for table in (reach, f"{reach}_lock"):
                cr.execute(SQL("DROP TABLE IF EXISTS %s", SQL.identifier(table)))
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
