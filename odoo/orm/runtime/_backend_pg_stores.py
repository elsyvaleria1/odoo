from __future__ import annotations

import typing

from psycopg import errors as pgerrors
from psycopg.types.json import Jsonb

from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.sql import SQL

if typing.TYPE_CHECKING:
    from odoo.db import Cursor

    from .._typing import ModelLike
    from .environment import Environment

_debug = DebugLog("odoo.orm.runtime.backend")


class PostgresSequenceStore:
    __slots__ = ()

    def create(
        self, env: Environment, name: str, *, increment: int, start: int
    ) -> None:
        _debug.lifecycle(
            "backend.sequence.created", name=name, increment=increment, start=start
        )
        env.cr.execute(
            SQL(
                "CREATE SEQUENCE %s INCREMENT BY %s START WITH %s",
                SQL.identifier(name),
                increment,
                max(start, 1),
            )
        )

    def drop(self, env: Environment, names: typing.Collection[str]) -> None:
        if not names:
            return
        _debug.lifecycle("backend.sequence.dropped", sequences=len(names))
        identifiers = SQL(",").join(map(SQL.identifier, names))
        env.cr.execute(SQL("DROP SEQUENCE IF EXISTS %s RESTRICT", identifiers))

    def alter(
        self,
        env: Environment,
        name: str,
        *,
        increment: int | None = None,
        restart: int | None = None,
    ) -> None:
        if increment is None and restart is None:
            return
        env.cr.execute(
            "SELECT relname FROM pg_class"
            " WHERE relkind = %s AND relname = %s"
            "   AND relnamespace = current_schema::regnamespace",
            ("S", name),
        )
        if not env.cr.fetchone():
            _debug.logic("backend.sequence.alter_missing", name=name)
            return
        _debug.lifecycle(
            "backend.sequence.altered",
            name=name,
            increment=increment,
            restart=restart,
        )
        env.cr.execute(
            SQL(
                "ALTER SEQUENCE %s%s%s",
                SQL.identifier(name),
                SQL(" INCREMENT BY %s", increment) if increment is not None else SQL(),
                SQL(" RESTART WITH %s", max(restart, 1))
                if restart is not None
                else SQL(),
            )
        )

    def next_values(self, env: Environment, name: str, count: int) -> list[int]:
        if count == 1:
            env.cr.execute("SELECT nextval(%s)", [name])
        else:
            env.cr.execute(
                "SELECT nextval(%s) FROM generate_series(1, %s)", [name, count]
            )
        return [number for (number,) in env.cr.fetchall()]

    def peek(self, env: Environment, names: typing.Collection[str]) -> dict[str, int]:
        if not names:
            return {}
        increments = dict(
            env.execute_query(
                SQL(
                    "SELECT sequencename, increment_by FROM pg_sequences"
                    " WHERE schemaname = current_schema"
                    "   AND sequencename = ANY(%s::name[])",
                    list(names),
                )
            )
        )
        if not increments:
            _debug.logic("backend.sequence.peek_none_found", requested=len(names))
            return {}
        _debug.perf.count(
            "backend.sequence.peek",
            requested=len(names),
            found=len(increments),
        )
        reads = SQL(" UNION ALL ").join(
            SQL(
                "SELECT %s AS name, last_value, is_called FROM %s",
                name,
                SQL.identifier(name),
            )
            for name in increments
        )
        return {
            name: last_value + increments[name] if is_called else last_value
            for name, last_value, is_called in env.execute_query(reads)
        }


class PostgresColumnStore:
    __slots__ = ()

    def read(
        self, model: ModelLike, column: str, ids: typing.Collection[int]
    ) -> dict[int, typing.Any]:
        if not ids:
            return {}
        rows = model.env.execute_query(
            SQL(
                "SELECT id, %s FROM %s WHERE id = ANY(%s)",
                SQL.identifier(column),
                SQL.identifier(model._table),
                list(ids),
            )
        )
        return dict(rows)

    def write(
        self,
        model: ModelLike,
        column: str,
        rows: typing.Collection[tuple[int, typing.Any]],
    ) -> None:
        if not rows:
            return
        table = SQL.identifier(model._table).code
        column_sql = SQL.identifier(column).code
        cr = typing.cast("Cursor", model.env.cr)
        cr.executemany(  # noqa: E8501 -- both names are SQL.identifier().code; executemany takes no SQL params
            f"UPDATE {table} SET {column_sql} = %s WHERE id = %s",
            [(value, id_) for id_, value in rows],
        )

    def fetch_and_add(
        self, model: ModelLike, column: str, record_id: int, delta: int
    ) -> int | None:
        table = SQL.identifier(model._table)
        column_sql = SQL.identifier(column)
        value: int | None
        [value] = model.env.execute_query(
            SQL(
                "WITH locked AS (SELECT %s AS value FROM %s WHERE id = %s FOR UPDATE NOWAIT) "
                "UPDATE %s t SET %s = t.%s + %s FROM locked WHERE t.id = %s "
                "RETURNING locked.value",
                column_sql,
                table,
                record_id,
                table,
                column_sql,
                column_sql,
                delta,
                record_id,
            )
        )[0]
        return value

    def try_write(
        self, model: ModelLike, column: str, record_id: int, value: typing.Any
    ) -> bool:
        cr = model.env.cr
        with cr.savepoint(flush=False) as savepoint:
            try:
                cr.execute(
                    SQL(
                        "UPDATE %s SET %s = %s WHERE id = %s",
                        SQL.identifier(model._table),
                        SQL.identifier(column),
                        value,
                        record_id,
                    ),
                    log_exceptions=False,
                )
            except pgerrors.ExclusionViolation, pgerrors.UniqueViolation:
                savepoint.rollback()
                return False
        return True

    def merge_json(
        self,
        model: ModelLike,
        column: str,
        record_id: int,
        fallback: dict[str, typing.Any],
        value: dict[str, typing.Any],
    ) -> int:
        cr = model.env.cr
        cr.execute(
            SQL(
                "UPDATE %(table)s SET %(column)s = NULLIF(jsonb_strip_nulls("
                "%(fallback)s || COALESCE(%(column)s, '{}'::jsonb) || %(value)s"
                "), '{}'::jsonb) WHERE id = %(id)s",
                table=SQL.identifier(model._table),
                column=SQL.identifier(column),
                fallback=Jsonb(fallback),
                value=Jsonb(value),
                id=record_id,
            )
        )
        return cr.rowcount

    def get_column_values(
        self,
        model: ModelLike,
        column: str,
        *,
        containing: typing.Any = None,
        limit: int | None = None,
    ) -> list[tuple[int, typing.Any]]:
        where = SQL("%s IS NOT NULL", SQL.identifier(column))
        if containing is not None:
            where = SQL(
                "%s AND %s @> %s::jsonb",
                where,
                SQL.identifier(column),
                json_dumps(containing),
            )
        query = SQL(
            "SELECT id, %s FROM %s WHERE %s ORDER BY id",
            SQL.identifier(column),
            SQL.identifier(model._table),
            where,
        )
        if limit is not None:
            query = SQL("%s LIMIT %s", query, limit)
        return model.env.execute_query(query)
