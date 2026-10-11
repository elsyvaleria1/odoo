from __future__ import annotations

import typing

from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import SQL
from odoo.tools import Query

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..domain import Domain

_debug = DebugLog("odoo.orm.runtime.backend")


def _single_table_where(model: ModelLike, domain: Domain) -> SQL | None:
    if domain.is_true():
        return None
    query = model._search(domain)
    if query.from_clause != SQL.identifier(model._table):
        raise ValueError(
            f"descendants({model._name}): the domain must resolve against "
            f"{model._table} alone, the recursive query inlines its WHERE clause "
            f"and cannot carry a join. Got: {query.from_clause}"
        )
    return query.where_clause if query._where_clauses else None


class _PostgresHierarchyMixin:
    __slots__ = ()

    def ancestors(
        self,
        model: ModelLike,
        parent_field: str,
        ids: typing.Collection[int],
        *,
        flush: bool = True,
    ) -> list[tuple[int, int | None]]:
        if not ids:
            return []
        return model.env.execute_query(
            SQL(
                """
                WITH RECURSIVE ancestry AS (
                    SELECT id, %(parent)s AS parent_id FROM %(table)s WHERE id = ANY(%(ids)s)
                UNION
                    SELECT parent.id, parent.%(parent)s
                    FROM %(table)s parent
                    INNER JOIN ancestry child ON child.parent_id = parent.id
                )
                SELECT id, parent_id FROM ancestry
                """,
                table=SQL.identifier(model._table),
                parent=SQL.identifier(
                    parent_field,
                    to_flush=model._fields[parent_field] if flush else None,
                ),
                ids=list(ids),
            )
        )

    def descendant_edges(
        self, model: ModelLike, parent_field: str, ids: typing.Collection[int]
    ) -> list[tuple[int, int]]:
        if not ids:
            return []
        parent = SQL.identifier(parent_field, to_flush=model._fields[parent_field])
        return model.env.execute_query(
            SQL(
                """
                WITH RECURSIVE descent AS (
                    SELECT id, %(parent)s AS parent_id FROM %(table)s
                    WHERE %(parent)s = ANY(%(ids)s)
                UNION
                    SELECT child.id, child.%(parent)s
                    FROM %(table)s child
                    INNER JOIN descent ON child.%(parent)s = descent.id
                )
                SELECT id, parent_id FROM descent
                """,
                table=SQL.identifier(model._table),
                parent=parent,
                ids=list(ids),
            )
        )

    def descendants(
        self,
        model: ModelLike,
        parent_field: str,
        root_ids: typing.Collection[int],
        *,
        domain: Domain,
        step_domain: Domain,
        same_columns: typing.Sequence[str] = (),
    ) -> Query:
        table = SQL.identifier(model._table)
        base_where = _single_table_where(model, domain)
        step_where = _single_table_where(model, domain & step_domain)
        columns = SQL(", ").join(
            SQL(", %s", SQL.identifier(model._table, column)) for column in same_columns
        )
        same = SQL("").join(
            SQL(
                " AND COALESCE(%s::text, '') = COALESCE(parent.%s::text, '')",
                SQL.identifier(model._table, column),
                SQL.identifier(column),
            )
            for column in same_columns
        )
        closure = SQL(
            """WITH RECURSIVE closure AS (
                SELECT %(id)s%(columns)s FROM %(table)s
                WHERE %(id)s = ANY(%(roots)s)%(base_where)s
            UNION
                SELECT %(id)s%(columns)s FROM %(table)s
                JOIN closure parent ON parent.id = %(parent)s
                WHERE TRUE%(step_where)s%(same)s
            )
            SELECT id FROM closure""",
            id=SQL.identifier(model._table, "id"),
            columns=columns,
            table=table,
            roots=list(root_ids),
            base_where=SQL(" AND (%s)", base_where) if base_where else SQL(),
            parent=SQL.identifier(
                model._table, parent_field, to_flush=model._fields[parent_field]
            ),
            step_where=SQL(" AND (%s)", step_where) if step_where else SQL(),
            same=same,
        )
        query = Query(model.env, model._table, model._table_sql)
        query.add_where(SQL("%s IN (%s)", SQL.identifier(model._table, "id"), closure))
        return query

    def has_cycle(
        self,
        model: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        ids: typing.Collection[int],
    ) -> bool:
        cr = model.env.cr
        cr.execute(
            SQL(
                """
            WITH RECURSIVE __reachability AS (
                SELECT %(col1)s AS source, %(col2)s AS destination
                FROM %(rel)s
                WHERE %(col1)s = ANY(%(ids)s) AND %(col2)s IS NOT NULL
            UNION
                SELECT r.source, t.%(col2)s
                FROM __reachability r
                JOIN %(rel)s t ON r.destination = t.%(col1)s AND t.%(col2)s IS NOT NULL
            )
            SELECT 1 FROM __reachability
            WHERE source = destination
            LIMIT 1
            """,
                ids=list(ids),
                rel=SQL.identifier(relation),
                col1=SQL.identifier(column1),
                col2=SQL.identifier(column2),
            )
        )
        return cr.fetchone() is not None

    def set_parent_paths(
        self, model: ModelLike, ids: typing.Sequence[int]
    ) -> list[tuple[int, str]]:
        rows = model.env.execute_query(
            SQL(
                """ UPDATE %(table)s node
                SET parent_path = CASE
                    WHEN node.%(parent)s IS NULL THEN node.id || '/'
                    ELSE (
                        SELECT parent.parent_path
                        FROM %(table)s parent
                        WHERE parent.id = node.%(parent)s
                    ) || node.id || '/'
                END
                WHERE node.id = ANY(%(ids)s)
                RETURNING node.id, node.parent_path """,
                table=SQL.identifier(model._table),
                parent=SQL.identifier(model._parent_name),
                ids=list(ids),
            )
        )
        updated = [(id_, path) for id_, path in rows if path is not None]
        if orphans := [id_ for id_, path in rows if path is None]:
            updated.extend(self._rebuild_parent_paths(model, orphans).items())
        return updated

    def records_with_parent_changed(
        self, model: ModelLike, parent_to_ids: dict[typing.Any, list[int]]
    ) -> list[int]:
        sql_parent = SQL.identifier(model._parent_name)
        conditions = []
        for parent_id, ids in parent_to_ids.items():
            if parent_id:
                condition = SQL(
                    "(%s != %s OR %s IS NULL)", sql_parent, parent_id, sql_parent
                )
            else:
                condition = SQL("%s IS NOT NULL", sql_parent)
            conditions.append(SQL('("id" = ANY(%s) AND %s)', list(ids), condition))
        rows = model.env.execute_query(
            SQL(
                "SELECT id FROM %s WHERE %s ORDER BY id",
                SQL.identifier(model._table),
                SQL(" OR ").join(conditions),
            )
        )
        return [row[0] for row in rows]

    def move_parent_paths(
        self, model: ModelLike, ids: typing.Sequence[int], prefix: str
    ) -> dict[int, str]:
        rows = model.env.execute_query(
            SQL(
                """ WITH node AS (
                    SELECT node.id, node.parent_path,
                        node.parent_path IS NULL OR (
                            node.%(parent)s IS NOT NULL AND parent.parent_path IS NULL
                        ) AS unlocated
                    FROM %(table)s node
                    LEFT JOIN %(table)s parent ON parent.id = node.%(parent)s
                    WHERE node.id = ANY(%(ids)s)
                ), moved AS (
                    UPDATE %(table)s child
                    SET parent_path = %(prefix)s::text || substr(child.parent_path,
                        length(owner.parent_path) - length(owner.id || '/') + 1)
                    FROM (
                        SELECT DISTINCT ON (child.id)
                            child.id AS child_id, node.id, node.parent_path
                        FROM node
                        JOIN %(table)s child
                            ON child.parent_path LIKE node.parent_path || %(wildcard)s::text
                        WHERE NOT node.unlocated
                        ORDER BY child.id, length(node.parent_path) DESC
                    ) owner
                    WHERE child.id = owner.child_id
                    RETURNING child.id, child.parent_path
                )
                SELECT id, parent_path FROM moved
                UNION ALL
                SELECT id, NULL FROM node WHERE unlocated """,
                table=SQL.identifier(model._table),
                parent=SQL.identifier(model._parent_name),
                prefix=prefix,
                ids=list(ids),
                wildcard="%",
            )
        )
        moved = {id_: path for id_, path in rows if path is not None}
        if unlocated := [id_ for id_, path in rows if path is None]:
            moved.update(self._rebuild_parent_paths(model, unlocated))
        return moved

    def _rebuild_parent_paths(self, model: ModelLike, ids: list[int]) -> dict[int, str]:
        rows = model.env.execute_query(
            SQL(
                """ WITH RECURSIVE missing AS (
                    SELECT parent.id, parent.%(parent)s AS parent_id
                    FROM %(table)s node
                    JOIN %(table)s parent ON parent.id = node.%(parent)s
                    WHERE node.id = ANY(%(ids)s) AND parent.parent_path IS NULL
                UNION
                    SELECT parent.id, parent.%(parent)s
                    FROM missing
                    JOIN %(table)s parent ON parent.id = missing.parent_id
                    WHERE parent.parent_path IS NULL
                ), healed AS (
                    SELECT missing.id,
                        coalesce(parent.parent_path, '') || missing.id || '/' AS path
                    FROM missing
                    LEFT JOIN %(table)s parent ON parent.id = missing.parent_id
                    WHERE missing.parent_id IS NULL OR parent.parent_path IS NOT NULL
                UNION ALL
                    SELECT missing.id, healed.path || missing.id || '/'
                    FROM missing
                    JOIN healed ON missing.parent_id = healed.id
                ), subtree AS (
                    SELECT node.id,
                        coalesce(healed.path, parent.parent_path, '') || node.id || '/'
                            AS path
                    FROM %(table)s node
                    LEFT JOIN %(table)s parent ON parent.id = node.%(parent)s
                    LEFT JOIN healed ON healed.id = node.%(parent)s
                    WHERE node.id = ANY(%(ids)s)
                UNION ALL
                    SELECT child.id, subtree.path || child.id || '/'
                    FROM %(table)s child
                    JOIN subtree ON child.%(parent)s = subtree.id
                    WHERE strpos('/' || subtree.path, '/' || child.id || '/') = 0
                )
                UPDATE %(table)s node
                SET parent_path = rebuilt.path
                FROM (
                    SELECT DISTINCT ON (id) id, path
                    FROM (
                        SELECT id, path FROM healed
                        UNION ALL
                        SELECT id, path FROM subtree
                    ) every_path
                ) rebuilt
                WHERE node.id = rebuilt.id
                RETURNING node.id, node.parent_path """,
                table=SQL.identifier(model._table),
                parent=SQL.identifier(model._parent_name),
                ids=ids,
            )
        )
        _debug.logic(
            "backend.parent_path.rebuilt",
            model=model._name,
            nodes=len(ids),
            rows=len(rows),
        )
        return dict(rows)
