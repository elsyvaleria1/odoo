from __future__ import annotations

import functools
import operator as pyoperator
import typing
import zoneinfo
from datetime import UTC, datetime
from datetime import timedelta as _timedelta
from decimal import Decimal
from itertools import product

from odoo.exceptions import UserError
from odoo.libs.datetime import get_quarter_number
from odoo.libs.debug_log import DebugLog
from odoo.libs.iteration import unique
from odoo.libs.sql import SQL
from odoo.tools import Query, get_lang

from ..domain import Domain, DomainCondition
from ..domain.ast import DomainCustom
from ..fields.properties import local_temporal_property, parse_temporal_property
from ..fields.temporal import Date
from ..parsing import parse_read_group_spec, regex_order_part_read_group
from ._backend_memory_constraints import _foreign_key_targets
from ._backend_memory_hierarchy import _InMemoryHierarchyMixin
from ._backend_memory_query import _get_sort_key, _InMemoryQuery
from ._backend_memory_read import _InMemoryReadMixin
from ._backend_memory_relations import _InMemoryRelationsMixin
from ._backend_memory_stores import InMemoryColumnStore, InMemorySequenceStore
from ._backend_memory_write import _InMemoryWriteMixin
from ._search_flush import flush_search_dependencies
from .backend import ColumnStore, SequenceStore

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..components.storage import DictBackend
    from ..fields import Field
    from ..models.base import BaseModel
    from .environment import Environment

__all__ = [
    "InMemoryBackend",
    "InMemoryColumnStore",
    "InMemorySequenceStore",
    "_InMemoryQuery",
    "_foreign_key_targets",
]

_debug = DebugLog(__name__)


def _carries_a_python_predicate(domain: Domain) -> bool:
    if isinstance(domain, DomainCustom):
        return domain._filtered is not None
    child = getattr(domain, "child", None)
    if child is not None:
        return _carries_a_python_predicate(child)
    return any(
        _carries_a_python_predicate(item) for item in getattr(domain, "children", ())
    )


@functools.cache
def _python_timezone_names() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


class _MultiValued(list[typing.Any]):
    __slots__ = ()


_DATE_PART = {
    "year_number": lambda d: float(d.year),
    "quarter_number": lambda d: float(get_quarter_number(d)),
    "month_number": lambda d: float(d.month),
    "iso_week_number": lambda d: float(d.isocalendar()[1]),
    "day_of_year": lambda d: float(d.timetuple().tm_yday),
    "day_of_month": lambda d: float(d.day),
    "day_of_week": lambda d: float((d.weekday() + 1) % 7),
    "hour_number": lambda d: float(d.hour),
    "minute_number": lambda d: float(d.minute),
    "second_number": lambda d: float(d.second),
}


_TRUNCATE_GRANULARITY = {
    "year": lambda d: d.replace(month=1, day=1),
    "quarter": lambda d: d.replace(month=3 * ((d.month - 1) // 3) + 1, day=1),
    "month": lambda d: d.replace(day=1),
    "day": lambda d: d,
}


def _truncate(
    value: typing.Any,
    granularity: str,
    first_week_day: int = 0,
    tz: zoneinfo.ZoneInfo | None = None,
) -> typing.Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        if tz is not None:
            try:
                value = value.replace(tzinfo=UTC).astimezone(tz).replace(tzinfo=None)
            except OverflowError:
                if granularity != "week" or value.year != 1:
                    raise
                return value.replace(
                    month=1, day=1, hour=0, minute=0, second=0, microsecond=0
                )
        if granularity == "hour":
            return value.replace(minute=0, second=0, microsecond=0)
        if granularity in _DATE_PART:
            return _DATE_PART[granularity](value)
        value = value.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity in _DATE_PART:
        if granularity in ("hour_number", "minute_number", "second_number"):
            return 0.0
        return _DATE_PART[granularity](value)
    if granularity == "week":
        try:
            return value - _timedelta(days=(value.weekday() - first_week_day) % 7)
        except OverflowError:
            return value.replace(year=1, month=1, day=1)
    try:
        return _TRUNCATE_GRANULARITY[granularity](value)
    except KeyError:
        raise NotImplementedError(
            f"InMemoryBackend.read_group_rows: granularity {granularity!r} is not "
            "supported in memory"
        ) from None


type _CacheSnapshot = dict[
    tuple[Field[typing.Any], tuple[typing.Any, ...] | None], set[typing.Any]
]


def _cache_snapshot(env: Environment) -> _CacheSnapshot:
    core = env.core
    snapshot: _CacheSnapshot = {}
    for field in list(core.iter_cached_fields()):
        data = core.get_field_data_or_none(field)
        if data is not None:
            snapshot[field, None] = set(data)
        for key, slot in core.iter_context_caches(field):
            snapshot[field, key] = set(slot)
    return snapshot


_RELATIONAL_SEARCH_OPERATORS = frozenset(("any", "not any", "any!", "not any!"))


def _scope_to_reader(model: ModelLike, domain: Domain) -> Domain:
    env = model.env
    policy = env.registry.access_policy

    def scope(condition: DomainCondition) -> Domain:
        field = condition._get_field(typing.cast("BaseModel", model))
        model._check_field_access(field, "read")
        value = condition.value
        if not (
            field.relational
            and condition.operator in _RELATIONAL_SEARCH_OPERATORS
            and isinstance(value, Domain)
        ):
            return condition
        comodel = env[field.comodel_name]
        scoped = _scope_to_reader(comodel, value)
        if condition.operator in ("any", "not any") and not field.bypass_search_access:
            comodel.check_access("read")
            rule = policy.record_domain(env, comodel._name, "read")
            if not rule.is_true():
                readable = comodel.sudo().with_context(active_test=False)
                scoped &= Domain("id", "in", readable.search(rule).ids)
        return DomainCondition(condition.field_expr, condition.operator, scoped)

    return domain.map_conditions(scope)


def _drop_cache_additions(env: Environment, snapshot: _CacheSnapshot) -> None:
    core = env.core
    for field in list(core.iter_cached_fields()):
        data = core.get_field_data_or_none(field)
        if data is not None:
            for id_ in set(data) - snapshot.get((field, None), set()):
                del data[id_]
        for key, slot in list(core.iter_context_caches(field)):
            for id_ in set(slot) - snapshot.get((field, key), set()):
                del slot[id_]


class _InMemoryReadGroup:
    """read_group over the dict storage: one row per group, raw values shaped as
    the SQL rows are (a many2one is its id, a date is truncated, text NULLIF'd)."""

    def __init__(
        self,
        model: ModelLike,
        domain: typing.Any,
        groupby: typing.Iterable[str],
        aggregates: typing.Iterable[str],
        storage: DictBackend | None = None,
    ) -> None:
        self.model = model
        self.storage = storage
        self.records = typing.cast(
            "BaseModel", model.browse(model._search(domain).get_result_ids())
        )
        self.groupby_specs = list(groupby)
        self.aggregate_specs = list(aggregates)
        self.groupby = [self._groupby_reader(spec) for spec in groupby]
        self.aggregates = [self._aggregate_reader(spec) for spec in aggregates]
        self.order_specs: list[str] = []
        self.order_aggregates: list[typing.Callable[[ModelLike], typing.Any]] = []

    def _stored_is_null(self, table: str, fname: str, record: ModelLike) -> bool:
        if self.storage is None:
            return False
        row = self.storage.get_row(table, typing.cast("int", record.id))
        return row is None or row.get(fname) is None

    def _unsupported(self, what: str) -> typing.NoReturn:
        raise NotImplementedError(
            f"InMemoryBackend.read_group_rows on {self.model._name}: {what} is not "
            "supported in memory; use a DB-backed TransactionCase"
        )

    def _groupby_reader(
        self, spec: typing.Any, model: ModelLike | None = None
    ) -> typing.Callable[[BaseModel], typing.Any]:
        model = self.model if model is None else model
        fname, seq_fnames, granularity = parse_read_group_spec(spec)
        field = model._fields[fname]
        if field.is_properties:
            return self._property_reader(model, field, seq_fnames, granularity, spec)
        if field.is_many2many:
            return self._many2many_reader(model, field, spec)
        if seq_fnames:
            return self._many2one_path_reader(
                model, fname, field, seq_fnames, granularity, spec
            )

        first_week_day = 0
        tz = None
        if field.is_temporal:
            model._read_group_check_temporal_granularity(
                granularity or "", field.is_date, spec
            )
        elif granularity:
            raise ValueError(
                f"Granularity set on a no-datetime field or property: {spec!r}"
            )
        temporal_unit = granularity or ""
        if field.is_temporal and granularity == "week":
            first_week_day = int(get_lang(model.env).week_start) - 1
        if field.is_datetime and (tz_name := model.env.context.get("tz")):
            try:
                tz = zoneinfo.ZoneInfo(tz_name)
            except zoneinfo.ZoneInfoNotFoundError, ValueError:
                tz = None

        reads_null_cell = (
            field.store and bool(field.column_type) and not field.company_dependent
        )

        def read(record: ModelLike) -> typing.Any:
            value = record[fname]
            if field.is_many2one:
                return value.id or None
            if field.is_temporal:
                return _truncate(value or None, temporal_unit, first_week_day, tz)
            if field.is_boolean:
                return bool(value)
            if field.is_text:
                return value or None
            if value is False or (
                not value
                and reads_null_cell
                and self._stored_is_null(model._table, fname, record)
            ):
                return None
            return value

        return read

    def _many2many_reader(
        self, model: ModelLike, field: Field[typing.Any], spec: str
    ) -> typing.Callable[[BaseModel], typing.Any]:
        if not field.store:
            raise ValueError(f"Group by non-stored many2many field: {spec!r}")
        comodel = model.env[field.comodel_name].with_context(**field.context)
        allowed = set(
            comodel._search(
                field.get_comodel_domain(model),
                bypass_access=field.bypass_search_access,
            ).get_result_ids()
        )

        def read(record: ModelLike) -> typing.Any:
            ids = [id_ for id_ in record[field.name]._ids if id_ in allowed]
            return _MultiValued(ids or [None])

        return read

    @staticmethod
    def _property_temporal_unit(
        model: ModelLike,
        property_type: str | None,
        granularity: str | None,
        spec: str,
    ) -> tuple[int, zoneinfo.ZoneInfo | None]:
        if property_type not in ("date", "datetime"):
            if granularity:
                raise ValueError(
                    f"Granularity set on a no-datetime field or property: {spec!r}"
                )
            return 0, None
        model._read_group_check_temporal_granularity(
            granularity or "", property_type == "date", spec
        )
        first_week_day = 0
        if granularity == "week":
            first_week_day = int(get_lang(model.env).week_start) - 1
        tz = None
        if property_type == "datetime" and (tz_name := model.env.context.get("tz")):
            try:
                tz = zoneinfo.ZoneInfo(tz_name)
            except zoneinfo.ZoneInfoNotFoundError, ValueError:
                tz = None
        return first_week_day, tz

    def _property_reader(
        self,
        model: ModelLike,
        field: Field[typing.Any],
        property_name: str | None,
        granularity: str | None,
        spec: str,
    ) -> typing.Callable[[BaseModel], typing.Any]:
        if not property_name:
            self._unsupported(f"groupby {spec!r}")
        definition = model.get_property_definition(f"{field.name}.{property_name}")
        property_type = definition.get("type")
        if property_type == "html":
            raise UserError(
                model.env._("Grouping by HTML properties is not supported.")
            )
        options = {option[0] for option in definition.get("selection") or ()}
        tags = {tag[0] for tag in definition.get("tags") or ()}
        comodel = None
        if property_type in ("many2one", "many2many") and definition.get("comodel"):
            comodel = (
                model.env[definition["comodel"]].sudo().with_context(active_test=False)
            )

        def is_id(raw: typing.Any) -> bool:
            return isinstance(raw, int) and not isinstance(raw, bool)

        first_week_day, tz = self._property_temporal_unit(
            model, property_type, granularity, spec
        )

        if property_type in ("tags", "many2many"):
            def read_collection(record: ModelLike) -> typing.Any:
                values = record[field.name]
                raw = (values._values or {}).get(property_name)
                if not isinstance(raw, list):
                    return None
                if property_type == "tags":
                    keys = [key for key in raw if key in tags]
                elif comodel is None:
                    keys = []
                else:
                    keys = [
                        key
                        for key in raw
                        if is_id(key) and comodel.browse(key).exists()
                    ]
                return _MultiValued(keys) if keys else None

            return read_collection

        def read(record: ModelLike) -> typing.Any:
            values = record[field.name]
            raw = (values._values or {}).get(property_name)
            if property_type == "selection":
                return raw if raw in options else None
            if property_type == "many2one":
                if not is_id(raw) or comodel is None:
                    return None
                return raw if comodel.browse(raw).exists() else None
            if property_type in ("date", "datetime"):
                value = parse_temporal_property(raw, property_type)
                if (
                    tz is not None
                    and isinstance(value, datetime)
                    and local_temporal_property(value, tz) is None
                ):
                    return None
                return _truncate(value, granularity or "", first_week_day, tz)
            if property_type == "boolean":
                return bool(raw)
            if raw is None or raw is False:
                return None
            return raw

        return read

    def _many2one_path_reader(
        self,
        model: ModelLike,
        fname: str,
        field: Field[typing.Any],
        seq_fnames: typing.Sequence[str],
        granularity: str | None,
        spec: str,
    ) -> typing.Callable[[BaseModel], typing.Any]:
        if not field.is_many2one:
            raise ValueError(
                f"Only many2one path is accepted for the {spec!r} groupby spec"
            )
        env = model.env
        comodel = env[field.comodel_name]
        rules = None
        if not env.su:
            sec_domain = env.registry.access_policy.record_domain(
                env, comodel._name, "read"
            )
            if not sec_domain.is_true():
                rules = sec_domain
        rest = f"{seq_fnames}:{granularity}" if granularity else seq_fnames
        read_rest = self._groupby_reader(rest, comodel)

        def read(record: ModelLike) -> typing.Any:
            corecord = record[fname]
            if not corecord:
                return None
            if rules is not None and not (
                corecord.sudo().with_context(active_test=False).filtered_domain(rules)
            ):
                return None
            return read_rest(corecord)

        return read

    def _aggregate_reader(self, spec: str) -> typing.Callable[[ModelLike], typing.Any]:
        if spec == "__count":
            return len
        fname, _property, func = parse_read_group_spec(spec)
        field = self.model._fields[fname]
        if not field.store and not self.model._aggregates_through_records(
            field, func or ""
        ):
            raise ValueError(f"Cannot convert {field} to SQL because it is not stored")

        if self.model._aggregates_through_records(field, func or ""):
            def group_ids(records: ModelLike) -> typing.Any:
                return list(records.ids) or None

            return group_ids

        table = self.model._table

        def raw(record: ModelLike) -> typing.Any:
            value = record[fname]
            if field.relational:
                return value.id or None if field.is_many2one else list(value.ids)
            if field.is_boolean:
                return value
            if not value and self._stored_is_null(table, fname, record):
                return None
            return None if value is False else value

        def values(records: ModelLike) -> list[typing.Any]:
            return [raw(record) for record in records]

        def present(records: ModelLike) -> list[typing.Any]:
            return [v for v in values(records) if v is not None]

        def distinct_sorted(all_values: list[typing.Any]) -> list[typing.Any] | None:
            distinct = set(all_values)
            has_null = None in distinct
            distinct.discard(None)
            return [*sorted(distinct), *([None] if has_null else [])] or None

        total: typing.Callable[[list[typing.Any]], typing.Any]
        mean: typing.Callable[[list[typing.Any]], typing.Any]
        if field.column_type and field.column_type[0] == "numeric":
            def total(present_values: list[typing.Any]) -> typing.Any:
                return float(sum(Decimal(repr(v)) for v in present_values))

            def mean(present_values: list[typing.Any]) -> typing.Any:
                exact = sum(Decimal(repr(v)) for v in present_values)
                return float(exact / len(present_values))
        else:
            total = sum

            def mean(present_values: list[typing.Any]) -> typing.Any:
                return sum(present_values) / len(present_values)

        def over_present(
            fold: typing.Callable[[list[typing.Any]], typing.Any],
        ) -> typing.Callable[[ModelLike], typing.Any]:
            def read(records: ModelLike) -> typing.Any:
                present_values = present(records)
                return fold(present_values) if present_values else None

            return read

        readers = {
            "count": lambda records: len(present(records)),
            "count_distinct": lambda records: len(set(present(records))),
            "sum": over_present(total),
            "avg": over_present(mean),
            "max": lambda records: max(present(records), default=None),
            "min": lambda records: min(present(records), default=None),
            "bool_and": over_present(all),
            "bool_or": over_present(any),
            "array_agg": lambda records: values(records) or None,
            "array_agg_distinct": lambda records: distinct_sorted(values(records)),
            "recordset": lambda records: (
                [
                    id_
                    for record in records
                    for id_ in (record.ids if fname == "id" else record[fname].ids)
                ]
                or None
            ),
        }
        if func == "sum_currency":
            return self._sum_currency_reader(field, fname, raw)
        if func not in readers:
            self._unsupported(f"aggregate {spec!r}")
        return readers[func]

    def _sum_currency_reader(
        self,
        field: Field[typing.Any],
        fname: str,
        raw: typing.Callable[[BaseModel], typing.Any],
    ) -> typing.Callable[[ModelLike], typing.Any]:
        if not field.is_monetary:
            raise ValueError(
                f'Aggregator "sum_currency" only works on currency field for {fname!r}'
            )
        env = self.model.env
        currency_field_name = field.get_currency_field(self.model)
        rate_by_currency = env.registry.locale.currency_rates(
            env, env.company, Date.context_today(self.model)
        )

        def read(records: ModelLike) -> typing.Any:
            present = [
                (value, record[typing.cast("str", currency_field_name)].id)
                for record in typing.cast("BaseModel", records)
                if (value := raw(record)) is not None
            ]
            if not present:
                return None
            return sum(
                value / rate_by_currency.get(currency_id, 1.0)
                for value, currency_id in present
            )

        return read

    def rows(
        self,
        having: list[typing.Any] | None,
        order: str | None,
        limit: int | None,
        offset: int,
    ) -> list[tuple[typing.Any, ...]]:
        self._select_order_aggregates(order)
        groups: dict[tuple[typing.Any, ...], list[BaseModel]] = {}
        for record in self.records:
            for key in product(
                *(
                    value if isinstance(value, _MultiValued) else (value,)
                    for value in (read(record) for read in self.groupby)
                )
            ):
                groups.setdefault(key, []).append(record)
        if not self.groupby:
            groups = {(): list(self.records)}
        rows = [
            (
                *key,
                *(
                    aggregate(self.model.browse(sorted(r.id for r in members)))
                    for aggregate in (*self.aggregates, *self.order_aggregates)
                ),
            )
            for key, members in groups.items()
        ]
        if having:
            keep = self._having_predicate(having)
            rows = [row for row in rows if keep(row) is True]
        self._sort(rows, order)
        if self.groupby:
            rows = rows[offset:]
            if limit is not None:
                rows = rows[:limit]
        if self.order_specs:
            width = len(self.groupby_specs) + len(self.aggregate_specs)
            rows = [row[:width] for row in rows]
        return rows

    def _select_order_aggregates(self, order: str | None) -> None:
        self.order_specs = []
        self.order_aggregates = []
        if not order:
            return
        for order_part in order.split(","):
            match = regex_order_part_read_group.fullmatch(order_part)
            if not match:
                raise ValueError(f"Invalid order {order!r} for _read_group()")
            term = match["term"]
            if (
                term in self.groupby_specs
                or term in self.aggregate_specs
                or term in self.order_specs
            ):
                continue
            try:
                reader = self._aggregate_reader(term)
            except (ValueError, KeyError) as e:
                raise ValueError(
                    f"Order term {order_part!r} is not a valid aggregate nor valid groupby"
                ) from e
            self.order_specs.append(term)
            self.order_aggregates.append(reader)

    def _having_predicate(
        self, having: list[typing.Any]
    ) -> typing.Callable[[tuple[typing.Any, ...]], typing.Any]:
        specs = [*self.groupby_specs, *self.aggregate_specs]
        compare = {
            "=": pyoperator.eq,
            "!=": pyoperator.ne,
            "<": pyoperator.lt,
            "<=": pyoperator.le,
            ">": pyoperator.gt,
            ">=": pyoperator.ge,
        }

        def condition(
            item: typing.Any,
        ) -> typing.Callable[[tuple[typing.Any, ...]], typing.Any]:
            left, op, right = item
            if left not in specs:
                raise ValueError(
                    f"Invalid having clause {item!r}: {left!r} is neither an "
                    "aggregate nor a groupby of this read_group"
                )
            index = specs.index(left)
            if op in ("in", "not in"):
                values = (
                    tuple(right) if isinstance(right, (list, set, frozenset)) else right
                )
                if isinstance(values, tuple) and not values:
                    return lambda row: op == "not in"
                return lambda row: (
                    None
                    if row[index] is None
                    else (row[index] in values) == (op == "in")
                )
            if op not in compare:
                raise ValueError(
                    f"Invalid having clause {item!r}: supported comparators are "
                    "('in', 'not in', '<', '>', '<=', '>=', '=', '!=')"
                )
            test = compare[op]
            return lambda row: (
                None if row[index] is None or right is None else test(row[index], right)
            )

        def negate(
            pred: typing.Callable[[tuple[typing.Any, ...]], typing.Any],
        ) -> typing.Callable[[tuple[typing.Any, ...]], typing.Any]:
            return lambda row: None if (v := pred(row)) is None else not v

        def both(
            a: typing.Callable[[tuple[typing.Any, ...]], typing.Any],
            b: typing.Callable[[tuple[typing.Any, ...]], typing.Any],
        ) -> typing.Callable[[tuple[typing.Any, ...]], typing.Any]:
            def pred(row: tuple[typing.Any, ...]) -> typing.Any:
                x, y = a(row), b(row)
                if x is False or y is False:
                    return False
                return None if x is None or y is None else True

            return pred

        def either(
            a: typing.Callable[[tuple[typing.Any, ...]], typing.Any],
            b: typing.Callable[[tuple[typing.Any, ...]], typing.Any],
        ) -> typing.Callable[[tuple[typing.Any, ...]], typing.Any]:
            def pred(row: tuple[typing.Any, ...]) -> typing.Any:
                x, y = a(row), b(row)
                if x is True or y is True:
                    return True
                return None if x is None or y is None else False

            return pred

        stack: list[typing.Callable[[tuple[typing.Any, ...]], typing.Any]] = []
        try:
            for item in reversed(having):
                if item == "!":
                    stack.append(negate(stack.pop()))
                elif item == "&":
                    stack.append(both(stack.pop(), stack.pop()))
                elif item == "|":
                    stack.append(either(stack.pop(), stack.pop()))
                elif isinstance(item, (list, tuple)) and len(item) == 3:
                    stack.append(condition(item))
                else:
                    raise ValueError(
                        f"Invalid having clause {item!r}: it should be a domain-like clause"
                    )
            while len(stack) > 1:
                stack.append(both(stack.pop(), stack.pop()))
            [predicate] = stack
        except IndexError:
            raise ValueError(f"Invalid having clause {having!r}") from None
        return predicate

    def _sort(self, rows: list[tuple[typing.Any, ...]], order: str | None) -> None:
        for index, rank, desc, nulls_first in reversed(self._order_terms(rows, order)):
            null_is_true = nulls_first == desc
            rows.sort(key=_get_sort_key(index, rank, null_is_true), reverse=desc)

    def _day_of_week_rank(self, spec: str) -> typing.Any:
        if parse_read_group_spec(spec)[2] != "day_of_week":
            return None
        week_start = int(get_lang(self.model.env).week_start)
        return lambda dow: (7 - week_start + dow) % 7

    def _order_terms(
        self, rows: list[tuple[typing.Any, ...]], order: str | None
    ) -> list[tuple[int, typing.Callable[[typing.Any], typing.Any] | None, bool, bool]]:
        if not order:
            return [
                (index, self._day_of_week_rank(spec), False, False)
                for index, spec in enumerate(self.groupby_specs)
            ]
        terms = []
        for order_part in order.split(","):
            match = regex_order_part_read_group.fullmatch(order_part)
            if not match:
                raise ValueError(f"Invalid order {order!r} for _read_group()")
            term = match["term"]
            desc = (match["direction"] or "asc").lower() == "desc"
            nulls = (match["nulls"] or "").lower()
            nulls_first = nulls == "nulls first" if nulls else desc
            rank = None
            if term in self.groupby_specs:
                index = self.groupby_specs.index(term)
                fname, seq_fnames, _granularity = parse_read_group_spec(term)
                rank = self._day_of_week_rank(term)
                field = self.model._fields[fname]
                if field.is_many2one and not seq_fnames:
                    comodel = self.model.env[field.comodel_name]
                    if comodel._order != "id":
                        ids = [row[index] for row in rows if row[index] is not None]
                        ordered = comodel.browse(ids).sorted(key=comodel._order)
                        positions = {
                            id_: position for position, id_ in enumerate(ordered._ids)
                        }
                        rank = positions.__getitem__
            elif term in self.aggregate_specs:
                index = len(self.groupby) + self.aggregate_specs.index(term)
            else:
                index = (
                    len(self.groupby)
                    + len(self.aggregate_specs)
                    + self.order_specs.index(term)
                )
            terms.append((index, rank, desc, nulls_first))
        return terms


def _order_within_grouping_set(
    order: str | None,
    present: typing.Sequence[str],
    aggregates: typing.Sequence[str],
    all_specs: typing.Sequence[str],
) -> str | None:
    if not order:
        return None
    kept = []
    for part in order.split(","):
        match = regex_order_part_read_group.fullmatch(part)
        if not match:
            raise ValueError(f"Invalid order {order!r} for _read_grouping_sets()")
        term = match["term"]
        if term in present or term in aggregates or term not in all_specs:
            kept.append(part.strip())
    return ", ".join(kept) or None


class InMemoryBackend(
    _InMemoryWriteMixin,
    _InMemoryReadMixin,
    _InMemoryHierarchyMixin,
    _InMemoryRelationsMixin,
):
    __slots__ = ("columns", "sequences", "storage")

    def __init__(self, storage: DictBackend) -> None:
        self.storage = storage
        self.sequences: SequenceStore = InMemorySequenceStore(storage)
        self.columns: ColumnStore = InMemoryColumnStore(storage)

    def timezone_names(self, env: Environment) -> frozenset[str]:
        return _python_timezone_names()

    def search_raw(
        self,
        model: ModelLike,
        domain: Domain,
        offset: int,
        limit: int | None,
        order: str | None,
        *,
        check_access: bool = True,
    ) -> Query | None:
        return None

    @staticmethod
    def _refuse_what_sql_cannot_compile(
        model: ModelLike, domain: Domain, order: str | None
    ) -> None:
        query = Query(model.env, model._table, model._table_sql)
        if not domain.is_true() and not _carries_a_python_predicate(domain):
            query.add_where(
                domain._to_sql(typing.cast("BaseModel", model), model._table, query)
            )
        if order:
            model._order_to_sql(order, query)

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
    ) -> Query:
        self._refuse_what_sql_cannot_compile(model, domain, order)
        searched_fnames = flush_search_dependencies(
            typing.cast("BaseModel", model), domain, order
        )
        sec_domain = (
            model.env.registry.access_policy.record_domain(
                model.env, model._name, "read"
            )
            if check_access
            else Domain.TRUE
        )
        if not sec_domain.is_true():
            flush_search_dependencies(typing.cast("BaseModel", model), sec_domain, None)
        cached_before = _cache_snapshot(model.env)
        all_ids = self.storage.get_table_ids(model._table)
        all_records = model.browse(all_ids)

        fields = model._fields
        self._load_column_cache(
            model,
            all_ids,
            [
                field
                for fname in searched_fnames.get(model._name, ())
                if (field := fields[fname]).column_type
            ],
            all_records,
        )

        if not domain.is_true():
            evaluated = all_records
            if check_access and not model.env.su:
                domain = _scope_to_reader(model, domain)
                evaluated = all_records.sudo()
            matching = model.browse(evaluated.filtered_domain(domain)._ids)
        else:
            matching = all_records

        if check_access:
            if not sec_domain.is_true():
                _debug.logic(
                    "backend.memory.rules_applied", model=model._name, uid=model.env.uid
                )
                allowed = (
                    matching.sudo()
                    .with_context(active_test=False)
                    .filtered_domain(sec_domain)
                )
                matching = model.browse(allowed._ids)

        if order:
            matching = matching.sorted(key=order)

        _drop_cache_additions(model.env, cached_before)

        query = _InMemoryQuery(model, self.storage, matching._ids)
        if limit is not None and limit is not False:
            query.limit = 1 if limit is True else limit
        if offset:
            query.offset = 1 if offset is True else offset
        _debug.pipeline(
            "backend.memory.search",
            model=model._name,
            scanned=len(all_ids),
            matched=len(matching),
            returned=len(query.get_result_ids()),
            ordered=bool(order),
            check_access=check_access,
        )
        return query

    def as_query(self, model: ModelLike, ordered: bool = True) -> Query:
        ids = model._ids if ordered else tuple(unique(model._ids))
        return _InMemoryQuery(model, self.storage, ids)

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
    ) -> list[tuple[typing.Any, ...]]:
        return _InMemoryReadGroup(
            model, domain, groupby, aggregates, self.storage
        ).rows(having, order, limit, offset)

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
    ) -> list[tuple[typing.Any, ...]]:
        all_specs = list(groupby_terms)
        mask_by_term = {
            term: 1 << index
            for index, term in enumerate(reversed(list(unique(groupby_terms.values()))))
        }
        rows: list[tuple[typing.Any, ...]] = []
        seen: set[frozenset[SQL]] = set()
        for grouping_set in grouping_sets:
            terms = frozenset(groupby_terms[spec] for spec in grouping_set)
            if terms in seen:
                continue
            seen.add(terms)
            present = [spec for spec in all_specs if groupby_terms[spec] in terms]
            mask = sum(m for term, m in mask_by_term.items() if term not in terms)
            set_order = _order_within_grouping_set(
                order, present, aggregates, all_specs
            )
            group = _InMemoryReadGroup(model, domain, present, aggregates, self.storage)
            for row in group.rows(None, set_order, None, 0):
                values = dict(zip(present, row[: len(present)], strict=True))
                rows.append(
                    (
                        mask,
                        *(values.get(spec) for spec in all_specs),
                        *row[len(present) :],
                    )
                )
        _debug.pipeline(
            "backend.memory.grouping_sets",
            model=model._name,
            sets=len(grouping_sets),
            groupby=len(all_specs),
            aggregates=len(aggregates),
            rows=len(rows),
        )
        return rows
