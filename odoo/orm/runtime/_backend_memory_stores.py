from __future__ import annotations

import itertools
import typing
from decimal import Decimal

from psycopg.errors import UniqueViolation

from odoo.libs.debug_log import DebugLog

from ._backend_memory_constraints import _check_table_constraints
from .backend import _unwrap_json

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..components.storage import DictBackend
    from .environment import Environment

_debug = DebugLog("odoo.orm.runtime._backend_memory")


class InMemorySequenceStore:
    __slots__ = ("storage",)

    def __init__(self, storage: DictBackend) -> None:
        self.storage = storage

    def create(
        self, env: Environment | None, name: str, *, increment: int, start: int
    ) -> None:
        self.storage.create_sequence(name, increment=increment, start=start)

    def drop(self, env: Environment | None, names: typing.Collection[str]) -> None:
        self.storage.drop_sequences(names)

    def alter(
        self,
        env: Environment | None,
        name: str,
        *,
        increment: int | None = None,
        restart: int | None = None,
    ) -> None:
        self.storage.alter_sequence(name, increment=increment, restart=restart)

    def next_values(self, env: Environment | None, name: str, count: int) -> list[int]:
        return self.storage.next_sequence_values(name, count)

    def peek(
        self, env: Environment | None, names: typing.Collection[str]
    ) -> dict[str, int]:
        return self.storage.peek_sequences(names)


def _load(value: typing.Any) -> typing.Any:
    # what the cursor's loaders answer for the stored value: a numeric as a
    # float (db.lifecycle registers the loader), a json object unwrapped
    if isinstance(value, Decimal):
        return float(value)
    return _unwrap_json(value)


class InMemoryColumnStore:
    __slots__ = ("storage",)

    def __init__(self, storage: DictBackend) -> None:
        self.storage = storage

    def read(
        self, model: ModelLike, column: str, ids: typing.Collection[int]
    ) -> dict[int, typing.Any]:
        rows = self.storage.get_rows(model._table, list(ids))
        return {id_: _load(row.get(column)) for id_, row in rows.items()}

    def write(
        self,
        model: ModelLike,
        column: str,
        rows: typing.Collection[tuple[int, typing.Any]],
    ) -> None:
        self.storage.update_rows(
            model._table, [(id_, {column: _unwrap_json(value)}) for id_, value in rows]
        )

    def fetch_and_add(
        self, model: ModelLike, column: str, record_id: int, delta: int
    ) -> int | None:
        row = self.storage.get_row(model._table, record_id)
        if row is None:
            # the SQL twin unpacks the RETURNING of an UPDATE that matched
            # nothing: an absent row is an error, never a fabricated 0
            raise ValueError(f"fetch_and_add: no row {record_id} in {model._table!r}")
        value = row.get(column)
        # NULL + delta is NULL on PostgreSQL, and the raw old value returns
        new = None if value is None else value + delta
        self.storage.update_rows(model._table, [(record_id, {column: new})])
        return value

    def try_write(
        self, model: ModelLike, column: str, record_id: int, value: typing.Any
    ) -> bool:
        # a value the table refuses under a unique constraint is an answer,
        # not an error: the caller picks the next candidate (mirrors the
        # UniqueViolation catch of the PostgreSQL twin)
        row = dict(self.storage.get_row(model._table, record_id) or {})
        row["id"] = record_id
        row[column] = value
        try:
            _check_table_constraints(self.storage, model, [row])
        except UniqueViolation:
            return False
        self.storage.update_rows(model._table, [(record_id, {column: value})])
        return True

    def merge_json(
        self,
        model: ModelLike,
        column: str,
        record_id: int,
        fallback: dict[str, typing.Any],
        value: dict[str, typing.Any],
    ) -> int:
        row = self.storage.get_row(model._table, record_id)
        if row is None:
            return 0
        stored = _unwrap_json(row.get(column)) or {}
        merged = {
            key: item
            for key, item in {
                **_unwrap_json(fallback),
                **stored,
                **_unwrap_json(value),
            }.items()
            if item is not None
        }
        self.storage.update_rows(model._table, [(record_id, {column: merged or None})])
        return 1

    def get_column_values(
        self,
        model: ModelLike,
        column: str,
        *,
        containing: typing.Any = None,
        limit: int | None = None,
    ) -> list[tuple[int, typing.Any]]:
        storage = self.storage
        rows = (
            (row_id, _load(row[column]))
            for row_id in sorted(storage.get_table_ids(model._table))
            if (row := storage.get_row(model._table, row_id)) is not None
            and row.get(column) is not None
        )
        if containing is not None:
            rows = (
                (row_id, value)
                for row_id, value in rows
                if _jsonb_contains(value, containing)
            )
        return list(rows if limit is None else itertools.islice(rows, limit))


def _jsonb_contains(value: object, needle: object) -> bool:
    # PostgreSQL's jsonb @>: an object contains every key of the needle with
    # a containing value; an array contains every needle element in some
    # element; scalars must be equal
    if isinstance(needle, dict):
        return isinstance(value, dict) and all(
            key in value and _jsonb_contains(value[key], sub)
            for key, sub in needle.items()
        )
    if isinstance(needle, list):
        if not isinstance(value, list):
            return False
        return all(
            any(_jsonb_contains(element, sub) for element in value) for sub in needle
        )
    return value == needle
