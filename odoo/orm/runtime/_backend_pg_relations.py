from __future__ import annotations

import typing
from collections import defaultdict

from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import SQL
from odoo.tools import Query

if typing.TYPE_CHECKING:
    from .._typing import ModelLike

_debug = DebugLog("odoo.orm.runtime.backend")


class _PostgresRelationsMixin:
    __slots__ = ()

    def read_m2m_groups(
        self,
        records: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        query: Query,
        *,
        probe_links: bool = False,
    ) -> dict[int, list[int]]:
        sql_id1 = SQL.identifier(relation, column1)
        sql_id2 = SQL.identifier(relation, column2)
        group: dict[int, list[int]] = defaultdict(list)
        if probe_links and not records.env.execute_query(
            SQL(
                "SELECT 1 FROM %s WHERE %s = ANY(%s) LIMIT 1",
                SQL.identifier(relation),
                sql_id1,
                list(records.ids),
            )
        ):
            return group
        query.add_join(
            "JOIN",
            relation,
            None,
            SQL("%s = %s", sql_id2, SQL.identifier(query.table, "id")),
        )
        query.add_where(SQL("%s = ANY(%s)", sql_id1, list(records.ids)))
        for id1, id2 in records.env.execute_query(query.statement(sql_id1, sql_id2)):
            group[id1].append(id2)
        return group

    def count_m2m_groups(
        self,
        records: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        query: Query,
    ) -> dict[int, int]:
        sql_id1 = SQL.identifier(relation, column1)
        rows = records.env.execute_query(
            SQL(
                "SELECT %s, count(*) FROM %s WHERE %s = ANY(%s) AND %s IN %s "
                "GROUP BY %s",
                sql_id1,
                SQL.identifier(relation),
                sql_id1,
                list(records.ids),
                SQL.identifier(relation, column2),
                query.subselect(),
                sql_id1,
            )
        )
        return dict(rows)

    def link_m2m_pairs(
        self,
        model: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        pairs: typing.Iterable[tuple[int, int]],
    ) -> None:
        cr = model.env.cr
        cr.execute(
            SQL(
                "INSERT INTO %s (%s, %s) VALUES %s ON CONFLICT DO NOTHING",
                SQL.identifier(relation),
                SQL.identifier(column1),
                SQL.identifier(column2),
                SQL(", ").join(pairs),
            )
        )
        _debug.perf.count(
            "backend.m2m.linked",
            model=model._name,
            relation=relation,
            inserted=cr.rowcount,
        )

    def unlink_m2m_pairs(
        self,
        model: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        pairs: typing.Iterable[tuple[int, int]],
    ) -> None:
        xs_to_ys: dict[frozenset[int], set[int]] = defaultdict(set)
        y_to_xs: dict[int, set[int]] = defaultdict(set)
        for x, y in pairs:
            y_to_xs[y].add(x)
        for y, xs in y_to_xs.items():
            xs_to_ys[frozenset(xs)].add(y)
        cr = model.env.cr
        cr.execute(
            SQL(
                "DELETE FROM %s WHERE %s",
                SQL.identifier(relation),
                SQL(" OR ").join(
                    SQL(
                        "%s = ANY(%s) AND %s = ANY(%s)",
                        SQL.identifier(column1),
                        list(xs),
                        SQL.identifier(column2),
                        list(ys),
                    )
                    for xs, ys in xs_to_ys.items()
                ),
            )
        )
        _debug.perf.count(
            "backend.m2m.unlinked",
            model=model._name,
            relation=relation,
            groups=len(xs_to_ys),
            deleted=cr.rowcount,
        )
