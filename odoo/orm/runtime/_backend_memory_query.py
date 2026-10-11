from __future__ import annotations

import re
import typing

from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import SQL
from odoo.tools import Query

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..components.storage import DictBackend
    from .environment import Environment

_debug = DebugLog("odoo.orm.runtime._backend_memory")


def _get_sort_key(
    index: int, rank: typing.Any, null_is_true: bool
) -> typing.Callable[[tuple[typing.Any, ...]], tuple[bool, typing.Any]]:
    def key(row: tuple[typing.Any, ...]) -> tuple[bool, typing.Any]:
        value = row[index]
        if value is not None and rank is not None:
            value = rank(value)
        if isinstance(value, list):
            value = tuple((item is None, item) for item in value)
        return (value is None if null_is_true else value is not None, value)

    return key


_ORDER_TERM = re.compile(
    r'\s*(?:COALESCE\("(?P<balias>[^"]+)"\."(?P<bcolumn>[^"]+)", FALSE\)'
    r'|"(?P<alias>[^"]+)"\."(?P<column>[^"]+)")'
    r"(?:\s+(?P<direction>ASC|DESC))?(?:\s+(?P<nulls>NULLS (?:FIRST|LAST)))?"
    r"\s*(?:,|$)"
)


def _parse_column_order(
    model: ModelLike, alias: str, order: SQL
) -> list[tuple[str, bool, bool, bool]] | None:
    code = order.code
    if order.params:
        return None
    terms = []
    position = 0
    while position < len(code):
        match = _ORDER_TERM.match(code, position)
        if match is None or match.end() == position:
            return None
        position = match.end()
        column = match["column"] or match["bcolumn"]
        if (match["alias"] or match["balias"]) != alias:
            return None
        field = model._fields.get(column)
        if column != "id" and not (
            field is not None
            and field.store
            and field.column_type
            and not field.translate
            and not field.company_dependent
        ):
            return None
        descending = match["direction"] == "DESC"
        nulls = match["nulls"]
        nulls_first = nulls == "NULLS FIRST" if nulls else descending
        terms.append((column, match["bcolumn"] is not None, descending, nulls_first))
    return terms


class _InMemoryQuery(Query):
    """A query the in-memory backend answered: it holds every matching id,
    in the order the search sorted them, so a later ORDER BY, LIMIT or
    OFFSET is applied to the whole match as the SQL query applies it. What
    narrows it in SQL (a WHERE, a join, a GROUP BY) cannot be evaluated
    here, and from then on the query refuses to answer."""

    __slots__ = ("_matched", "_model", "_storage", "_unanswerable")

    def __init__(
        self, model: ModelLike, storage: DictBackend, matched: typing.Iterable[int]
    ) -> None:
        super().__init__(model.env, model._table, model._table_sql)
        self._model = model
        self._storage = storage
        self._matched = tuple(matched)
        self._unanswerable: str | None = None
        self._ids = self._matched

    def _refuse(self, reason: str) -> None:
        if self._unanswerable is None and self._matched:
            _debug.logic(
                "backend.memory.query_unanswerable", table=self.table, reason=reason
            )
            self._unanswerable = reason
            self._ids = None

    def _invalidate_ids(self) -> None:
        self._refuse("a condition, a join or a grouping added in SQL")

    def _drop_ids(self) -> None:
        self._evaluate()

    @property
    def order(self) -> SQL | None:
        return self._order

    @order.setter
    def order(self, value: SQL | None) -> None:
        self._order = value
        self._evaluate()

    def _evaluate(self) -> None:
        if self._unanswerable is not None or not self._matched:
            return
        ids: list[int] = list(self._matched)
        if self._order:
            terms = _parse_column_order(self._model, self.table, self._order)
            if terms is None:
                self._refuse(f"ORDER BY {self._order.code}")
                return
            self._env.flush_query(self._order)
            ids = self._sorted(ids, terms)
        if self._order or self._limit is not None or self._offset:
            existing = self._storage.get_existing_ids(self._model._table, ids)
            ids = [id_ for id_ in ids if id_ in existing]
        if self._offset:
            ids = ids[self._offset :]
        if self._limit is not None:
            ids = ids[: self._limit]
        self._ids = tuple(ids)

    def _sorted(
        self, ids: list[int], terms: list[tuple[str, bool, bool, bool]]
    ) -> list[int]:
        stored = self._storage.get_rows(self._model._table, ids)
        rows: list[tuple[typing.Any, ...]] = []
        for id_ in ids:
            row = stored.get(id_) or {}
            values = []
            for column, is_boolean, _descending, _nulls_first in terms:
                value = id_ if column == "id" else row.get(column)
                values.append(False if is_boolean and value is None else value)
            rows.append((id_, *values))
        for index, (_column, _is_boolean, descending, nulls_first) in reversed(
            list(enumerate(terms, start=1))
        ):
            null_is_true = nulls_first == descending
            rows.sort(key=_get_sort_key(index, None, null_is_true), reverse=descending)
        return [row[0] for row in rows]

    def _require_answer(self) -> None:
        if self._unanswerable is not None:
            raise NotImplementedError(
                f"InMemoryBackend: a query on {self.table} was given "
                f"{self._unanswerable}, which only PostgreSQL can evaluate; "
                "use a DB-backed TransactionCase"
            )

    def get_result_ids(self, env: Environment | None = None) -> tuple[int, ...]:
        self._require_answer()
        return super().get_result_ids(env)

    def __len__(self) -> int:
        self._require_answer()
        return super().__len__()

    def count_matching(self, limit: int | None = None) -> int:
        self._require_answer()
        count = len(self._matched)
        return count if limit is None else min(count, limit)


def _is_whole_table(query: Query) -> bool:
    return not (
        query._where_clauses
        or query._joins
        or query._once
        or query._once_sets
        or len(query._tables) > 1
        or query.groupby
        or query.having
        or query._empty_by_construction
    )
