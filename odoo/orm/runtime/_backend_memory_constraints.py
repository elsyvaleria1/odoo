from __future__ import annotations

import re
import typing
from collections import defaultdict

from psycopg.errors import (
    CheckViolation,
    DataError,
    ForeignKeyViolation,
    NotNullViolation,
    NumericValueOutOfRange,
    UniqueViolation,
)

from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import INT4_MAX, INT4_MIN, INT8_MAX, INT8_MIN, get_index_name

from ..models.table_objects import Constraint
from ._check_constraints import violates_check

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..components.storage import DictBackend

_debug = DebugLog("odoo.orm.runtime._backend_memory")


_UNIQUE_DEFINITION = re.compile(r"^\s*unique\s*\(([^)]*)\)\s*$", re.IGNORECASE)


def _foreign_key_targets(model: ModelLike) -> list[tuple[str, str]]:
    if not model._is_an_ordinary_table():
        return []
    targets = []
    for field in model._fields.values():
        if not (field.is_many2one and field.store and field.column_type):
            continue
        if field.company_dependent or field.comodel_name not in model.env.registry:
            continue
        comodel = model.env[field.comodel_name]
        if not comodel._is_an_ordinary_table() or not comodel._auto:
            continue
        if comodel._is_table_inheritance_root():
            continue
        targets.append((field.name, comodel._table))
    return targets


def _check_foreign_keys(
    storage: DictBackend, model: ModelLike, rows: list[dict[str, typing.Any]]
) -> None:
    for column, table in _foreign_key_targets(model):
        for row in rows:
            value = row.get(column)
            if type(value) is not int:
                continue
            if not storage.get_existing_ids(table, [value]):
                _debug.logic(
                    "backend.memory.foreign_key_violated",
                    model=model._name,
                    column=column,
                    table=table,
                    value=value,
                )
                raise ForeignKeyViolation(
                    f"insert or update on table {model._table!r} violates "
                    f"foreign key constraint on column {column!r}: "
                    f"key ({column})=({value}) is not present in table {table!r}"
                )


def _check_m2m_foreign_keys(
    storage: DictBackend,
    model: ModelLike,
    relation: str,
    column1: str,
    column2: str,
    pairs: typing.Iterable[tuple[int, ...]],
) -> None:
    field = next(
        (
            candidate
            for candidate in model._fields.values()
            if candidate.is_many2many
            and candidate.store
            and candidate.relation == relation
            and candidate.column1 == column1
            and candidate.column2 == column2
        ),
        None,
    )
    if field is None or field.comodel_name not in model.env.registry:
        return
    comodel = model.env[field.comodel_name]
    if not comodel._is_an_ordinary_table() or comodel._is_table_inheritance_root():
        return
    wanted = {pair[1] for pair in pairs if type(pair[1]) is int}
    missing = wanted - storage.get_existing_ids(comodel._table, list(wanted))
    if missing:
        _debug.logic(
            "backend.memory.foreign_key_violated",
            model=model._name,
            column=f"{relation}.{column2}",
            table=comodel._table,
            value=min(missing),
        )
        raise ForeignKeyViolation(
            f"insert or update on table {relation!r} violates foreign key "
            f"constraint on column {column2!r}: key ({column2})="
            f"({min(missing)}) is not present in table {comodel._table!r}"
        )


_INTEGER_BOUNDS = {"int4": (INT4_MIN, INT4_MAX), "int8": (INT8_MIN, INT8_MAX)}


def _check_column_values(model: ModelLike, rows: list[dict[str, typing.Any]]) -> None:
    for field in model._fields.values():
        if not field.store or not field.column_type:
            continue
        kind = field.column_type[0]
        if kind in _INTEGER_BOUNDS:
            low, high = _INTEGER_BOUNDS[kind]
            for row in rows:
                value = row.get(field.name)
                if type(value) is int and not low <= value <= high:
                    raise NumericValueOutOfRange(
                        "integer out of range"
                        if kind == "int4"
                        else "bigint out of range"
                    )
        elif kind in ("varchar", "text"):
            for row in rows:
                value = row.get(field.name)
                if isinstance(value, str) and "\0" in value:
                    raise DataError(
                        "PostgreSQL text fields cannot contain NUL (0x00) bytes"
                    )


def _check_table_constraints(
    storage: DictBackend, model: ModelLike, rows: list[dict[str, typing.Any]]
) -> None:
    _check_column_values(model, rows)
    registry = model.env.registry
    not_null = [
        field.name
        for field in model._fields.values()
        if field.name != "id" and field in registry.not_null_fields
    ]
    for row in rows:
        for name in not_null:
            if name in row and row[name] is None:
                raise NotNullViolation(
                    f'null value in column "{name}" of relation '
                    f'"{model._table}" violates not-null constraint'
                )
    _check_foreign_keys(storage, model, rows)
    checks = [
        (obj.get_full_name(model), definition)
        for obj in model._table_objects.values()
        if isinstance(obj, Constraint)
        and (definition := obj.get_definition(registry))
        and definition.strip().upper().startswith("CHECK")
    ]
    for conname, definition in checks:
        for row in rows:
            stored = storage.get_row(model._table, row["id"]) if "id" in row else None
            candidate = {**(stored or {}), **row}
            if violates_check(definition, candidate):
                raise CheckViolation(
                    f'new row for relation "{model._table}" violates check '
                    f'constraint "{conname}"'
                )
    uniques = [
        (obj.get_full_name(model), tuple(c.strip() for c in match[1].split(",")))
        for obj in model._table_objects.values()
        if isinstance(obj, Constraint)
        and (match := _UNIQUE_DEFINITION.match(obj.get_definition(registry)))
    ]
    uniques += [
        (get_index_name(model._table, field.name), (field.name,))
        for field in model._fields.values()
        if field.index == "unique"
        and field.store
        and field.column_type
        and not field.translate
    ]
    if not uniques:
        return
    existing = storage.get_rows(model._table, storage.get_table_ids(model._table))
    for conname, columns in uniques:
        rewritten = {
            row.get("id") for row in rows if all(column in row for column in columns)
        }
        holders: defaultdict[tuple[typing.Any, ...], set[int]] = defaultdict(set)
        for row_id, stored in existing.items():
            if row_id in rewritten:
                continue
            stored_key = tuple(stored.get(column) for column in columns)
            if None not in stored_key:
                holders[stored_key].add(row_id)
        seen: set[tuple[typing.Any, ...]] = set()
        for row in rows:
            if not all(column in row for column in columns):
                continue
            key = tuple(row.get(column) for column in columns)
            if any(value is None for value in key):
                continue
            if key in seen or key in holders:
                raise UniqueViolation(
                    f'duplicate key value violates unique constraint "{conname}"'
                )
            seen.add(key)


class _ForeignKeyPlan:
    __slots__ = ("backend", "m2m_rows", "nulls", "registry", "rows")

    def __init__(self, backend: typing.Any, registry: typing.Any) -> None:
        self.backend = backend
        self.registry = registry
        self.rows: dict[str, set[int]] = {}
        self.nulls: dict[str, list[tuple[int, dict[str, typing.Any]]]] = {}
        self.m2m_rows: dict[str, set[int]] = {}

    def add_removal(self, model: ModelLike, ids: set[int]) -> None:
        storage = self.backend.storage
        seen = self.rows.setdefault(model._table, set())
        ids = ids.difference(seen)
        if not ids:
            return
        seen.update(ids)
        for field in model._fields.values():
            if field.is_many2many and field.store and field.relation and field.column1:
                self._add_relation_removal(field.relation, field.column1, ids)
        for field in self.registry.fields_by_comodel.get(model._name, ()):
            if not field.store:
                continue
            if field.is_many2many:
                if field.relation and field.column2:
                    self._add_relation_removal(field.relation, field.column2, ids)
                continue
            if not field.is_many2one or field.company_dependent:
                continue
            referrer = model.env[field.model_name]
            if referrer._abstract or not referrer._table:
                continue
            table = referrer._table
            hit = [
                row_id
                for row_id in storage.get_table_ids(table)
                if (row := storage.get_row(table, row_id))
                and row.get(field.name) in ids
                and row_id not in self.rows.get(table, ())
            ]
            if not hit:
                continue
            _debug.logic(
                "backend.memory.foreign_key",
                model=model._name,
                referrer=f"{field.model_name}.{field.name}",
                action=field.ondelete,
                rows=len(hit),
            )
            if field.ondelete == "cascade":
                self.add_removal(referrer, set(hit))
            elif field.ondelete == "restrict":
                raise ForeignKeyViolation(
                    f"update or delete on table {model._table!r} violates foreign "
                    f"key constraint on table {table!r}: key still referenced by "
                    f"{field.model_name}.{field.name}"
                )
            else:
                self.nulls.setdefault(table, []).extend(
                    (row_id, {field.name: None}) for row_id in hit
                )

    def _add_relation_removal(self, relation: str, column: str, ids: set[int]) -> None:
        self.m2m_rows.setdefault(relation, set()).update(
            row_id
            for row_id, row in self.backend._iter_m2m_rows(relation)
            if row.get(column) in ids
        )

    def apply(self, storage: DictBackend) -> None:
        for table, updates in self.nulls.items():
            storage.update_rows(table, updates)
        for relation, row_ids in self.m2m_rows.items():
            storage.remove_rows(relation, list(row_ids))
        for table, ids in self.rows.items():
            storage.remove_rows(table, list(ids))
