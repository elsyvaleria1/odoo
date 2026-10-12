from __future__ import annotations

import re
import typing
import warnings
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any, override

from psycopg import sql as _sql

from odoo.libs.collections.frozen_dict import freehash
from odoo.libs.utils import named_to_positional_printf

if TYPE_CHECKING:
    from psycopg.abc import AdaptContext

    from odoo.db import BaseCursor
    from odoo.fields import Field
else:
    type Field[T] = typing.Any
    BaseCursor = typing.Any
__all__ = ["SQL"]


IDENT_RE = re.compile(r"^[a-z0-9_][a-z0-9_$\-]*\Z", re.IGNORECASE)

_PRINTF_DIRECTIVE_RE = re.compile(r"%(.)", re.DOTALL)
_EMPTY_TUPLE = "(NULL)"
_NOT_IN_EMPTY_RE = re.compile(r"\bNOT\s+IN\s*\(NULL\)", re.IGNORECASE)
_MAX_IDENTIFIER_BYTES = 63


def _check_identifier(name: str) -> None:
    if not (name.isidentifier() or IDENT_RE.match(name)):
        raise ValueError(f"{name!r} invalid for SQL.identifier()")
    if (
        len(name) > _MAX_IDENTIFIER_BYTES // 4
        and len(name.encode()) > _MAX_IDENTIFIER_BYTES
    ):
        raise ValueError(
            f"{name!r} exceeds PostgreSQL's {_MAX_IDENTIFIER_BYTES}-byte identifier "
            "limit; shorten it with normalize_identifier()"
        )


class SQL:
    __slots__ = ("__code", "__params", "__to_flush")

    __code: str
    __params: tuple[Any, ...]
    __to_flush: tuple[Field[Any], ...]

    def __init__(
        self,
        code: str | SQL = "",
        /,
        *args: object,
        to_flush: Field[Any] | Iterable[Field[Any]] | None = None,
        **kwargs: object,
    ) -> None:
        if isinstance(code, SQL):
            self.__adopt(code, args, kwargs, to_flush)
            return
        if code == "%s" and len(args) == 1 and isinstance(args[0], SQL):
            self.__adopt(args[0], (), kwargs, to_flush)
            return

        if args and kwargs:
            msg = "SQL() takes either positional arguments, or named arguments"
            raise TypeError(msg)

        if kwargs:
            code, args = named_to_positional_printf(code, kwargs)
        elif not args:
            if "%" in code:
                code % ()
            self.__code = code
            self.__params = ()
            self.__to_flush = self.__normalize_to_flush(to_flush)
            return

        code_list: list[str] = []
        params_list: list[object] = []
        to_flush_list: list[Field[Any]] = []
        inserts_empty_tuple = False
        for arg in args:
            if isinstance(arg, SQL):
                inserts_empty_tuple |= arg.__code.lstrip().startswith(_EMPTY_TUPLE)
                code_list.append(arg.__code)
                params_list.extend(arg.__params)
                to_flush_list.extend(arg.__to_flush)
            elif isinstance(arg, tuple):
                if arg:
                    element_codes = []
                    for element in arg:
                        if isinstance(element, SQL):
                            element_codes.append(element.__code)
                            params_list.extend(element.__params)
                            to_flush_list.extend(element.__to_flush)
                        else:
                            element_codes.append("%s")
                            params_list.append(element)
                    code_list.append("(%s)" % ", ".join(element_codes))
                else:
                    inserts_empty_tuple = True
                    code_list.append(_EMPTY_TUPLE)
            else:
                code_list.append("%s")
                params_list.append(arg)
        to_flush_list.extend(self.__normalize_to_flush(to_flush))

        self.__code = code.replace("%%", "%%%%") % tuple(code_list)
        if inserts_empty_tuple and _NOT_IN_EMPTY_RE.search(self.__code):
            msg = (
                "an empty tuple after NOT IN renders NOT IN (NULL), which matches "
                "no row; excluding nothing is TRUE, so test for the empty case, "
                "or write `<> ALL(%s)` with a list that holds no NULL"
            )
            raise ValueError(msg)
        self.__params = tuple(params_list)
        self.__to_flush = tuple(to_flush_list)

    def __adopt(
        self,
        source: SQL,
        args: tuple[object, ...],
        kwargs: dict[str, object],
        to_flush: Field[Any] | Iterable[Field[Any]] | None,
    ) -> None:
        if args or kwargs:
            msg = "SQL() unexpected arguments when code has type SQL"
            raise TypeError(msg)
        self.__code = source.__code
        self.__params = source.__params
        self.__to_flush = source.__to_flush + self.__normalize_to_flush(to_flush)

    @staticmethod
    def __normalize_to_flush(
        to_flush: Field[Any] | Iterable[Field[Any]] | None,
    ) -> tuple[Field[Any], ...]:
        if to_flush is None:
            return ()
        if isinstance(to_flush, Iterable) and not isinstance(to_flush, (str, bytes)):
            return tuple(to_flush)
        return (to_flush,)

    @property
    def code(self) -> str:
        return self.__code

    @property
    def params(self) -> tuple[Any, ...]:
        return self.__params

    @property
    def to_flush(self) -> Iterable[Field[Any]]:
        return self.__to_flush

    def with_to_flush(self, to_flush: Iterable[Field[Any]]) -> SQL:
        sql = SQL.__new__(SQL)
        sql.__code = self.__code
        sql.__params = self.__params
        sql.__to_flush = self.__normalize_to_flush(to_flush)
        return sql

    def render(self) -> str:
        return self.__inline_params(None)

    def inlined(self, cr: BaseCursor) -> SQL:
        if not self.__params:
            return self
        return SQL(self.__inline_params(cr.connection), to_flush=self.__to_flush)

    def __inline_params(self, context: AdaptContext | None) -> str:
        if not self.__params:
            return self.__code
        params = iter(self.__params)

        def substitute(match: re.Match[str]) -> str:
            directive = match[1]
            if directive == "%":
                return "%%"
            if directive == "s":
                literal: str = _sql.Literal(next(params)).as_string(context)
                return literal.replace("%", "%%")
            raise ValueError(
                f"SQL: unsupported format directive %{directive} in {self.__code!r}"
            )

        return _PRINTF_DIRECTIVE_RE.sub(substitute, self.__code)

    @override
    def __repr__(self) -> str:
        return f"SQL({', '.join(map(repr, [self.__code, *self.__params]))})"

    def __bool__(self) -> bool:
        return bool(self.__code)

    @override
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, SQL)
            and self.__code == other.__code
            and self.__params == other.__params
        )

    @override
    def __hash__(self) -> int:
        return hash((self.__code, freehash(self.__params)))

    def __iter__(self) -> Iterator[str | tuple[Any, ...]]:
        warnings.warn(
            "Deprecated since 19.0, use code and params properties directly",
            DeprecationWarning,
            stacklevel=2,
        )
        yield self.code
        yield self.params

    def join(self, args: Iterable[object]) -> SQL:
        items = args if isinstance(args, list) else list(args)
        if len(items) == 0:
            return SQL.EMPTY
        if len(items) == 1 and isinstance(items[0], SQL):
            return items[0]
        separator_to_flush = self.__to_flush if len(items) > 1 else ()
        if not self.__params:
            return SQL(
                self.__code.join("%s" for _ in items),
                *items,
                to_flush=separator_to_flush,
            )
        result = [self] * (len(items) * 2 - 1)
        for index, arg in enumerate(items):
            result[index * 2] = arg
        items_to_flush = SQL("%s" * len(items), *items).__to_flush
        return SQL("%s" * len(result), *result).with_to_flush(
            (*items_to_flush, *separator_to_flush)
        )

    EMPTY: SQL

    @classmethod
    def identifier(
        cls,
        name: str,
        subname: str | None = None,
        to_flush: Field[Any] | None = None,
    ) -> SQL:
        _check_identifier(name)
        if subname is None:
            return cls(f'"{name}"', to_flush=to_flush)
        _check_identifier(subname)
        return cls(f'"{name}"."{subname}"', to_flush=to_flush)

    @classmethod
    def literal(cls, value: str) -> SQL:
        if not isinstance(value, str):
            raise TypeError(
                f"SQL.literal() expected str, got {type(value).__name__}: {value!r}"
            )
        if "'" in value or "\\" in value or "%" in value or "\x00" in value:
            raise ValueError(f"{value!r} invalid for SQL.literal()")
        return cls(f"'{value}'")


SQL.EMPTY = SQL()
