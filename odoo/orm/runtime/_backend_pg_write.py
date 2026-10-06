from __future__ import annotations

import logging
import os
import typing
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from itertools import batched

from odoo.exceptions import LockError, UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.iteration import partition
from odoo.libs.sql import SQL
from odoo.tools import Query

from ..primitives import (
    INSERT_BATCH_SIZE,
    MODULE_UNINSTALL_FLAG,
    SQL_DEFAULT,
    UPDATE_BATCH_SIZE,
    NewId,
)
from ..profiling import _OrmProfile

if typing.TYPE_CHECKING:
    from odoo.db import Cursor

    from .._typing import ModelLike
    from ..fields import Field
    from ..models.base import BaseModel

_debug = DebugLog("odoo.orm.runtime.backend")


_orm_crud = logging.getLogger("odoo.orm.crud")


COPY_THRESHOLD = int(os.environ.get("ODOO_COPY_THRESHOLD", "50"))
COPY_DISABLED = os.environ.get("ODOO_DISABLE_COPY", "").lower() in (
    "1",
    "true",
    "yes",
)

_UNIFORM_UPDATE_TYPES = (
    type(None),
    bool,
    bytes,
    date,
    datetime,
    Decimal,
    float,
    int,
    str,
)


class _PostgresWriteMixin:
    __slots__ = ()

    if typing.TYPE_CHECKING:

        def as_query(self, model: ModelLike, ordered: bool = True) -> Query: ...

    def create_rows(
        self,
        model: ModelLike,
        stored_list: list[dict[str, typing.Any]],
        columns: list[str],
        col_fields: list[Field[typing.Any]],
    ) -> list[int]:
        cr = typing.cast("Cursor", model.env.cr)
        ids: list[int] = []
        use_copy = (
            not COPY_DISABLED and col_fields and len(stored_list) >= COPY_THRESHOLD
        )
        _debug.logic(
            "backend.create_rows.strategy",
            model=model._name,
            strategy="copy" if use_copy else "insert",
            rows=len(stored_list),
            columns=len(columns),
            in_pipeline=cr.in_pipeline,
        )
        subprof = _OrmProfile(_orm_crud)

        if use_copy:
            copy_rows = self._prepare_insert_rows(
                model, stored_list, columns, col_fields
            )
            batch_ids = cr.copy_from(
                model._table,
                columns,
                copy_rows,
                returning_ids=True,
                binary=True,
            )
            ids.extend(batch_ids or ())
            subprof.stop()
            subprof.report(
                _orm_crud,
                "_create %s: %d records via COPY (%d columns)",
                model._name,
                len(stored_list),
                len(columns),
            )
        else:
            if col_fields:
                rows: list[tuple[typing.Any, ...]] = self._prepare_insert_rows(
                    model, stored_list, columns, col_fields
                )
            else:
                columns = ["id"]
                rows = [(SQL_DEFAULT,) for _ in stored_list]

            # an INSERT carries its values as bind parameters, so it goes in
            # batches; COPY above streams them all
            for batch in batched(rows, INSERT_BATCH_SIZE, strict=False):
                cr.execute(
                    SQL(
                        'INSERT INTO %s (%s) VALUES %s RETURNING "id"',
                        SQL.identifier(model._table),
                        SQL(", ").join(map(SQL.identifier, columns)),
                        SQL(", ").join(
                            SQL("(%s)", SQL(", ").join(row)) for row in batch
                        ),
                    )
                )
                ids.extend(id_ for (id_,) in cr.fetchall())
            subprof.stop()
            subprof.report(
                _orm_crud,
                "_create %s: %d records via INSERT (%d columns)",
                model._name,
                len(stored_list),
                len(columns),
            )
        return ids

    @staticmethod
    def _prepare_insert_rows(
        model: ModelLike,
        stored_list: list[dict[str, typing.Any]],
        columns: list[str],
        col_fields: list[Field[typing.Any]],
    ) -> list[tuple[typing.Any, ...]]:
        return [
            tuple(
                field.convert_to_column_insert(
                    stored[fname],
                    model,
                    stored,
                    validate=not field.column_value_is_cache,
                )
                if fname in stored
                else None
                for fname, field in zip(columns, col_fields, strict=True)
            )
            for stored in stored_list
        ]

    def update_rows(
        self,
        model: ModelLike,
        fnames: tuple[str, ...],
        rows: list[tuple[typing.Any, ...]],
    ) -> None:
        if (values := self._resolve_uniform_update_values(rows)) is not None:
            _debug.logic(
                "backend.update_rows.strategy",
                model=model._name,
                strategy="uniform",
                rows=len(rows),
                columns=len(fnames),
            )
            self._update_rows_uniform(model, fnames, [row[0] for row in rows], values)
            return
        _debug.logic(
            "backend.update_rows.strategy",
            model=model._name,
            strategy="values",
            rows=len(rows),
            columns=len(fnames),
            batches=-(-len(rows) // UPDATE_BATCH_SIZE),
        )
        for sub_rows in batched(rows, UPDATE_BATCH_SIZE, strict=False):
            self._update_rows_values(model, fnames, sub_rows)

    @staticmethod
    def _resolve_uniform_update_values(
        rows: list[tuple[typing.Any, ...]],
    ) -> tuple[typing.Any, ...] | None:
        if len(rows) < 2:
            return None
        values = rows[0][1:]
        if not all(isinstance(value, _UNIFORM_UPDATE_TYPES) for value in values):
            _debug.logic(
                "backend.update_rows.uniform_rejected",
                rows=len(rows),
                reason="value_type",
            )
            return None
        if any(row[1:] != values for row in rows):
            _debug.logic(
                "backend.update_rows.uniform_rejected",
                rows=len(rows),
                reason="values_differ",
            )
            return None
        return values

    @staticmethod
    def _update_assignments(
        model: ModelLike,
        fnames: tuple[str, ...],
        value_sql: Callable[[int, str, SQL, SQL], SQL],
    ) -> tuple[list[SQL], list[SQL]]:
        columns = []
        assignments = []
        for index, fname in enumerate(fnames):
            field = model._fields[fname]
            column_type = field.column_type
            if not field.is_column or column_type is None:
                raise RuntimeError(
                    f"_execute_update: {field} is not a stored column field"
                )
            column = SQL.identifier(fname)
            cast = SQL(column_type[1])  # noqa: E8501  from the field declaration
            expr = value_sql(index, fname, column, cast)
            if field.translate is True:
                _debug.logic(
                    "backend.update_rows.translated_merge",
                    model=model._name,
                    field=fname,
                )
                expr = SQL(
                    """CASE WHEN %(expr)s IS NULL THEN NULL ELSE
                        COALESCE(%(table)s.%(column)s, jsonb_build_object(
                            'en_US', jsonb_path_query_first(%(expr)s, '$.*')
                        )) || %(expr)s
                    END""",
                    table=SQL.identifier(model._table),
                    column=column,
                    expr=expr,
                )
            if field.company_dependent:
                fallbacks = model.env.registry.metaschema.field_column_fallbacks(
                    model.env, model._name, fname
                )
                _debug.logic(
                    "backend.update_rows.company_dependent_merge",
                    model=model._name,
                    field=fname,
                )
                expr = SQL(
                    """(SELECT jsonb_object_agg(d.key, d.value)
                    FROM jsonb_each(COALESCE(%(table)s.%(column)s, '{}'::jsonb) || %(expr)s) d
                    JOIN jsonb_each(%(fallbacks)s) f
                    ON d.key = f.key AND d.value != f.value)""",
                    table=SQL.identifier(model._table),
                    column=column,
                    expr=expr,
                    fallbacks=fallbacks,
                )
            columns.append(column)
            assignments.append(SQL("%s = %s", column, expr))
        return columns, assignments

    def _update_rows_values(
        self,
        model: ModelLike,
        fnames: tuple[str, ...],
        rows: tuple[tuple[typing.Any, ...], ...] | list[tuple[typing.Any, ...]],
    ) -> None:
        columns, assignments = self._update_assignments(
            model,
            fnames,
            lambda _index, _fname, column, cast: SQL('"__tmp".%s::%s', column, cast),
        )
        model.env.cr.execute(
            SQL(
                """ UPDATE %(table)s
                SET %(assignments)s
                FROM (VALUES %(values)s) AS "__tmp"("id", %(columns)s)
                WHERE %(table)s."id" = "__tmp"."id"
            """,
                table=SQL.identifier(model._table),
                assignments=SQL(", ").join(assignments),
                values=SQL(", ").join(rows),
                columns=SQL(", ").join(columns),
            )
        )

    def _update_rows_uniform(
        self,
        model: ModelLike,
        fnames: tuple[str, ...],
        ids: list[int],
        values: tuple[typing.Any, ...],
    ) -> None:
        _columns, assignments = self._update_assignments(
            model,
            fnames,
            lambda index, _fname, _column, cast: SQL("%s::%s", values[index], cast),
        )
        model.env.cr.execute(
            SQL(
                """UPDATE %(table)s SET %(assignments)s WHERE "id" = ANY(%(ids)s)""",
                table=SQL.identifier(model._table),
                assignments=SQL(", ").join(assignments),
                ids=ids,
            )
        )

    def increment_columns_skip_locked(
        self, model: ModelLike, columns: typing.Sequence[str], ids: typing.Sequence[int]
    ) -> int:
        cr = model.env.cr
        table = SQL.identifier(model._table)
        cr.execute(
            SQL(
                """
            UPDATE %s
               SET %s
             WHERE id IN (SELECT id FROM %s WHERE id = ANY(%s) FOR UPDATE SKIP LOCKED)
            """,
                table,
                SQL(", ").join(
                    SQL(
                        "%s = COALESCE(%s, 0) + 1",
                        SQL.identifier(column),
                        SQL.identifier(column),
                    )
                    for column in columns
                ),
                table,
                list(ids),
            )
        )
        return cr.rowcount

    @staticmethod
    def _lock_clause(allow_referencing: bool, wait: bool = False) -> SQL:
        strength = SQL("FOR NO KEY UPDATE") if allow_referencing else SQL("FOR UPDATE")
        return strength if wait else SQL("%s SKIP LOCKED", strength)

    def lock_for_update(
        self, model: ModelLike, *, allow_referencing: bool = False, wait: bool = False
    ) -> None:
        ids = {id_ for id_ in model._ids if id_}
        if not ids:
            return
        query = Query(model.env, model._table, model._table_sql)
        query.add_where(
            SQL("%s = ANY(%s)", SQL.identifier(model._table, "id"), list(ids))
        )
        if wait:
            # two writers queueing on the same rows take them in one order
            query.order = SQL.identifier(model._table, "id")
        sql = SQL("%s %s", query.select(), self._lock_clause(allow_referencing, wait))
        rows = model.env.execute_query(sql)
        if len(rows) != len(ids):
            _debug.logic(
                "backend.lock_for_update.contended",
                model=model._name,
                requested=len(ids),
                locked=len(rows),
                allow_referencing=allow_referencing,
            )
            raise LockError(model.env._("Cannot grab a lock on records"))

    def try_lock_for_update(
        self,
        model: ModelLike,
        *,
        allow_referencing: bool = False,
        limit: int | None = None,
    ) -> ModelLike:
        new_ids, ids = partition(lambda i: isinstance(i, NewId), model._ids)
        if limit is not None and len(new_ids) >= limit:
            return model.browse(new_ids[:limit])
        if not ids:
            return model
        if limit is not None:
            query = self.as_query(model.browse(ids), ordered=True)
            query.limit = limit - len(new_ids)
        else:
            query = Query(model.env, model._table, model._table_sql)
            query.add_where(
                SQL("%s = ANY(%s)", SQL.identifier(model._table, "id"), list(ids))
            )
        sql = SQL("%s %s", query.select(), self._lock_clause(allow_referencing))
        real_ids = (id_ for [id_] in model.env.execute_query(sql))
        valid_ids = {*real_ids, *new_ids}
        _debug.perf.count(
            "backend.try_lock_for_update",
            model=model._name,
            requested=len(ids),
            locked=len(valid_ids) - len(new_ids),
            limit=limit,
        )
        return model.browse(i for i in model._ids if i in valid_ids)

    def unlink_rows(self, model: ModelLike, sub_ids: tuple[int, ...]) -> None:
        env = model.env
        cr = env.cr
        records = model.browse(sub_ids)
        if not all(isinstance(id_, int) and id_ > 0 for id_ in sub_ids):
            raise TypeError(
                f"unlink_rows: sub_ids must be positive ints, got {sub_ids!r}"
            )

        cr.execute(
            SQL(
                "DELETE FROM %s WHERE id = ANY(%s)",
                SQL.identifier(model._table),
                list(sub_ids),
            )
        )

        many2one_fields = env.registry.many2one_company_dependents[model._name]
        uninstalling = env.context.get(MODULE_UNINSTALL_FLAG)
        _debug.pipeline(
            "backend.unlink_rows",
            model=model._name,
            rows=len(sub_ids),
            company_dependent_referrers=len(many2one_fields),
            uninstalling=bool(uninstalling),
        )
        if many2one_fields and not uninstalling:
            self._unlink_default_guard(model, sub_ids, many2one_fields)

        for field in many2one_fields:
            referrer = env[field.model_name]
            if field.ondelete == "restrict" and not uninstalling:
                self._unlink_restrict_guard(model, referrer, field, sub_ids)
            else:
                self._unlink_clear_company_dependent(referrer, field, sub_ids)

        env.registry.metaschema.discard_defaults(env, records)

    @staticmethod
    def _unlink_default_guard(
        model: ModelLike, sub_ids: tuple[int, ...], many2one_fields: typing.Any
    ) -> None:
        referencing = model.env.registry.metaschema.default_referencing(
            model.env, many2one_fields, sub_ids
        )
        if referencing is None:
            return
        field, record_id = referencing
        record = model.browse(record_id)
        _debug.logic(
            "backend.unlink.blocked_by_default",
            model=model._name,
            field=f"{field.model_name}.{field.name}",
            record=record.id,
        )
        raise UserError(
            model.env._(
                "Unable to delete %(record)s because it is used as the default value of %(field)s",
                record=record,
                field=field,
            )
        )

    @staticmethod
    def _unlink_restrict_guard(
        model: ModelLike,
        referrer: BaseModel,
        field: Field[typing.Any],
        sub_ids: tuple[int, ...],
    ) -> None:
        if res := model.env.execute_query(
            SQL(
                """
            SELECT id, %(field)s
            FROM %(table)s
            WHERE %(field)s IS NOT NULL
            AND %(field)s @? %(jsonpath)s
            ORDER BY id
            LIMIT 1
            """,
                table=SQL.identifier(referrer._table),
                field=SQL.identifier(field.name),
                jsonpath=f"$.* ? ({' || '.join(f'@ == {id_}' for id_ in sub_ids)})",
            )
        ):
            on_restrict_id, field_json = res[0]
            to_delete_id = next(v for v in field_json.values() if v in sub_ids)
            on_restrict_record = referrer.browse(on_restrict_id)
            to_delete_record = model.browse(to_delete_id)
            _debug.logic(
                "backend.unlink.blocked_by_restrict",
                model=model._name,
                referrer=referrer._name,
                field=field.name,
                record=to_delete_id,
            )
            raise UserError(
                model.env._(
                    "You cannot delete %(to_delete_record)s, as it is used by %(on_restrict_record)s",
                    to_delete_record=to_delete_record,
                    on_restrict_record=on_restrict_record,
                )
            )

    @staticmethod
    def _unlink_clear_company_dependent(
        referrer: BaseModel, field: Field[typing.Any], sub_ids: tuple[int, ...]
    ) -> None:
        affected = referrer.env.execute_query(
            SQL(
                """
            UPDATE %(table)s
            SET %(field)s = (
                SELECT jsonb_object_agg(
                    key,
                    CASE
                        WHEN value::int4 = ANY(%(ids)s) THEN NULL
                        ELSE value::int4
                    END)
                FROM jsonb_each_text(%(field)s)
            )
            WHERE %(field)s IS NOT NULL
            AND %(field)s @? %(jsonpath)s
            RETURNING id
            """,
                table=SQL.identifier(referrer._table),
                field=SQL.identifier(field.name),
                ids=list(sub_ids),
                jsonpath=f"$.* ? ({' || '.join(f'@ == {id_}' for id_ in sub_ids)})",
            )
        )
        if affected:
            _debug.logic(
                "backend.unlink.company_dependent_cleared",
                model=referrer._name,
                field=field.name,
                affected=len(affected),
            )
            affected_recs = referrer.browse(row[0] for row in affected)
            affected_recs.modified([field.name])
