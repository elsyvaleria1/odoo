from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, override

from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

type StorageSnapshot = tuple[dict[str, dict[int, dict[str, Any]]]]


@dataclass(slots=True)
class NamedSequence:
    increment: int
    last_value: int
    is_called: bool = False

    def next_values(self, count: int) -> list[int]:
        values = []
        for _ in range(count):
            if self.is_called:
                self.last_value += self.increment
            self.is_called = True
            values.append(self.last_value)
        return values

    def peek(self) -> int:
        return self.last_value + self.increment if self.is_called else self.last_value


class DictBackend:
    __slots__ = ("_children", "_named_sequences", "_roots", "_sequences", "_tables")

    def __init__(self) -> None:
        self._tables: dict[str, dict[int, dict[str, Any]]] = {}
        self._sequences: dict[str, int] = defaultdict(int)
        self._named_sequences: dict[str, NamedSequence] = {}
        self._roots: dict[str, str] = {}
        self._children: dict[str, list[str]] = defaultdict(list)

    def declare_inherits(self, table: str, root: str) -> None:
        if table == root or self._roots.get(table) == root:
            return
        self._roots[table] = root
        self._children[root].append(table)

    def _members(self, table: str) -> list[str]:
        return [table, *self._children.get(table, ())]

    def _sequence_key(self, table: str) -> str:
        return self._roots.get(table, table)

    def _find(self, table: str, id_: int) -> dict[str, Any] | None:
        for member in self._members(table):
            row = self._tables.get(member, {}).get(id_)
            if row is not None:
                return row
        return None

    def create_sequence(self, name: str, *, increment: int, start: int) -> None:
        self._named_sequences[name] = NamedSequence(increment, max(start, 1))

    def drop_sequences(self, names: Iterable[str]) -> None:
        for name in names:
            self._named_sequences.pop(name, None)

    def alter_sequence(
        self, name: str, *, increment: int | None = None, restart: int | None = None
    ) -> None:
        sequence = self._named_sequences.get(name)
        if sequence is None:
            return
        if increment is not None:
            sequence.increment = increment
        if restart is not None:
            sequence.last_value = max(restart, 1)
            sequence.is_called = False

    def next_sequence_values(self, name: str, count: int) -> list[int]:
        return self._named_sequences[name].next_values(count)

    def peek_sequences(self, names: Iterable[str]) -> dict[str, int]:
        sequences = self._named_sequences
        return {name: sequences[name].peek() for name in names if name in sequences}

    def snapshot(self) -> StorageSnapshot:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "storage.snapshot",
                tables=len(self._tables),
                rows=sum(len(rows) for rows in self._tables.values()),
                sequences=len(self._named_sequences),
            )
        return (
            {
                table: {id_: dict(row) for id_, row in rows.items()}
                for table, rows in self._tables.items()
            },
        )

    def restore(self, snapshot: StorageSnapshot) -> None:
        (tables,) = snapshot
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "storage.restore",
                tables=len(tables),
                rows=sum(len(rows) for rows in tables.values()),
                sequences=len(self._named_sequences),
            )
        self._tables = {
            table: {id_: dict(row) for id_, row in rows.items()}
            for table, rows in tables.items()
        }

    def insert_rows(
        self, table: str, columns: list[str], rows: list[tuple[Any, ...]]
    ) -> list[int]:
        tbl = self._tables.setdefault(table, {})
        key = self._sequence_key(table)
        new_ids: list[int] = []
        for row in rows:
            self._sequences[key] += 1
            id_ = self._sequences[key]
            tbl[id_] = dict(zip(columns, row, strict=True))
            new_ids.append(id_)
        return new_ids

    def put_rows(self, table: str, rows: list[dict[str, Any]]) -> None:
        tbl = self._tables.setdefault(table, {})
        key = self._sequence_key(table)
        seq = self._sequences[key]
        for row in rows:
            id_ = row["id"]
            tbl[id_] = dict(row)
            seq = max(seq, id_)
        self._sequences[key] = seq

    def update_rows(
        self, table: str, updates: list[tuple[int, dict[str, Any]]]
    ) -> None:
        for id_, values in updates:
            row = self._find(table, id_)
            if row is not None:
                row.update(values)

    def remove_rows(self, table: str, ids: list[int]) -> None:
        for member in self._members(table):
            tbl = self._tables.get(member)
            if tbl is None:
                continue
            for id_ in ids:
                tbl.pop(id_, None)

    def get_row(self, table: str, id_: int) -> dict[str, Any] | None:
        row = self._find(table, id_)
        return dict(row) if row is not None else None

    def get_rows(self, table: str, ids: list[int]) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        for id_ in ids:
            row = self._find(table, id_)
            if row is not None:
                result[id_] = dict(row)
        return result

    def get_existing_ids(self, table: str, ids: list[int]) -> set[int]:
        return {id_ for id_ in ids if self._find(table, id_) is not None}

    def get_table_ids(self, table: str) -> list[int]:
        ids: list[int] = []
        for member in self._members(table):
            ids.extend(self._tables.get(member, {}).keys())
        return ids

    def get_row_count(self, table: str) -> int:
        return sum(len(self._tables.get(m, {})) for m in self._members(table))

    def allocate_next_id(self, table: str) -> int:
        key = self._sequence_key(table)
        self._sequences[key] += 1
        return self._sequences[key]

    @override
    def __repr__(self) -> str:
        n_tables = len(self._tables)
        n_rows = sum(len(t) for t in self._tables.values())
        return f"<DictBackend tables={n_tables} rows={n_rows}>"
