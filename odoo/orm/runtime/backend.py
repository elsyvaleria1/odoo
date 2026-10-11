from __future__ import annotations

import logging
import typing
from decimal import Decimal

from psycopg.errors import (
    InvalidTextRepresentation,
    NumericValueOutOfRange,
    UntranslatableCharacter,
)
from psycopg.types.json import Json, Jsonb, JsonDumper

from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads
from odoo.libs.sql import SQL, pg_size_pretty
from odoo.tools import Query

from ._backend_pg_hierarchy import _PostgresHierarchyMixin
from ._backend_pg_read import _get_fetch_term, _PostgresReadMixin
from ._backend_pg_relations import _PostgresRelationsMixin
from ._backend_pg_stores import PostgresColumnStore, PostgresSequenceStore
from ._backend_pg_write import COPY_DISABLED, COPY_THRESHOLD, _PostgresWriteMixin

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..domain import Domain
    from ..fields import Field
    from .environment import Environment

__all__ = [
    "COPY_DISABLED",
    "COPY_THRESHOLD",
    "POSTGRES_BACKEND",
    "ColumnStore",
    "PostgresBackend",
    "PostgresColumnStore",
    "PostgresSequenceStore",
    "SequenceStore",
    "StorageBackend",
    "_get_column_read_value",
    "_get_fetch_term",
    "_unwrap_json",
]

_logger = logging.getLogger("odoo.orm.backend")
_debug = DebugLog(__name__)

_JSONB_MAX_INTEGER_DIGITS = 131072
_JSONB_MAX_SCALE = 16383


def _unwrap_json(value: typing.Any) -> typing.Any:
    if isinstance(value, (Json, Jsonb)):
        dumped = JsonDumper(type(value)).dump(value)
        if dumped is None:
            raise TypeError(f"{type(value).__name__} dumped to no value")
        return _get_jsonb_storage_value(
            json_loads(
                bytes(dumped),
                parse_float=Decimal,
                parse_constant=_reject_json_constant,
            )
        )
    return value


def _reject_json_constant(value: str) -> typing.NoReturn:
    raise InvalidTextRepresentation(f"Invalid JSON token: {value}")


def _get_jsonb_storage_value(value: typing.Any) -> typing.Any:
    if isinstance(value, str):
        if "\0" in value:
            raise UntranslatableCharacter("JSONB cannot store a NUL character")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise InvalidTextRepresentation("Invalid JSON Unicode surrogate") from error
    elif isinstance(value, Decimal):
        exponent = value.as_tuple().exponent
        assert isinstance(exponent, int)
        if (
            value and value.adjusted() >= _JSONB_MAX_INTEGER_DIGITS
        ) or exponent < -_JSONB_MAX_SCALE:
            raise NumericValueOutOfRange(
                "JSONB number exceeds PostgreSQL numeric range"
            )
        if exponent >= 0:
            return int(value)
        return float(value) if value else 0.0
    elif isinstance(value, list):
        return [_get_jsonb_storage_value(item) for item in value]
    elif isinstance(value, dict):
        return {
            _get_jsonb_storage_value(key): _get_jsonb_storage_value(item)
            for key, item in value.items()
        }
    return value


def _get_column_read_value(
    field: Field[typing.Any], value: typing.Any, env: Environment
) -> typing.Any:
    if field.company_dependent:
        company_key = str(env.company.id)
        if value is not None and company_key in value:
            return value[company_key]
        model = env[field.model_name]
        fallback = field.get_company_dependent_fallback(model)
        return field.convert_to_column(field.convert_to_write(fallback, model), model)
    if (
        field.translate
        and isinstance(value, dict)
        and not env.context.get("prefetch_langs")
    ):
        for lang in field.get_translation_fallback_langs(env):
            scalar = value.get(lang)
            if scalar is not None:
                return scalar
        return None
    if (
        field.is_binary
        and value is not None
        and (env.context.get("bin_size") or env.context.get("bin_size_" + field.name))
    ):
        return pg_size_pretty(len(value))
    return value


@typing.runtime_checkable
class SequenceStore(typing.Protocol):
    def create(
        self, env: Environment, name: str, *, increment: int, start: int
    ) -> None: ...

    def drop(self, env: Environment, names: typing.Collection[str]) -> None: ...

    def alter(
        self,
        env: Environment,
        name: str,
        *,
        increment: int | None = None,
        restart: int | None = None,
    ) -> None: ...

    def next_values(self, env: Environment, name: str, count: int) -> list[int]: ...

    def peek(
        self, env: Environment, names: typing.Collection[str]
    ) -> dict[str, int]: ...


@typing.runtime_checkable
class ColumnStore(typing.Protocol):
    def read(
        self, model: ModelLike, column: str, ids: typing.Collection[int]
    ) -> dict[int, typing.Any]: ...

    def write(
        self,
        model: ModelLike,
        column: str,
        rows: typing.Collection[tuple[int, typing.Any]],
    ) -> None: ...

    def fetch_and_add(
        self, model: ModelLike, column: str, record_id: int, delta: int
    ) -> int | None: ...

    def try_write(
        self, model: ModelLike, column: str, record_id: int, value: typing.Any
    ) -> bool: ...

    def merge_json(
        self,
        model: ModelLike,
        column: str,
        record_id: int,
        fallback: dict[str, typing.Any],
        value: dict[str, typing.Any],
    ) -> int: ...

    def get_column_values(
        self,
        model: ModelLike,
        column: str,
        *,
        containing: typing.Any = None,
        limit: int | None = None,
    ) -> list[tuple[int, typing.Any]]: ...


@typing.runtime_checkable
class StorageBackend(typing.Protocol):
    sequences: SequenceStore
    columns: ColumnStore

    def timezone_names(self, env: Environment) -> frozenset[str]: ...

    def create_rows(
        self,
        model: ModelLike,
        stored_list: list[dict[str, typing.Any]],
        columns: list[str],
        col_fields: list[Field[typing.Any]],
    ) -> list[int]: ...

    def update_rows(
        self,
        model: ModelLike,
        fnames: tuple[str, ...],
        rows: list[tuple[typing.Any, ...]],
    ) -> None: ...

    def fetch(
        self,
        model: ModelLike,
        query: Query,
        column_fields: typing.Iterable[Field[typing.Any]],
        other_fields: typing.Iterable[Field[typing.Any]],
    ) -> ModelLike: ...

    def search(
        self,
        model: ModelLike,
        domain: Domain,
        offset: int,
        limit: int | None,
        order: str | None,
        *,
        check_access: bool = True,
        prof: typing.Any = None,
    ) -> Query: ...

    def search_raw(
        self,
        model: ModelLike,
        domain: Domain,
        offset: int,
        limit: int | None,
        order: str | None,
        *,
        check_access: bool = True,
    ) -> Query | None: ...

    def as_query(self, model: ModelLike, ordered: bool = True) -> Query: ...

    def descendants(
        self,
        model: ModelLike,
        parent_field: str,
        root_ids: typing.Collection[int],
        *,
        domain: Domain,
        step_domain: Domain,
        same_columns: typing.Sequence[str] = (),
    ) -> Query: ...

    def ancestors(
        self,
        model: ModelLike,
        parent_field: str,
        ids: typing.Collection[int],
        *,
        flush: bool = True,
    ) -> list[tuple[int, int | None]]: ...

    def descendant_edges(
        self, model: ModelLike, parent_field: str, ids: typing.Collection[int]
    ) -> list[tuple[int, int]]: ...

    def read_group_rows(
        self,
        model: ModelLike,
        select: SQL,
        *,
        domain: Domain,
        query: Query,
        groupby: typing.Sequence[str],
        aggregates: typing.Sequence[str],
        having: typing.Any,
        order: str | None,
        limit: int | None,
        offset: int,
    ) -> list[tuple[typing.Any, ...]]: ...

    def read_grouping_sets_rows(
        self,
        model: ModelLike,
        select: SQL,
        *,
        domain: Domain,
        query: Query,
        grouping_sets: typing.Sequence[typing.Sequence[str]],
        groupby_terms: typing.Mapping[str, SQL],
        aggregates: typing.Sequence[str],
        order: str | None,
    ) -> list[tuple[typing.Any, ...]]: ...

    def get_existing_ids(
        self, model: ModelLike, ids: typing.Iterable[int]
    ) -> set[int]: ...

    def has_rows_beyond(self, model: ModelLike, count: int) -> bool: ...

    def has_cycle(
        self,
        model: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        ids: typing.Collection[int],
    ) -> bool: ...

    def increment_columns_skip_locked(
        self, model: ModelLike, columns: typing.Sequence[str], ids: typing.Sequence[int]
    ) -> int: ...

    def lock_for_update(
        self, model: ModelLike, *, allow_referencing: bool = False, wait: bool = False
    ) -> None: ...

    def try_lock_for_update(
        self,
        model: ModelLike,
        *,
        allow_referencing: bool = False,
        limit: int | None = None,
    ) -> ModelLike: ...

    def unlink_rows(self, model: ModelLike, sub_ids: tuple[int, ...]) -> None: ...

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
        ...

    def count_m2m_groups(
        self,
        records: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        query: Query,
    ) -> dict[int, int]: ...

    def set_parent_paths(
        self, model: ModelLike, ids: typing.Sequence[int]
    ) -> list[tuple[int, str]]: ...

    def records_with_parent_changed(
        self, model: ModelLike, parent_to_ids: dict[typing.Any, list[int]]
    ) -> list[int]: ...

    def move_parent_paths(
        self, model: ModelLike, ids: typing.Sequence[int], prefix: str
    ) -> dict[int, str]: ...

    def link_m2m_pairs(
        self,
        model: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        pairs: typing.Iterable[tuple[int, int]],
    ) -> None: ...

    def unlink_m2m_pairs(
        self,
        model: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        pairs: typing.Iterable[tuple[int, int]],
    ) -> None: ...


class PostgresBackend(
    _PostgresWriteMixin,
    _PostgresReadMixin,
    _PostgresHierarchyMixin,
    _PostgresRelationsMixin,
):
    sequences: SequenceStore = PostgresSequenceStore()
    columns: ColumnStore = PostgresColumnStore()

    __slots__ = ()

    def timezone_names(self, env: Environment) -> frozenset[str]:
        names = _sql_timezone_names.get(env.cr.dbname)
        if names is None:
            with _debug.perf("backend.timezones_loaded", cr=env.cr) as span:
                env.cr.execute("SELECT name FROM pg_timezone_names")
                names = frozenset(name for [name] in env.cr.fetchall())
                span.set(timezones=len(names))
            _sql_timezone_names[env.cr.dbname] = names
        return names


POSTGRES_BACKEND = PostgresBackend()


_sql_timezone_names: dict[str, frozenset[str]] = {}
