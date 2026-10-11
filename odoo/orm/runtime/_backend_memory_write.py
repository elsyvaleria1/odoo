from __future__ import annotations

import typing

from odoo.exceptions import LockError, UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.iteration import partition

from ..primitives import MODULE_UNINSTALL_FLAG, NewId
from ._backend_memory_constraints import _check_table_constraints, _ForeignKeyPlan
from .backend import PostgresBackend, _unwrap_json

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..components.storage import DictBackend
    from ..fields import Field

_debug = DebugLog("odoo.orm.runtime._backend_memory")


class _InMemoryWriteMixin:
    __slots__ = ()

    if typing.TYPE_CHECKING:
        storage: DictBackend

    def create_rows(
        self,
        model: ModelLike,
        stored_list: list[dict[str, typing.Any]],
        columns: list[str],
        col_fields: list[Field[typing.Any]],
    ) -> list[int]:
        row_dicts: list[dict[str, typing.Any]] = []
        new_ids: list[int] = []
        for stored in stored_list:
            new_id = stored.get("id") or self.storage.allocate_next_id(model._table)
            row_dict: dict[str, typing.Any] = {"id": new_id}
            for fname, field in zip(columns, col_fields, strict=True):
                if fname in stored:
                    row_dict[fname] = _unwrap_json(
                        field.convert_to_column_insert(
                            stored[fname],
                            model,
                            stored,
                            validate=not field.column_value_is_cache,
                        )
                    )
            row_dicts.append(row_dict)
            new_ids.append(new_id)
        _check_table_constraints(self.storage, model, row_dicts)
        self.storage.put_rows(model._table, row_dicts)
        _debug.pipeline(
            "backend.memory.rows_created",
            model=model._name,
            rows=len(row_dicts),
            columns=len(columns),
        )
        return new_ids

    @staticmethod
    def _strip_company_fallbacks(
        model: ModelLike, field: Field[typing.Any], merged: dict[str, typing.Any]
    ) -> dict[str, typing.Any]:
        kept = {}
        for key, item in merged.items():
            rec = model.with_company(int(key))
            fallback = field._to_json_value(
                field.convert_to_column(
                    field._get_company_dependent_fallback_raw(rec), rec
                )
            )
            if item != fallback:
                kept[key] = item
        return kept

    def update_rows(
        self,
        model: ModelLike,
        fnames: tuple[str, ...],
        rows: list[tuple[typing.Any, ...]],
    ) -> None:
        fields_map = model._fields
        updates = []
        for row in rows:
            id_ = row[0]
            values: dict[str, typing.Any] = {}
            for fname, value in zip(fnames, row[1:], strict=True):
                value = _unwrap_json(value)
                field = fields_map.get(fname)
                if (
                    value is not None
                    and field is not None
                    and (field.translate is True or field.company_dependent)
                    and isinstance(value, dict)
                ):
                    old_row = self.storage.get_row(model._table, id_)
                    old = old_row.get(fname) if old_row else None
                    if field.translate is True and not isinstance(old, dict):
                        old = {"en_US": next(iter(value.values()))}
                    if isinstance(old, dict):
                        value = {**old, **value}
                    if field.company_dependent and isinstance(value, dict):
                        value = (
                            self._strip_company_fallbacks(model, field, value) or None
                        )
                values[fname] = value
            updates.append((id_, values))
        _check_table_constraints(
            self.storage,
            model,
            [
                {**(self.storage.get_row(model._table, id_) or {}), **values}
                for id_, values in updates
            ],
        )
        self.storage.update_rows(model._table, updates)

    def increment_columns_skip_locked(
        self, model: ModelLike, columns: typing.Sequence[str], ids: typing.Sequence[int]
    ) -> int:
        table = model._table
        updates = []
        for id_ in ids:
            row = self.storage.get_row(table, id_)
            if row is not None:
                updates.append(
                    (id_, {column: (row.get(column) or 0) + 1 for column in columns})
                )
        self.storage.update_rows(table, updates)
        return len(updates)

    def lock_for_update(
        self, model: ModelLike, *, allow_referencing: bool = False, wait: bool = False
    ) -> None:
        ids = {id_ for id_ in model._ids if id_}
        if not ids:
            return
        if len(self.storage.get_existing_ids(model._table, list(ids))) != len(ids):
            raise LockError(model.env._("Cannot grab a lock on records"))

    def try_lock_for_update(
        self,
        model: ModelLike,
        *,
        allow_referencing: bool = False,
        limit: int | None = None,
    ) -> ModelLike:
        new_ids, real = partition(lambda i: isinstance(i, NewId), model._ids)
        if limit is not None and len(new_ids) >= limit:
            return model.browse(new_ids[:limit])
        existing = self.storage.get_existing_ids(model._table, real)
        lockable_real = [
            i for i in model._ids if not isinstance(i, NewId) and i in existing
        ]
        if limit is not None:
            lockable_real = lockable_real[: limit - len(new_ids)]
        valid = set(lockable_real) | set(new_ids)
        return model.browse(i for i in model._ids if i in valid)

    def unlink_rows(self, model: ModelLike, sub_ids: tuple[int, ...]) -> None:
        env = model.env
        wanted = set(sub_ids)
        plan = _ForeignKeyPlan(self, env.registry)
        plan.add_removal(model, wanted)

        many2one_fields = env.registry.many2one_company_dependents[model._name]
        uninstalling = env.context.get(MODULE_UNINSTALL_FLAG)
        if many2one_fields and not uninstalling:
            PostgresBackend._unlink_default_guard(model, sub_ids, many2one_fields)
        clearing: list[tuple[Field[typing.Any], int, dict[str, typing.Any]]] = []
        for field in many2one_fields:
            referrer = env[field.model_name]
            doomed = plan.rows.get(referrer._table, ())
            for row_id in self.storage.get_table_ids(referrer._table):
                if row_id in doomed:
                    continue
                row = self.storage.get_row(referrer._table, row_id)
                values = row.get(field.name) if row else None
                if not isinstance(values, dict):
                    continue
                hit = {key for key, value in values.items() if value in wanted}
                if not hit:
                    continue
                if field.ondelete == "restrict" and not uninstalling:
                    raise UserError(
                        env._(
                            "You cannot delete %(to_delete_record)s, as it is used by %(on_restrict_record)s",
                            to_delete_record=model.browse(values[next(iter(hit))]),
                            on_restrict_record=referrer.browse(row_id),
                        )
                    )
                cleared = {
                    key: None if key in hit else value for key, value in values.items()
                }
                clearing.append((field, row_id, cleared))

        for field, row_id, cleared in clearing:
            self.storage.update_rows(
                env[field.model_name]._table, [(row_id, {field.name: cleared})]
            )
        plan.apply(self.storage)
        for field in {field for field, _row_id, _cleared in clearing}:
            row_ids = [r for f, r, _c in clearing if f is field]
            env[field.model_name].browse(row_ids).modified([field.name])
        env.registry.metaschema.discard_defaults(env, model.browse(sub_ids))
