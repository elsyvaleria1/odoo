from __future__ import annotations

import logging
import typing

from odoo.libs.accel import fast_clone
from odoo.libs.debug_log import DebugLog
from odoo.tools import Query

from ._backend_memory_query import _InMemoryQuery, _is_whole_table
from .backend import _get_column_read_value, _unwrap_json

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..components.storage import DictBackend
    from ..fields import Field
    from ..models.base import BaseModel
    from .environment import Environment

_debug = DebugLog("odoo.orm.runtime._backend_memory")


_logger = logging.getLogger("odoo.orm.backend")


class _InMemoryReadMixin:
    __slots__ = ()

    if typing.TYPE_CHECKING:
        storage: DictBackend

    def fetch(
        self,
        model: ModelLike,
        query: Query,
        column_fields: typing.Iterable[Field[typing.Any]],
        other_fields: typing.Iterable[Field[typing.Any]],
    ) -> ModelLike:
        column_fields = list(column_fields)
        if isinstance(query, _InMemoryQuery):
            result_ids = query.get_result_ids()
        elif query._ids is not None:
            result_ids = query._ids
        elif _is_whole_table(query):
            whole = _InMemoryQuery(
                model, self.storage, self.storage.get_table_ids(model._table)
            )
            whole.order = query.order
            whole.offset = query.offset
            whole.limit = query.limit
            result_ids = whole.get_result_ids()
            _debug.logic(
                "backend.memory.fetch_whole_table",
                model=model._name,
                rows=len(result_ids),
            )
        else:
            raise NotImplementedError(
                f"InMemoryBackend.fetch on {model._name}: a query built in SQL "
                f"cannot be evaluated in memory ({query}); use a DB-backed "
                "TransactionCase"
            )
        if column_fields:
            existing = self.storage.get_existing_ids(model._table, list(result_ids))
            result_ids = tuple(id_ for id_ in result_ids if id_ in existing)

        if not result_ids:
            _debug.logic("backend.memory.fetch_nothing", model=model._name)
            return model.browse()

        fetched = model.browse(result_ids)
        context = model.env.context
        flushed = [
            field
            for field in column_fields
            if field.translate
            or (
                field.is_binary
                and (context.get("bin_size") or context.get("bin_size_" + field.name))
            )
        ]
        if flushed:
            fetched._flush_if_dirty(flushed)
        self._load_column_cache(model, result_ids, column_fields, fetched)

        if fetched:
            for field in other_fields:
                field.read(typing.cast("BaseModel", fetched))
        return fetched

    def _load_column_cache(
        self,
        model: ModelLike,
        record_ids: typing.Sequence[int],
        column_fields: list[Field[typing.Any]],
        records: ModelLike,
    ) -> None:
        if not column_fields:
            return
        env = model.env
        _fdc = env._field_depends_context
        field_caches: dict[
            Field[typing.Any], typing.MutableMapping[typing.Any, typing.Any]
        ] = {}
        for field in column_fields:
            if field not in _fdc:
                field_caches[field] = env.core.get_field_data(field)
            else:
                try:
                    field_caches[field] = field._get_cache(env)
                except (KeyError, AttributeError, TypeError) as e:
                    _logger.debug(
                        "DictBackend cache load skipped %s.%s: %s",
                        model._name,
                        field.name,
                        e,
                    )
                    field_caches[field] = env.core.get_field_data(field)
        prefetch_langs = bool(env.context.get("prefetch_langs"))
        for field in column_fields:
            if field.is_stored_computed:
                field._clear_dead_pending(records)
        rows = {
            record_id: row
            for record_id in record_ids
            if (row := self.storage.get_row(model._table, record_id)) is not None
        }
        if not rows:
            return
        core = env.core
        for field in column_fields:
            cells = self._get_column_cells(env, field, rows)
            if field.translate and prefetch_langs:
                for record_id, cell in cells.items():
                    field._insert_cache(
                        model.browse((record_id,)),
                        [_unwrap_json(cell)],
                    )
                continue
            ids, values = [], []
            for record_id, cell in cells.items():
                value = _get_column_read_value(field, cell, env)
                if value is None:
                    pass
                elif field.type == "json":
                    value = fast_clone(value)
                elif not (field.is_binary and isinstance(value, str)):
                    value = field.convert_to_cache(value, records, validate=False)
                ids.append(record_id)
                values.append(value)
            if field.is_stored_computed:
                members = (field, *field.tree_siblings)
                if any(core.has_pending_field(member) for member in members):
                    keep = [
                        index
                        for index, record_id in enumerate(ids)
                        if not core.is_pending_in_tree(field, record_id)
                    ]
                    ids = [ids[index] for index in keep]
                    values = [values[index] for index in keep]
            if not ids:
                continue
            try:
                field._insert_cache(model.browse(tuple(ids)), values)
            except (KeyError, AttributeError, TypeError) as e:
                _logger.debug(
                    "DictBackend cache insert fell back for %s.%s: %s",
                    model._name,
                    field.name,
                    e,
                )
                field_cache = field_caches[field]
                for record_id, value in zip(ids, values, strict=True):
                    field_cache.setdefault(record_id, value)

    def _get_column_cells(
        self,
        env: Environment,
        field: Field[typing.Any],
        rows: dict[int, dict[str, typing.Any]],
    ) -> dict[int, typing.Any]:
        if field.store:
            return {record_id: row.get(field.name) for record_id, row in rows.items()}
        *keys, target = field._related_field_seq
        cells = {}
        for record_id, row in rows.items():
            parent_row: dict[str, typing.Any] | None = row
            for key in keys:
                parent_id = parent_row.get(key.name) if parent_row else None
                parent_row = (
                    self.storage.get_row(env[key.comodel_name]._table, parent_id)
                    if parent_id
                    else None
                )
            cell = parent_row.get(target.name) if parent_row else None
            cells[record_id] = (
                _get_column_read_value(target, cell, env)
                if target.company_dependent
                else cell
            )
        return cells

    def get_existing_ids(self, model: ModelLike, ids: typing.Iterable[int]) -> set[int]:
        return set(self.storage.get_existing_ids(model._table, list(ids)))

    def has_rows_beyond(self, model: ModelLike, count: int) -> bool:
        return self.storage.get_row_count(model._table) > count
