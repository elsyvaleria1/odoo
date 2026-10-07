# Access through the record a row belongs to, as SQL.
#
# A message, a follower, an attachment is reached through the record it is
# on: a (model, res_id) pair naming any model. owner_reach states that as one
# condition the database evaluates -- per owning model, the row's model and
# its owner under that model's own access domain -- instead of reading
# candidate rows into Python and asking each model about its ids.
#
# The owning models are those the search pins, or else what the table holds,
# found by a loose index scan (owner_models). The branches are
# ordered by how many rows each model holds, so a row meets its own after a
# comparison or two, and each is an EXISTS the planner may answer by probing
# the owner's primary key per row (a few rows: one record's chatter) or by
# hashing the owner's reach once (a count over everything).

from __future__ import annotations

import functools
import typing
from collections.abc import Callable, Collection, Sequence

from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import SQL
from odoo.orm.domain import Domain
from odoo.orm.primitives import COLLECTION_TYPES
from odoo.tools.access_scan import get_accessible_ids
from odoo.tools.query import Query

if typing.TYPE_CHECKING:
    from odoo import api, models

__all__ = [
    "CONCRETE",
    "is_bounded",
    "owner_models",
    "owner_reach",
    "pinned_values",
    "search_by_owner",
]

_debug = DebugLog(__name__)

# the hosts whose reach is being stated, outermost first: an owning model that
# is one of them closes a cycle (an attachment on an attachment, a message on
# an attachment on a message), which no fixed SQL states
_COMPILING = "owner_reach_hosts"

# the candidates a page reads at a time, before deciding them
CHUNK = 1000

# a search returning at most this many rows reads few enough to probe each
# row's owner rather than hash every owner the user reaches
BOUNDED_SEARCH = 1000

# what a reach returns for an owning model no domain states: the owners the
# rows name are then decided one by one, by `decide`
CONCRETE = object()

Reach = Callable[["models.BaseModel"], typing.Any]
Decide = Callable[["models.BaseModel"], "models.BaseModel"]


def _readable(owners: models.BaseModel) -> models.BaseModel:
    return owners._filtered_access("read")


def is_bounded(limit: int | bool | None) -> bool:
    return limit is True or (
        isinstance(limit, int)
        and not isinstance(limit, bool)
        and 0 < limit <= BOUNDED_SEARCH
    )


def pinned_values(
    model: models.BaseModel, field_name: str, domain: Domain
) -> Collection[typing.Any] | None:
    # the values a domain holds `field_name` to everywhere it matches (an
    # "=" or "in" its every match obeys), None where it holds it to none
    domain = domain.optimize(model)
    field_only = domain.map_conditions(
        lambda cond: (
            cond
            if cond.field_expr == field_name and cond.operator in ("in", "=")
            else Domain.TRUE
        )
    ).optimize(model)
    condition = next(iter(field_only.iter_conditions()), None)
    if condition is None:
        return None
    if condition.operator == "=":
        return [condition.value]
    if isinstance(condition.value, COLLECTION_TYPES):
        return condition.value
    return None


def owner_models(env: api.Environment, table: str, column: str) -> tuple[str, ...]:
    # the models `table.column` names now, the most frequent first: read for
    # each search that pins none, as a row may land on a new model by any
    # path, raw SQL included, and a stale list would hide it
    rows = env.execute_query(
        SQL(
            """WITH RECURSIVE held AS (
                   (SELECT %(column)s AS name FROM %(table)s
                     WHERE %(column)s > '' ORDER BY %(column)s LIMIT 1)
                   UNION ALL
                   SELECT (SELECT %(column)s FROM %(table)s
                            WHERE %(column)s > held.name
                            ORDER BY %(column)s LIMIT 1)
                     FROM held WHERE held.name IS NOT NULL
               )
               SELECT held.name, coalesce(stats.freq, 0)
                 FROM held
                 LEFT JOIN (
                       SELECT unnest(most_common_vals::text::text[]) AS name,
                              unnest(most_common_freqs) AS freq
                         FROM pg_stats
                        WHERE schemaname = current_schema()
                          AND tablename = %(table_name)s AND attname = %(column_name)s
                 ) AS stats ON stats.name = held.name
                WHERE held.name IS NOT NULL
             ORDER BY 2 DESC, 1""",
            column=SQL.identifier(column),
            table=SQL.identifier(table),
            table_name=table,
            column_name=column,
        )
    )
    known = tuple(name for name, _freq in rows)
    _debug.perf.count("owner_models", table=table, column=column, models=len(known))
    return known


def owner_reach(
    model: models.BaseModel,
    model_field: str,
    res_id_field: str,
    reach: Reach,
    *,
    bounded: bool = False,
    only: Collection[str] | None = None,
    within: Reach | None = None,
    itself: Domain | None = None,
    decide: Decide = _readable,
) -> Domain:
    # The rows of `model` whose owner -- the record of model `model_field`
    # with id `res_id_field` -- is within `reach(Owner)`: a domain on the
    # owning model read in sudo, archived records included; None or FALSE
    # where nothing of that model is reached. An owner reached whole (TRUE)
    # asks nothing of its records, as the record-level check reads no record
    # no rule restricts; a row on no model of the registry is reached by none.
    #
    # `bounded`, for a search returning a page: each owner is probed per row
    # (OFFSET 0 keeps the planner from hashing the owner's whole reach for
    # the rows a page reads, as it would for the count it estimates without
    # the limit). `only`: the owning models the search holds its rows to
    # (pinned_values), no other model's branch stated nor planned.
    # `within(Owner)`: a further condition on the row in that owner's branch,
    # as an attachment's field must be one the user reads on its record.
    # `itself`: what reaches a row other than its owner (an attachment
    # public, or the user's unlinked one); given, a row on a row of the host
    # is reached along the chain of its owners in SQL, else its owners are
    # decided one by one. `decide(owners)`: of some owners, those reached, for
    # an owning model `reach` answers CONCRETE and where a cycle closes (the
    # record-level check by default).
    def to_sql(host: models.BaseModel, alias: str, query: Query) -> SQL:
        host.flush_model([model_field, res_id_field])
        stated = _OwnerReach(
            host,
            model_field,
            res_id_field,
            reach,
            bounded=bounded,
            only=only,
            within=within,
            itself=itself,
            decide=decide,
        ).branches(alias, query, cyclic=True)
        _debug.logic("owner_reach", model=host._name, branches=len(stated))
        if not stated:
            return SQL("FALSE")
        return SQL("(%s)", SQL(" OR ").join(stated))

    return Domain.custom(to_sql=to_sql)


class _OwnerReach:
    def __init__(
        self,
        host: models.BaseModel,
        model_field: str,
        res_id_field: str,
        reach: Reach,
        *,
        bounded: bool,
        only: Collection[str] | None,
        within: Reach | None,
        itself: Domain | None,
        decide: Decide,
    ) -> None:
        self.host = host
        self.model_field = model_field
        self.res_id_field = res_id_field
        self.reach = reach
        self.bounded = bounded
        self.within = within
        self.itself = itself
        self.decide = decide
        env = host.env
        self.compiling = (*env.context.get(_COMPILING, ()), host._name)
        self.owner_env = env(context={**env.context, _COMPILING: self.compiling})
        names = owner_models(env, host._table, model_field) if only is None else only
        self.names = [name for name in dict.fromkeys(names) if name and name in env]

    def branches(
        self,
        at: str,
        at_query: Query,
        *,
        cyclic: bool,
        names: Collection[str] | None = None,
    ) -> list[SQL]:
        # one branch per owning model (`names`, else the reach's own), the
        # models reached whole as one
        unrestricted = []
        stated = []
        for name in self.names if names is None else names:
            if name == self.host._name and self.itself is not None:
                if cyclic and (chain := self.self_chain(at, at_query)):
                    stated.append(chain)
                continue
            if name in self.compiling:
                if edge := self.concrete(name, at, at_query):
                    stated.append(edge)
                continue
            branch = self.branch(name, at, at_query)
            if branch is True:
                unrestricted.append(name)
            elif branch:
                stated.append(branch)
        if unrestricted:
            stated.insert(
                0,
                SQL(
                    "(%s = ANY(%s) AND %s <> 0)",
                    SQL.identifier(at, self.model_field),
                    unrestricted,
                    SQL.identifier(at, self.res_id_field),
                ),
            )
        return stated

    def branch(self, name: str, at: str, at_query: Query) -> SQL | bool:
        # the branch of one owning model: True where it is reached whole and
        # the row asks nothing more, False where nothing of it is reached
        try:
            domain = self.reach(self.owner_env[name])
            if domain is CONCRETE:
                return self.concrete(name, at, at_query) or False
        except AccessError:
            # a model the user may not search reaches them nothing
            _debug.logic("owner_reach.refused", model=self.host._name, owner=name)
            return False
        if domain is None or domain.is_false():
            return False
        row_sql = self.row_condition(name, at, at_query)
        if row_sql is None:
            return False
        model_column = SQL.identifier(at, self.model_field)
        res_id = SQL.identifier(at, self.res_id_field)
        if domain.is_true():
            if not row_sql:
                return True
            return SQL("(%s = %s AND %s <> 0%s)", model_column, name, res_id, row_sql)
        Owner = self.host.env[name].sudo().with_context(active_test=False)
        owned = Owner._search(domain, bypass_access=True)
        if owned.is_empty():
            return False
        owned.order = None
        if owned.table == at:
            owner_sql = SQL("%s IN %s", res_id, owned.subselect())
        else:
            owned.add_where(SQL("%s = %s", SQL.identifier(owned.table, "id"), res_id))
            owner_sql = SQL(
                "EXISTS (%s%s)",
                owned.select(SQL("1")),
                SQL(" OFFSET 0") if self.bounded else SQL(),
            )
        return SQL("(%s = %s AND %s%s)", model_column, name, owner_sql, row_sql)

    def row_condition(self, name: str, at: str, at_query: Query) -> SQL | None:
        # the row's own condition in the branch of `name`: SQL() for none,
        # None where no row of that branch is reached
        if self.within is None:
            return SQL()
        on_row = self.within(self.owner_env[name])
        if on_row is None:
            return SQL()
        on_row = on_row.optimize_full(self.host)
        if on_row.is_false():
            return None
        if on_row.is_true():
            return SQL()
        return SQL(" AND %s", on_row._to_sql(self.host, at, at_query))

    def self_chain(self, at: str, at_query: Query) -> SQL | None:
        # a row on a row of the host: reached where its owner is, and the
        # owner where its own owner is, as far as the chain goes. Stated over
        # the rows that own others only, by a recursive CTE whose base is what
        # reaches an owner otherwise (itself, or another model's record) and
        # whose step climbs one owner at a time
        host = self.host
        assert self.itself is not None
        row_sql = self.row_condition(host._name, at, at_query)
        if row_sql is None:
            return None
        env = host.env
        table = SQL.identifier(host._table)
        model_field = SQL.identifier(self.model_field)
        owners = SQL(
            "SELECT %s FROM %s WHERE %s = %s",
            SQL.identifier(self.res_id_field),
            table,
            model_field,
            host._name,
        )
        # the owners are on few models: their branches alone are stated
        owner_owners = sorted(
            name
            for (name,) in env.execute_query(
                SQL(
                    "SELECT DISTINCT owner.%s FROM %s AS owner WHERE owner.id IN (%s)",
                    model_field,
                    table,
                    owners,
                )
            )
            if name and name in env
        )
        step = Query.get_table_alias(at, "owner_chain")
        # an owner is the host's record too: its own access rows bind it
        rules = env.registry.access_policy.record_domain(env, host._name, "read")
        sudo_host = host.sudo().with_context(active_test=False)
        rules = rules.optimize_full(sudo_host)
        base_query = Query(env, step, table)
        if not rules.is_true():
            base_query.add_where(rules._to_sql(sudo_host, step, base_query))
        itself = self.itself.optimize_full(host)._to_sql(host, step, base_query)
        base = [
            SQL("(%s)", itself),
            *self.branches(step, base_query, cyclic=False, names=owner_owners),
        ]
        base_query.add_where(SQL("%s IN (%s)", SQL.identifier(step, "id"), owners))
        base_query.add_where(SQL("(%s)", SQL(" OR ").join(base)))
        climb_query = Query(env, step, table)
        if not rules.is_true():
            climb_query.add_where(rules._to_sql(sudo_host, step, climb_query))
        climb_sql = self.row_condition(host._name, step, climb_query)
        reached_name = f"{step}__reached"
        reached = SQL.identifier(reached_name)
        # the recursive reference joins: PostgreSQL refuses it in a subquery
        climb_query.add_join(
            "JOIN",
            reached_name,
            reached,
            SQL(
                "%s = %s",
                SQL.identifier(reached_name, "id"),
                SQL.identifier(step, self.res_id_field),
            ),
        )
        climb_query.add_where(
            SQL(
                "%s IN (%s) AND %s = %s%s",
                SQL.identifier(step, "id"),
                owners,
                SQL.identifier(step, self.model_field),
                host._name,
                climb_sql if climb_sql is not None else SQL(" AND FALSE"),
            )
        )
        return SQL(
            """(%s = %s AND %s IN (
                   WITH RECURSIVE %s(id) AS (%s UNION %s)
                   SELECT id FROM %s)%s)""",
            SQL.identifier(at, self.model_field),
            host._name,
            SQL.identifier(at, self.res_id_field),
            reached,
            base_query.select(SQL.identifier(step, "id")),
            climb_query.select(SQL.identifier(step, "id")),
            reached,
            row_sql,
        )

    def concrete(self, name: str, at: str, at_query: Query) -> SQL | None:
        # the records the rows name, decided one by one (`decide`): where no
        # domain states an owner's reach, and where the owners are a model
        # being stated further out -- the record-level check follows the rows
        # and ends where they do
        host = self.host
        env = host.env
        rows = env.execute_query(
            SQL(
                "SELECT DISTINCT %s FROM %s WHERE %s = %s AND %s <> 0",
                SQL.identifier(self.res_id_field),
                SQL.identifier(host._table),
                SQL.identifier(self.model_field),
                name,
                SQL.identifier(self.res_id_field),
            )
        )
        owners = env[name].with_context(active_test=False).browse(i for (i,) in rows)
        readable = self.decide(owners)._ids
        _debug.perf.count(
            "owner_reach.concrete",
            model=host._name,
            owner=name,
            named=len(owners),
            readable=len(readable),
        )
        if not readable:
            return None
        row_sql = self.row_condition(name, at, at_query)
        if row_sql is None:
            return None
        return SQL(
            "(%s = %s AND %s = ANY(%s)%s)",
            SQL.identifier(at, self.model_field),
            name,
            SQL.identifier(at, self.res_id_field),
            sorted(readable),
            row_sql,
        )


def search_by_owner(
    model: models.BaseModel,
    domain: Domain,
    offset: int,
    limit: int | None,
    order: str | None,
    base_search: Callable[..., Query],
    reached: Callable[[Collection[str] | None, bool], Domain],
    model_field: str,
    **kwargs: typing.Any,
) -> Query:
    # the rows of `domain` the user reaches, `reached(only, bounded)` being
    # their reach on the owning models `only` (None: all). A search that holds
    # its rows to some owning models, or reads past a page, is one statement;
    # a page over every model is not -- the reach of every owning model is a
    # statement too large to plan for eighty rows -- so its candidates come a
    # chunk at a time, each decided by the reach of the models it holds alone
    pinned = pinned_values(model, model_field, domain)
    if pinned is None and (ids := pinned_values(model, "id", domain)) is not None:
        # a search by ids asks the models of those rows, not of the table
        pinned = _owner_models_of(model, model_field, ids)
    bounded = is_bounded(limit)
    if pinned is not None or not bounded:
        return base_search(
            domain & reached(pinned, bounded), offset, limit, order, **kwargs
        )
    table = SQL.identifier(model._table)
    column = SQL.identifier(model._table, model_field)

    def fetch(query: Query) -> list[tuple]:
        return model.env.execute_query(query.select(SQL("%s.id", table), column))

    def allowed(rows: Sequence[Sequence[typing.Any]]) -> list[int]:
        ids = [row[0] for row in rows]
        if not ids:
            return []
        held = {row[1] for row in rows if row[1]}
        query = base_search(Domain("id", "in", ids) & reached(held, True), **kwargs)
        return list(query.get_result_ids())

    unchecked = model.sudo().with_context(active_test=False)
    ids = get_accessible_ids(
        model,
        domain,
        offset,
        limit,
        order,
        functools.partial(unchecked._search, bypass_access=True),
        fetch=fetch,
        allowed=allowed,
        chunk_min=CHUNK,
        chunk_max=CHUNK,
        keyset=True,
    )
    return model.browse(ids)._as_query(bool(order))


def _owner_models_of(
    model: models.BaseModel, model_field: str, ids: Collection[typing.Any]
) -> list[str]:
    ids = [id_ for id_ in ids if isinstance(id_, int) and not isinstance(id_, bool)]
    if not ids:
        return []
    # the rows the transaction read already say it, as they will to the search
    cached = model._fields[model_field]._get_cache(model.env)
    if all(id_ in cached for id_ in ids):
        return list(dict.fromkeys(cached[id_] for id_ in ids if cached[id_]))
    model.flush_model([model_field])
    rows = model.env.execute_query(
        SQL(
            "SELECT DISTINCT %s FROM %s WHERE id = ANY(%s) AND %s IS NOT NULL",
            SQL.identifier(model_field),
            SQL.identifier(model._table),
            ids,
            SQL.identifier(model_field),
        )
    )
    return [name for (name,) in rows]
