import itertools
import re
from typing import TYPE_CHECKING

from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import SQL, normalize_identifier

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from odoo.api import Environment

_debug = DebugLog(__name__)

_SUBSELECT_UNNEST_THRESHOLD = 100


def _prepare_table_sql(alias: str, table: SQL) -> SQL:
    if (alias_identifier := SQL.identifier(alias)) == table:
        return table
    return SQL("%s AS %s", table, alias_identifier)


def _prepare_join_sql(kind: SQL, alias: str, table: SQL, condition: SQL) -> SQL:
    return SQL("%s %s ON (%s)", kind, _prepare_table_sql(alias, table), condition)


_SQL_JOINS = {
    "JOIN": SQL("JOIN"),
    "LEFT JOIN": SQL("LEFT JOIN"),
}


def _generate_table_alias(src_table_alias: str, link: str) -> str:
    return normalize_identifier(f"{src_table_alias}__{link}")


_PLACEHOLDER_RE = re.compile(r"%[%s]")


def _count_placeholders(code: str) -> int:
    return sum(match[0] == "%s" for match in _PLACEHOLDER_RE.finditer(code))


def _once_reference(table: str, index: int) -> SQL:
    identifier = SQL.identifier(_generate_table_alias(table, f"$once{index}"))
    return SQL("(SELECT v FROM %s)", identifier)


def _once_set_reference(table: str, index: int) -> SQL:
    identifier = SQL.identifier(_generate_table_alias(table, f"$set{index}"))
    return SQL("(SELECT * FROM %s)", identifier)


def _with_once(
    table: str, expressions: list[SQL], sets: Sequence[SQL] = ()
) -> SQL:
    if not expressions and not sets:
        return SQL.EMPTY
    return SQL(
        "WITH %s ",
        SQL(", ").join(
            [
                *(
                    SQL(
                        "%s AS MATERIALIZED (SELECT %s AS v)",
                        SQL.identifier(_generate_table_alias(table, f"$once{index}")),
                        expression,
                    )
                    for index, expression in enumerate(expressions)
                ),
                *(
                    SQL(
                        "%s AS MATERIALIZED (%s)",
                        SQL.identifier(_generate_table_alias(table, f"$set{index}")),
                        expression,
                    )
                    for index, expression in enumerate(sets)
                ),
            ]
        ),
    )


def _splice_once(sql: SQL, replacements: dict[str, SQL]) -> SQL:
    if not replacements or not sql:
        return sql
    references = re.compile("|".join(map(re.escape, replacements)))
    code: list[str] = []
    params: list = []
    pending = list(sql.params)
    position = 0
    for match in references.finditer(sql.code):
        before = sql.code[position : match.start()]
        taken = _count_placeholders(before)
        replacement = replacements[match[0]]
        code += (before, replacement.code)
        params += pending[:taken]
        params += replacement.params
        del pending[:taken]
        position = match.end()
    if not position:
        return sql
    code.append(sql.code[position:])
    return SQL(
        "".join(code),
        *params,
        *pending,
        to_flush=(
            *sql.to_flush,
            *(field for each in replacements.values() for field in each.to_flush),
        ),
    )


class Query:
    __slots__ = (
        "_any_value_orderby",
        "_empty_by_construction",
        "_env",
        "_groupby",
        "_having",
        "_ids",
        "_joins",
        "_limit",
        "_offset",
        "_once",
        "_once_sets",
        "_order",
        "_tables",
        "_where_clauses",
    )

    def __init__(self, env: Environment, alias: str, table: SQL | None = None) -> None:
        self._env = env

        self._tables: dict[str, SQL] = {
            alias: table if table is not None else SQL.identifier(alias),
        }

        self._joins: dict[str, tuple[SQL, SQL, SQL]] = {}

        self._once: list[SQL] = []
        self._once_sets: list[SQL] = []

        self._where_clauses: list[SQL] = []

        self._groupby: SQL | None = None
        self._any_value_orderby: bool = False
        self._having: SQL | None = None
        self._order: SQL | None = None
        self._limit: int | None = None
        self._offset: int | None = None

        self._ids: tuple[int, ...] | None = None

        self._empty_by_construction: bool = False

    def _invalidate_ids(self) -> None:
        if self._ids:
            self._ids = None

    def _drop_ids(self) -> None:
        self._ids = None

    @staticmethod
    def get_table_alias(alias: str, link: str) -> str:
        return _generate_table_alias(alias, link)

    def add_table(self, alias: str, table: SQL | None = None) -> None:
        if alias in self._tables or alias in self._joins:
            raise ValueError(f"Alias {alias!r} already in {self}")
        self._tables[alias] = table if table is not None else SQL.identifier(alias)
        self._invalidate_ids()

    def add_join(
        self, kind: str, alias: str, table: str | SQL | None, condition: SQL
    ) -> None:
        sql_kind = _SQL_JOINS.get(kind.upper())
        if sql_kind is None:
            raise ValueError(f"Invalid JOIN type {kind!r}")
        if alias in self._tables:
            raise ValueError(f"Alias {alias!r} already used")
        table = table or alias
        if isinstance(table, str):
            table = SQL.identifier(table)

        if alias in self._joins:
            if self._joins[alias] != (sql_kind, table, condition):
                raise ValueError(f"Alias {alias!r} already used with a different join")
        else:
            self._joins[alias] = (sql_kind, table, condition)
            self._invalidate_ids()

    def once(self, expression: SQL) -> SQL:
        try:
            index = self._once.index(expression)
        except ValueError:
            index = len(self._once)
            self._once.append(expression)
            self._invalidate_ids()
        return _once_reference(self.table, index)

    def once_set(self, expression: SQL) -> SQL:
        try:
            index = self._once_sets.index(expression)
        except ValueError:
            index = len(self._once_sets)
            self._once_sets.append(expression)
            self._invalidate_ids()
        return _once_set_reference(self.table, index)

    def _inline_once(self, sql: SQL) -> SQL:
        return self._inline_sets(
            _splice_once(
                sql,
                {
                    _once_reference(self.table, index).code: expression
                    for index, expression in enumerate(self._once)
                },
            )
        )

    def _inline_sets(self, sql: SQL) -> SQL:
        return _splice_once(
            sql,
            {
                _once_set_reference(self.table, index).code: SQL("(%s)", expression)
                for index, expression in enumerate(self._once_sets)
            },
        )

    def _with_sql(self) -> SQL:
        return _with_once(self.table, self._once)

    def copy(self) -> Query:
        cls = type(self)
        other = cls.__new__(cls)
        for klass in cls.__mro__:
            for slot in klass.__dict__.get("__slots__", ()):
                value = getattr(self, slot)
                if type(value) is dict:
                    value = dict(value)
                elif type(value) is list:
                    value = list(value)
                setattr(other, slot, value)
        return other

    def add_where(self, where_clause: SQL) -> None:
        self._where_clauses.append(where_clause)
        self._invalidate_ids()

    def _join_on_column(
        self,
        kind: str,
        lhs_alias: str,
        lhs_column: str,
        rhs_table: str | SQL,
        rhs_column: str,
        link: str,
    ) -> str:
        assert lhs_alias in self._tables or lhs_alias in self._joins, (
            "Alias %r not in %s" % (lhs_alias, str(self))
        )
        rhs_alias = self.get_table_alias(lhs_alias, link)
        condition = SQL(
            "%s = %s",
            SQL.identifier(lhs_alias, lhs_column),
            SQL.identifier(rhs_alias, rhs_column),
        )
        self.add_join(kind, rhs_alias, rhs_table, condition)
        return rhs_alias

    def join(
        self,
        lhs_alias: str,
        lhs_column: str,
        rhs_table: str | SQL,
        rhs_column: str,
        link: str,
    ) -> str:
        return self._join_on_column(
            "JOIN", lhs_alias, lhs_column, rhs_table, rhs_column, link
        )

    def left_join(
        self,
        lhs_alias: str,
        lhs_column: str,
        rhs_table: str | SQL,
        rhs_column: str,
        link: str,
    ) -> str:
        return self._join_on_column(
            "LEFT JOIN", lhs_alias, lhs_column, rhs_table, rhs_column, link
        )

    @property
    def order(self) -> SQL | None:
        return self._order

    @order.setter
    def order(self, value: SQL | None) -> None:
        self._order = value
        self._invalidate_ids()

    @property
    def groupby(self) -> SQL | None:
        return self._groupby

    @groupby.setter
    def groupby(self, value: SQL | None) -> None:
        self._groupby = value
        self._invalidate_ids()

    @property
    def having(self) -> SQL | None:
        return self._having

    @having.setter
    def having(self, value: SQL | None) -> None:
        self._having = value
        self._invalidate_ids()

    @property
    def limit(self) -> int | None:
        return self._limit

    @limit.setter
    def limit(self, value: int | None) -> None:
        self._limit = value
        self._drop_ids()

    @property
    def offset(self) -> int | None:
        return self._offset

    @offset.setter
    def offset(self, value: int | None) -> None:
        self._offset = value
        self._drop_ids()

    @property
    def table(self) -> str:
        return next(iter(self._tables))

    @property
    def from_clause(self) -> SQL:
        return self._inline_once(self._from_sql())

    def _from_sql(self) -> SQL:
        tables = SQL(" CROSS JOIN ").join(
            itertools.starmap(_prepare_table_sql, self._tables.items())
        )
        if not self._joins:
            return tables
        items = (
            tables,
            *(
                _prepare_join_sql(kind, alias, table, condition)
                for alias, (kind, table, condition) in self._joins.items()
            ),
        )
        return SQL(" ").join(items)

    @property
    def where_clause(self) -> SQL:
        return self._inline_once(self._where_sql())

    def _where_sql(self) -> SQL:
        return SQL(" AND ").join(self._where_clauses)

    def is_empty(self) -> bool:
        return self._empty_by_construction or self._ids == ()

    def select(self, *args: str | SQL) -> SQL:
        return self._select_sql(args, self.from_clause, self.where_clause)

    def statement(self, *args: str | SQL) -> SQL:
        if not self._once:
            return self.select(*args)
        return SQL(
            "%s%s",
            self._with_sql(),
            self._inline_sets(
                self._select_sql(args, self._from_sql(), self._where_sql())
            ),
        )

    def _select_sql(
        self, args: tuple[str | SQL, ...], from_clause: SQL, where_clause: SQL
    ) -> SQL:
        sql_args = map(SQL, args) if args else [SQL.identifier(self.table, "id")]
        return SQL(
            "%s%s%s%s%s%s%s%s",
            SQL("SELECT %s", SQL(", ").join(sql_args)),
            SQL(" FROM %s", from_clause),
            (SQL(" WHERE %s", where_clause) if self._where_clauses else SQL.EMPTY),
            SQL(" GROUP BY %s", self.groupby) if self.groupby else SQL.EMPTY,
            SQL(" HAVING %s", self.having) if self.having else SQL.EMPTY,
            SQL(" ORDER BY %s", self._order) if self._order else SQL.EMPTY,
            SQL(" LIMIT %s", self.limit) if self.limit is not None else SQL.EMPTY,
            SQL(" OFFSET %s", self.offset) if self.offset else SQL.EMPTY,
        )

    def subselect(self, *args: str | SQL) -> SQL:
        if self.groupby or self.having:
            raise ValueError(
                "Query.subselect() does not support groupby/having; use select()"
            )

        if self._ids is not None and not args:
            if not self._ids:
                return SQL("(SELECT 1 WHERE FALSE)")
            if len(self._ids) > _SUBSELECT_UNNEST_THRESHOLD:
                return SQL("(SELECT unnest(%s))", list(self._ids))
            return SQL("%s", self._ids)

        if self.limit is not None or self.offset:
            return SQL("(%s)", self.select(*args))

        sql_args = map(SQL, args) if args else [SQL.identifier(self.table, "id")]
        return SQL(
            "(%s%s%s)",
            SQL("SELECT %s", SQL(", ").join(sql_args)),
            SQL(" FROM %s", self.from_clause),
            (SQL(" WHERE %s", self.where_clause) if self._where_clauses else SQL.EMPTY),
        )

    def get_result_ids(self, env: Environment | None = None) -> tuple[int, ...]:
        if self._empty_by_construction:
            self._ids = ()
            return self._ids

        if env is None or env.cr is self._env.cr:
            if self._ids is None:
                self._ids = tuple(
                    id_ for (id_,) in self._env.execute_query(self.statement())
                )
                _debug.perf.count(
                    "query.result_ids",
                    table=self.table,
                    joins=len(self._joins),
                    rows=len(self._ids),
                    limit=self.limit,
                )
            return self._ids

        _debug.logic("query.result_ids.foreign_transaction", table=self.table)
        return tuple(id_ for (id_,) in env.execute_query(self.statement()))

    def set_result_ids(self, ids: Iterable[int], ordered: bool = True) -> None:
        if (
            self._joins
            or self._once
            or self._once_sets
            or self._where_clauses
            or self.limit is not None
            or self.offset
        ):
            raise ValueError(
                "Method set_result_ids() can only be called on a virgin Query"
            )
        ids = tuple(ids)
        _debug.logic(
            "query.result_ids_pinned", table=self.table, ids=len(ids), ordered=ordered
        )
        if not ids:
            self.add_where(SQL("FALSE"))
            self._empty_by_construction = True
        elif ordered:
            alias = self.join(
                self.table,
                "id",
                SQL("(SELECT * FROM unnest(%s) WITH ORDINALITY)", list(ids)),
                "unnest",
                "ids",
            )
            self.order = SQL.identifier(alias, "ordinality")
        else:
            self.add_where(
                SQL("%s = ANY(%s)", SQL.identifier(self.table, "id"), list(ids))
            )
        self._ids = ids

    def __str__(self) -> str:
        sql = self.select()
        return f"<Query: {sql.code!r} with params: {sql.params!r}>"

    def __bool__(self) -> bool:
        return bool(self.get_result_ids())

    def __len__(self) -> int:
        if self._ids is None:
            if self.limit is not None or self.offset or self.groupby or self.having:
                sql = SQL("SELECT COUNT(*) FROM (%s) t", self.statement(""))
            else:
                sql = self.statement("COUNT(*)")
            count = self._env.execute_query(sql)[0][0]
            _debug.perf.count(
                "query.len_counted",
                table=self.table,
                joins=len(self._joins),
                count=count,
                wrapped=self.limit is not None or bool(self.offset),
            )
            return count
        return len(self.get_result_ids())

    def count_matching(self, limit: int | None = None) -> int:
        if self._empty_by_construction:
            return 0
        if (
            self._ids is not None
            and self.limit is None
            and not self.offset
            and not self.groupby
            and not self.having
        ):
            return len(self._ids) if limit is None else min(len(self._ids), limit)

        _debug.perf.count(
            "query.count_matching",
            table=self.table,
            joins=len(self._joins),
            limit=limit,
            subquery=bool(self.groupby or self.having or limit is not None),
        )
        if self.groupby or self.having or limit is not None:
            parts = [
                SQL(
                    "%sSELECT FROM %s",
                    self._with_sql(),
                    self._inline_sets(self._from_sql()),
                )
            ]
            if self._where_clauses:
                parts.append(SQL(" WHERE %s", self._inline_sets(self._where_sql())))
            if self.groupby:
                parts.append(SQL(" GROUP BY %s", self.groupby))
            if self.having:
                parts.append(SQL(" HAVING %s", self.having))
            if limit is not None:
                parts.append(SQL(" LIMIT %s", limit))
            return self._env.execute_query(
                SQL("SELECT COUNT(*) FROM (%s) t", SQL("").join(parts))
            )[0][0]
        sql = SQL(
            "%sSELECT COUNT(*) FROM %s",
            self._with_sql(),
            self._inline_sets(self._from_sql()),
        )
        if self._where_clauses:
            sql = SQL("%s WHERE %s", sql, self._inline_sets(self._where_sql()))
        return self._env.execute_query(sql)[0][0]

    def __iter__(self) -> Iterator[int]:
        return iter(self.get_result_ids())


class SharedOnce:

    __slots__ = ("_expressions", "_sets", "_table")

    def __init__(self, table: str) -> None:
        self._table = table
        self._expressions: list[SQL] = []
        self._sets: list[SQL] = []

    def select(self, query: Query, *args: str | SQL) -> SQL:
        if query.table != self._table:
            msg = f"{query.table!r} is not this scope's table {self._table!r}"
            raise ValueError(msg)
        references: dict[str, SQL] = {}
        for index, expression in enumerate(query._once):
            try:
                shared = self._expressions.index(expression)
            except ValueError:
                shared = len(self._expressions)
                self._expressions.append(expression)
            references[_once_reference(self._table, index).code] = _once_reference(
                self._table, shared
            )
        for index, expression in enumerate(query._once_sets):
            try:
                shared = self._sets.index(expression)
            except ValueError:
                shared = len(self._sets)
                self._sets.append(expression)
            references[_once_set_reference(self._table, index).code] = (
                _once_set_reference(self._table, shared)
            )
        return _splice_once(
            query._select_sql(args, query._from_sql(), query._where_sql()),
            references,
        )

    def statement(self, body: SQL) -> SQL:
        _debug.perf.count(
            "query.shared_once",
            table=self._table,
            expressions=len(self._expressions),
            sets=len(self._sets),
        )
        return SQL("%s%s", _with_once(self._table, self._expressions, self._sets), body)
