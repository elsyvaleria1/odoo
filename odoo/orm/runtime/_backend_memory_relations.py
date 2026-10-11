from __future__ import annotations

import typing
from collections import defaultdict

from odoo.libs.debug_log import DebugLog
from odoo.tools import Query

from ._backend_memory_constraints import _check_m2m_foreign_keys

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..components.storage import DictBackend

_debug = DebugLog("odoo.orm.runtime._backend_memory")


class _InMemoryRelationsMixin:
    __slots__ = ()

    if typing.TYPE_CHECKING:
        storage: DictBackend

    def _iter_m2m_rows(
        self, relation: str
    ) -> typing.Iterator[tuple[int, dict[str, typing.Any]]]:
        for row_id in self.storage.get_table_ids(relation):
            row = self.storage.get_row(relation, row_id)
            if row is not None:
                yield row_id, row

    def _read_m2m_pairs(
        self,
        model: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        ids: typing.Collection[int],
    ) -> list[tuple[int, int]]:
        wanted = set(ids)
        return [
            (row[column1], row[column2])
            for _row_id, row in self._iter_m2m_rows(relation)
            if row.get(column1) in wanted
        ]

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
        position = {id2: index for index, id2 in enumerate(query.get_result_ids())}
        group: dict[int, list[int]] = defaultdict(list)
        for id1, id2 in self._read_m2m_pairs(
            records, relation, column1, column2, records.ids
        ):
            if id2 in position:
                group[id1].append(id2)
        for ids2 in group.values():
            ids2.sort(key=position.__getitem__)
        return group

    def count_m2m_groups(
        self,
        records: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        query: Query,
    ) -> dict[int, int]:
        groups = self.read_m2m_groups(records, relation, column1, column2, query)
        return {id1: len(ids2) for id1, ids2 in groups.items()}

    def link_m2m_pairs(
        self,
        model: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        pairs: typing.Iterable[tuple[int, int]],
    ) -> None:
        existing: set[tuple[typing.Any, ...]] = {
            (row.get(column1), row.get(column2))
            for _row_id, row in self._iter_m2m_rows(relation)
        }
        to_insert = []
        for pair in pairs:
            key = tuple(pair)
            if key not in existing:
                existing.add(key)
                to_insert.append(key)
        if to_insert:
            _check_m2m_foreign_keys(
                self.storage, model, relation, column1, column2, to_insert
            )
            self.storage.insert_rows(relation, [column1, column2], to_insert)

    def unlink_m2m_pairs(
        self,
        model: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        pairs: typing.Iterable[tuple[int, int]],
    ) -> None:
        doomed = {tuple(pair) for pair in pairs}
        row_ids = [
            row_id
            for row_id, row in self._iter_m2m_rows(relation)
            if (row.get(column1), row.get(column2)) in doomed
        ]
        if row_ids:
            self.storage.remove_rows(relation, row_ids)
