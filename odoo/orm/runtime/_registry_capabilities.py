import threading
import typing
from contextlib import closing
from dataclasses import dataclass
from functools import partial

from psycopg import sql as psycopg_sql

from odoo.db import FunctionStatus, get_unaccent_status, has_trigram
from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import SQL

from ._registry_stubs import _RegistryStubs

_debug = DebugLog(__name__)

if typing.TYPE_CHECKING:
    from odoo.db import BaseCursor

    from .environment import Environment


class _Unaccent(typing.Protocol):
    @typing.overload
    def __call__(self, x: SQL) -> SQL: ...
    @typing.overload
    def __call__(self, x: str) -> str: ...
    @typing.overload
    def __call__(self, x: psycopg_sql.Composable) -> psycopg_sql.Composed: ...


@typing.overload
def _unaccent(x: SQL) -> SQL: ...
@typing.overload
def _unaccent(x: str) -> str: ...
@typing.overload
def _unaccent(x: psycopg_sql.Composable) -> psycopg_sql.Composed: ...
def _unaccent(
    x: SQL | str | psycopg_sql.Composable,
) -> SQL | str | psycopg_sql.Composed:
    if isinstance(x, SQL):
        return SQL("unaccent(%s)", x)
    if isinstance(x, psycopg_sql.Composable):
        return psycopg_sql.SQL("unaccent({})").format(x)
    return f"unaccent({x})"


@dataclass(frozen=True)
class _TextTransforms:
    unaccent_enabled: bool
    unaccent: dict[int, str]
    ilike: dict[int, str] | None


_ILIKE_FOLD_CACHE_MAX = 4096


class _TextTables:
    by_db: dict[str, _TextTransforms] = {}
    unaccented_chars: dict[str, dict[int, str]] = {}
    build_lock = threading.Lock()


def _get_text_transforms(
    cr: BaseCursor, db_name: str, unaccent_enabled: bool
) -> _TextTransforms:
    cached = _TextTables.by_db.get(db_name)
    if cached is not None and cached.unaccent_enabled == unaccent_enabled:
        return cached
    with _TextTables.build_lock:
        cached = _TextTables.by_db.get(db_name)
        if cached is not None and cached.unaccent_enabled == unaccent_enabled:
            return cached
        return _reset_text_transforms(cr, db_name, unaccent_enabled)


def _reset_text_transforms(
    cr: BaseCursor, db_name: str, unaccent_enabled: bool
) -> _TextTransforms:
    with _debug.perf(
        "registry.text_transforms.built", cr=cr, db=db_name, unaccent=unaccent_enabled
    ) as span:
        cr.execute(
            "SELECT datlocprovider FROM pg_database WHERE datname = current_database()"
        )
        provider = cr.fetchone()
        assert provider is not None
        context_free = provider[0] == "c"
        unaccent = SQL("unaccent(source)") if unaccent_enabled else SQL("source")
        folded = SQL("lower(%s)", unaccent) if context_free else SQL("source")
        cr.execute(
            SQL(
                """
            WITH chars AS (
                SELECT chr(code) AS source FROM generate_series(1, 55295) AS code
                UNION ALL
                SELECT chr(code) AS source FROM generate_series(57344, 1114111) AS code
            )
            SELECT source, %(unaccent)s AS unaccented, %(folded)s AS folded
            FROM chars WHERE source <> %(unaccent)s OR source <> %(folded)s
            """,
                unaccent=unaccent,
                folded=folded,
            )
        )
        unaccent_table = {}
        ilike_table = {}
        for row in cr.dictfetchall():
            code = ord(row["source"])
            if row["unaccented"] != row["source"]:
                unaccent_table[code] = row["unaccented"]
            if row["folded"] != row["source"]:
                ilike_table[code] = row["folded"]
        transforms = _TextTransforms(
            unaccent_enabled, unaccent_table, ilike_table if context_free else None
        )
        span.set(
            context_free=context_free,
            unaccent_table=len(unaccent_table),
            ilike_table=len(ilike_table),
        )
    _TextTables.by_db[db_name] = transforms
    return transforms


_UNACCENT_COVERING_MAX = 4096


def _unaccent_table_covering(cr: BaseCursor, db_name: str, text: str) -> dict[int, str]:
    table = _TextTables.unaccented_chars.setdefault(db_name, {})
    missing = sorted(
        {char for char in text if ord(char) > 127 and ord(char) not in table}
    )
    if missing:
        cr.execute(
            SQL(
                "SELECT source, unaccent(source) FROM unnest(%s::text[]) AS source",
                missing,
            )
        )
        table.update((ord(source), unaccented) for source, unaccented in cr.fetchall())
    return table


def clear_text_transforms(db_name: str) -> None:
    _TextTables.by_db.pop(db_name, None)
    _TextTables.unaccented_chars.pop(db_name, None)


def clear_all_text_transforms() -> None:
    _TextTables.by_db.clear()
    _TextTables.unaccented_chars.clear()


def _identity(x: typing.Any) -> typing.Any:
    return x


def _translate_python(x: str, table: dict[int, str]) -> str:
    return x.translate(table)


class _RegistryCapabilitiesMixin(_RegistryStubs):
    __slots__ = ()

    unaccent_status: FunctionStatus
    has_trigram: bool
    unaccent: _Unaccent

    _text_transforms: _TextTransforms | None
    _ilike_folded: dict[str, str]

    def _probe_capabilities(self, cr: BaseCursor, db_name: str) -> None:
        self._ilike_folded = {}
        self.unaccent_status = get_unaccent_status(cr)
        self.has_trigram = has_trigram(cr)
        self.unaccent = _unaccent if self.unaccent_status else _identity
        cached = _TextTables.by_db.get(db_name)
        self._text_transforms = (
            cached
            if cached is not None
            and cached.unaccent_enabled == bool(self.unaccent_status)
            else None
        )
        _debug.lifecycle(
            "registry.capabilities_probed",
            db=db_name,
            unaccent=self.unaccent_status.name,
            trigram=self.has_trigram,
            text_transforms_cached=self._text_transforms is not None,
        )

    def _get_text_transforms(self, cr: BaseCursor | None = None) -> _TextTransforms:
        transforms = self._text_transforms
        if transforms is None:
            unaccent_enabled = bool(self.unaccent_status)
            if cr is not None:
                transforms = _get_text_transforms(cr, self.db_name, unaccent_enabled)
            else:
                with closing(self.cursor()) as own_cr:
                    transforms = _get_text_transforms(
                        own_cr, self.db_name, unaccent_enabled
                    )
            self._text_transforms = transforms
        return transforms

    @property
    def unaccent_python(self) -> typing.Callable[[str], str]:
        return self.get_unaccent_normalizer()

    def get_unaccent_normalizer(
        self, cr: BaseCursor | None = None, covering: str | None = None
    ) -> typing.Callable[[str], str]:
        if not self.unaccent_status:
            return _identity
        if covering is None:
            table = self._get_text_transforms(cr).unaccent
        elif self._text_transforms is not None:
            table = self._text_transforms.unaccent
        elif covering.isascii():
            return _identity
        elif cr is not None:
            table = _unaccent_table_covering(cr, self.db_name, covering)
        else:
            with closing(self.cursor()) as own_cr:
                table = _unaccent_table_covering(own_cr, self.db_name, covering)
        if len(table) > _UNACCENT_COVERING_MAX:
            _TextTables.unaccented_chars.pop(self.db_name, None)
            table = self._get_text_transforms(cr).unaccent
        return partial(_translate_python, table=table)

    def get_ilike_normalizer(self, env: Environment) -> typing.Callable[[str], str]:
        transforms = self._text_transforms or self._get_text_transforms(env.cr)
        ilike_table = transforms.ilike
        if ilike_table is not None:
            return partial(_translate_python, table=ilike_table)

        folded = self._ilike_folded

        def normalize(value: str) -> str:
            result = folded.get(value)
            if result is None:
                if len(folded) >= _ILIKE_FOLD_CACHE_MAX:
                    folded.clear()
                expression = self.unaccent(SQL("%s", value))
                result = env.execute_query(SQL("SELECT lower(%s)", expression))[0][0]
                folded[value] = result
            return result

        return normalize
