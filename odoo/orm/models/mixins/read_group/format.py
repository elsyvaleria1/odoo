import datetime
import logging
import typing

import babel
import babel.dates

from odoo.libs.datetime import (
    all_timezones,
    wall_range_to_utc,
    weeknumber,
)
from odoo.libs.datetime import timezone as get_timezone
from odoo.libs.debug_log import DebugLog
from odoo.libs.iteration import unique
from odoo.tools import (
    DEFAULT_SERVER_DATE_FORMAT,
    DEFAULT_SERVER_DATETIME_FORMAT,
    get_lang,
)

from .... import fields
from ...._recordset import is_recordset
from ....constants import (
    READ_GROUP_DISPLAY_FORMAT,
    READ_GROUP_NUMBER_GRANULARITY,
    READ_GROUP_TIME_GRANULARITY,
)
from ....domain import Domain
from ....parsing import parse_read_group_spec
from ._empty import _ReadGroupEmptyMixin

if typing.TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    from ...._typing import IdType
    from ....fields.base import Field
    from ...base import BaseModel

_debug = DebugLog(__name__)
_logger = logging.getLogger("odoo.models")

# an aggregate over a non-stored field computes the field on every record of
# every group, collapsed or not; past this many it is worth storing the field
_THROUGH_RECORDS_WARNING = 5000

_FOLD_COUNTS: dict[str, typing.Callable[[list[typing.Any]], int]] = {
    "count": len,
    "count_distinct": lambda values: len(set(values)),
}
_FOLD_VALUES: dict[str, typing.Callable[[list[typing.Any]], typing.Any]] = {
    "sum": sum,
    "avg": lambda values: sum(values) / len(values),
    "min": min,
    "max": max,
    "bool_and": all,
    "bool_or": any,
}


def _sorted_distinct(values: typing.Iterable[typing.Any]) -> list[typing.Any]:
    distinct = set(values)
    has_none = None in distinct
    distinct.discard(None)
    return [*sorted(distinct), *([None] if has_none else [])]


class _ReadGroupFormatMixin(_ReadGroupEmptyMixin):
    __slots__ = ()

    def _read_group_postprocess_groupby(
        self, groupby_spec: str, raw_values: Sequence[typing.Any]
    ) -> Generator[typing.Any]:
        empty_value = self._read_group_empty_value(groupby_spec)

        fname, chain_fnames, granularity = parse_read_group_spec(groupby_spec)
        field = self._fields[fname]

        if field.relational or fname == "id":
            if chain_fnames and field.relational:
                groupby_seq = (
                    f"{chain_fnames}:{granularity}" if granularity else chain_fnames
                )
                model = self.env[field.comodel_name]
                _debug.logic(
                    "read_group.postprocess.chained_groupby",
                    model=self._name,
                    groupby=groupby_spec,
                    comodel=model._name,
                    values=len(raw_values),
                )
                return model._read_group_postprocess_groupby(groupby_seq, raw_values)

            registry = self.env.registry
            Model = (
                registry[field.comodel_name]
                if field.relational
                else registry[self._name]
            )
            prefetch_ids = tuple(raw_value for raw_value in raw_values if raw_value)

            def recordset(value: typing.Any) -> typing.Any:
                return Model(self.env, (value,), prefetch_ids) if value else empty_value

            return (recordset(value) for value in raw_values)

        return ((value if value is not None else empty_value) for value in raw_values)

    def _read_group_postprocess_aggregate(
        self, aggregate_spec: str, raw_values: Sequence[typing.Any]
    ) -> Generator[typing.Any]:
        empty_value = self._read_group_empty_value(aggregate_spec)

        if aggregate_spec == "__count":
            return (
                (value if value is not None else empty_value) for value in raw_values
            )

        fname, __, func = parse_read_group_spec(aggregate_spec)
        field = self._fields.get(fname)
        if (
            field is not None
            and func is not None
            and self._aggregates_through_records(field, func)
        ):
            return self._read_group_fold_through_records(
                field, func, raw_values, empty_value
            )
        if func == "recordset":
            field = self._fields[fname]
            _debug.logic(
                "read_group.postprocess.recordset_aggregate",
                model=self._name,
                aggregate=aggregate_spec,
                comodel=field.comodel_name if field.relational else self._name,
                rows=len(raw_values),
            )
            registry = self.env.registry
            Model = (
                registry[field.comodel_name]
                if field.relational
                else registry[self._name]
            )
            prefetch_ids = tuple(
                unique(
                    id_
                    for array_values in raw_values
                    if array_values
                    for id_ in array_values
                    if id_
                )
            )

            def recordset(value: typing.Any) -> typing.Any:
                if not value:
                    return empty_value
                ids = tuple(unique(id_ for id_ in value if id_))
                return Model(self.env, ids, prefetch_ids)

            return (recordset(value) for value in raw_values)

        return ((value if value is not None else empty_value) for value in raw_values)

    def _read_group_fold_through_records(
        self,
        field: Field[typing.Any],
        func: str,
        raw_values: Sequence[typing.Any],
        empty_value: typing.Any,
    ) -> Generator[typing.Any]:
        Model = self.env.registry[self._name]
        prefetch_ids = tuple(
            unique(id_ for ids in raw_values if ids for id_ in ids if id_)
        )
        if func == "sum_currency":
            currency_field = self._fields[field._get_currency_field_name(self)]
            to_currency = self.env.company.currency_id
            today = fields.Date.context_today(typing.cast("BaseModel", self))

        def value_of(record: BaseModel) -> typing.Any:
            value = record[field.name]
            if field.is_boolean:
                return value
            if field.is_many2one:
                # the SQL tier aggregates the column, which holds the id
                return value.id or None
            return None if value is False else value

        def present(records: BaseModel) -> list[typing.Any]:
            return [v for v in (value_of(r) for r in records) if v is not None]

        _debug.logic(
            "read_group.postprocess.through_records",
            model=self._name,
            field=field.name,
            func=func,
            records=len(prefetch_ids),
            groups=len(raw_values),
        )
        if len(prefetch_ids) > _THROUGH_RECORDS_WARNING:
            _logger.warning(
                "%s:%s is computed on %d %s records to aggregate it; "
                "store the field or drop the aggregate from the view",
                field,
                func,
                len(prefetch_ids),
                self._name,
            )

        def fold(ids: typing.Any) -> typing.Any:
            if not ids:
                return empty_value
            records = Model(self.env, tuple(unique(i for i in ids if i)), prefetch_ids)
            if func == "sum_currency":
                total = 0.0
                for record in records:
                    amount = value_of(record)
                    if amount is None:
                        continue
                    currency = record[currency_field.name]
                    total += (
                        currency._convert(
                            from_amount=amount,
                            to_currency=to_currency,
                            company=self.env.company,
                            date=today,
                        )
                        if currency and currency != to_currency
                        else amount
                    )
                return total
            if func == "array_agg":
                return [value_of(r) for r in records] or empty_value
            if func == "array_agg_distinct":
                return _sorted_distinct(value_of(r) for r in records) or empty_value
            values = present(records)
            if func in _FOLD_COUNTS:
                return _FOLD_COUNTS[func](values)
            if not values:
                return empty_value
            if func in _FOLD_VALUES:
                return _FOLD_VALUES[func](values)
            raise ValueError(f"Aggregate method {func!r} cannot fold {field}")

        return (fold(ids) for ids in raw_values)

    def _read_group_temporal_range(
        self,
        value: typing.Any,
        is_datetime: bool,
        interval: typing.Any,
        granularity: str,
        locale: str,
        fmt: str,
    ) -> tuple[
        str, str, list[tuple[str | typing.Literal[False], str | typing.Literal[False]]]
    ]:
        # the label, the group's own start, and the spans its domain covers:
        # a span may be open at either end of the calendar
        opens_before_calendar = False
        try:
            if granularity == "week":
                # to the next week's first day: a week held to 0001-01-01 is
                # shorter than seven days, and the calendar's first week is no
                # bound below -- whatever reads before year 1 (a local time
                # west of UTC, -infinity) is held into it too
                first_week_day = int(get_lang(self.env).week_start) - 1
                opens_before_calendar = (value.year, value.month, value.day) == (
                    1,
                    1,
                    1,
                )
                end = value + datetime.timedelta(
                    days=7 - (value.weekday() - first_week_day) % 7
                )
            else:
                end = value + interval
        except OverflowError, ValueError:
            # the last period of year 9999 ends past the calendar: open
            end = None
        spans: Sequence[tuple[datetime.date, datetime.date | None]] = [(value, end)]
        if is_datetime:
            assert isinstance(value, datetime.datetime)
            if self.env.context.get("tz") in all_timezones():
                spans = wall_range_to_utc(
                    value, end, get_timezone(self.env.context["tz"])
                )
        if granularity == "week":
            # babel's own week-year reads past year 9999 at the calendar's end
            year, week = weeknumber(babel.Locale.parse(locale), value)
            label = f"W{week} {year:04}"
        elif is_datetime:
            label = babel.dates.format_datetime(
                value,
                format=READ_GROUP_DISPLAY_FORMAT[granularity],
                locale=locale,
            )
        else:
            label = babel.dates.format_date(
                value,
                format=READ_GROUP_DISPLAY_FORMAT[granularity],
                locale=locale,
            )
        bounds: list[
            tuple[str | typing.Literal[False], str | typing.Literal[False]]
        ] = [
            (start.strftime(fmt), end.strftime(fmt) if end is not None else False)
            for start, end in spans
        ]
        group_start = bounds[0][0]
        assert group_start
        if opens_before_calendar:
            bounds[0] = (False, bounds[0][1])
        return label, group_start, bounds

    @staticmethod
    def _read_group_property_date_domain(fullname: str, has_date: bool) -> Domain:
        # a value no date reads ('hello', '2024-02-30' written under another
        # definition) is counted in the empty group: "= False" would not find
        # it again, and a date group's text range could
        return Domain(f"{fullname}.year_number", "!=" if has_date else "=", False)

    @staticmethod
    def _read_group_temporal_domain(
        field_expr: str,
        spans: list[tuple[str | typing.Literal[False], str | typing.Literal[False]]],
    ) -> Domain:
        return Domain.OR(
            (Domain(field_expr, ">=", start) if start else Domain.TRUE)
            & (Domain(field_expr, "<", end) if end else Domain.TRUE)
            for start, end in spans
        )

    def _read_group_format_result(
        self, rows_dict: list[dict[str, typing.Any]], lazy_groupby: list[str]
    ) -> None:
        for group in lazy_groupby:
            field_name = group.split(":")[0].split(".")[0]
            field = self._fields[field_name]

            if field.is_temporal:
                granularity = group.split(":")[1] if ":" in group else "month"
                if granularity in READ_GROUP_TIME_GRANULARITY:
                    locale = get_lang(self.env).code
                    fmt = (
                        DEFAULT_SERVER_DATETIME_FORMAT
                        if field.is_datetime
                        else DEFAULT_SERVER_DATE_FORMAT
                    )
                    interval = READ_GROUP_TIME_GRANULARITY[granularity]
            elif field.is_properties:
                self._read_group_format_result_properties(rows_dict, group)
                continue

            # a group names only the records the reader may see named, as
            # read() and web_read_group do; the id stays, the group's domain
            # needs it. Expanded groups arrive sudo, so the check takes the
            # reader's env, not a row's
            values = [
                row[group]
                for row in rows_dict
                if is_recordset(row[group]) and row[group]
            ]
            named: set[IdType] = set()
            if values:
                targets = values[0].with_env(self.env).browse().union(*values)
                named = set(targets._filtered_display_name_access()._ids)

            for row in rows_dict:
                value = row[group]

                if is_recordset(value):
                    row[group] = (
                        (
                            value.id,
                            value.sudo().display_name if value.id in named else "",
                        )
                        if value
                        else False
                    )
                    value = value.id

                additional_domain: list[object]
                if not value and field.is_many2many:
                    additional_domain = [(field_name, "not any", [])]
                else:
                    additional_domain = [(field_name, "=", value)]

                if field.is_temporal:
                    if value and isinstance(value, datetime.date):
                        label, start, spans = self._read_group_temporal_range(
                            value,
                            field.is_datetime,
                            interval,
                            granularity,
                            locale,
                            fmt,
                        )
                        row[group] = label
                        row.setdefault("__range", {})[group] = {
                            "from": start,
                            "to": spans[-1][1],
                        }
                        additional_domain = list(
                            self._read_group_temporal_domain(field_name, spans)
                        )
                    elif (
                        value is not None
                        and granularity in READ_GROUP_NUMBER_GRANULARITY
                    ):
                        additional_domain = [
                            (f"{field_name}.{granularity}", "=", value)
                        ]
                    elif not value:
                        row.setdefault("__range", {})[group] = False

                row["__domain"] &= Domain(additional_domain)
        for row in rows_dict:
            row["__domain"] = list(row["__domain"])
        _debug.pipeline(
            "read_group.formatted",
            model=self._name,
            rows=len(rows_dict),
            groups=len(lazy_groupby),
        )

    def _format_properties_selection(
        self,
        rows_dict: list[dict[str, typing.Any]],
        fullname: str,
        definition: dict[str, typing.Any],
    ) -> None:
        options = definition.get("selection") or []
        options = tuple(option[0] for option in options)
        for row in rows_dict:
            if not row[fullname]:
                additional_domain = Domain(fullname, "=", False) | Domain(
                    fullname, "not in", options
                )
            else:
                additional_domain = Domain(fullname, "=", row[fullname])

            row["__domain"] &= additional_domain

    def _format_properties_many2one(
        self,
        rows_dict: list[dict[str, typing.Any]],
        fullname: str,
        definition: dict[str, typing.Any],
    ) -> None:
        comodel = self.env[typing.cast("str", definition.get("comodel"))]
        prefetch_ids = all_groups = tuple(
            row[fullname] for row in rows_dict if row[fullname]
        )
        for row in rows_dict:
            if not row[fullname]:
                additional_domain = Domain(fullname, "=", False) | Domain(
                    fullname, "not in", all_groups
                )
            else:
                additional_domain = Domain(fullname, "=", row[fullname])
                record = comodel.browse(row[fullname]).with_prefetch(prefetch_ids)
                row[fullname] = (row[fullname], record.display_name)

            row["__domain"] &= additional_domain

    def _format_properties_many2many(
        self,
        rows_dict: list[dict[str, typing.Any]],
        fullname: str,
        definition: dict[str, typing.Any],
    ) -> None:
        comodel = self.env[typing.cast("str", definition.get("comodel"))]
        prefetch_ids = all_groups = tuple(
            row[fullname] for row in rows_dict if row[fullname]
        )
        for row in rows_dict:
            if not row[fullname]:
                if all_groups:
                    additional_domain = Domain(fullname, "=", False) | Domain.AND(
                        [(fullname, "not in", group)] for group in all_groups
                    )
                else:
                    additional_domain = Domain.TRUE
            else:
                additional_domain = Domain(fullname, "in", row[fullname])
                record = comodel.browse(row[fullname]).with_prefetch(prefetch_ids)
                row[fullname] = (row[fullname], record.display_name)

            row["__domain"] &= additional_domain

    def _format_properties_tags(
        self,
        rows_dict: list[dict[str, typing.Any]],
        fullname: str,
        definition: dict[str, typing.Any],
    ) -> None:
        tags = definition.get("tags") or []
        tags = {tag[0]: tag for tag in tags}
        for row in rows_dict:
            if not row[fullname]:
                if tags:
                    additional_domain = Domain(fullname, "=", False) | Domain.AND(
                        [(fullname, "not in", tag)] for tag in tags
                    )
                else:
                    additional_domain = Domain.TRUE
            else:
                additional_domain = Domain(fullname, "in", row[fullname])
                row[fullname] = tags.get(row[fullname])

            row["__domain"] &= additional_domain

    def _format_properties_temporal(
        self,
        rows_dict: list[dict[str, typing.Any]],
        fullname: str,
        group: str,
        property_type: str,
        func: str,
    ) -> None:
        granularity = func or "month"
        if granularity in READ_GROUP_NUMBER_GRANULARITY:
            for row in rows_dict:
                row["__domain"] &= Domain(f"{fullname}.{granularity}", "=", row[group])
            return

        is_datetime = property_type == "datetime"
        locale = get_lang(self.env).code
        fmt = (
            DEFAULT_SERVER_DATETIME_FORMAT
            if is_datetime
            else DEFAULT_SERVER_DATE_FORMAT
        )
        interval = READ_GROUP_TIME_GRANULARITY[granularity]
        for row in rows_dict:
            if not row[group]:
                row[group] = False
                row["__domain"] &= self._read_group_property_date_domain(
                    fullname, has_date=False
                )
                row.setdefault("__range", {})[group] = False
                continue

            label, start, spans = self._read_group_temporal_range(
                row[group], is_datetime, interval, granularity, locale, fmt
            )
            row["__domain"] &= self._read_group_property_date_domain(
                fullname, has_date=True
            ) & self._read_group_temporal_domain(fullname, spans)
            row.setdefault("__range", {})[group] = {
                "from": start,
                "to": spans[-1][1],
            }
            row[group] = label

    def _read_group_format_result_properties(
        self, rows_dict: list[dict[str, typing.Any]], group: str
    ) -> None:
        if "." not in group:
            msg = "You must choose the property you want to group by."
            raise ValueError(msg)
        fullname, __, func = group.partition(":")

        definition = self.get_property_definition(fullname)
        property_type = definition.get("type")

        _debug.logic(
            "read_group.format.property",
            model=self._name,
            groupby=group,
            property_type=property_type,
            rows=len(rows_dict),
        )
        if property_type == "selection":
            self._format_properties_selection(rows_dict, fullname, definition)
        elif property_type == "many2one":
            self._format_properties_many2one(rows_dict, fullname, definition)
        elif property_type == "many2many":
            self._format_properties_many2many(rows_dict, fullname, definition)
        elif property_type == "tags":
            self._format_properties_tags(rows_dict, fullname, definition)
        elif property_type in ("date", "datetime"):
            self._format_properties_temporal(
                rows_dict, fullname, group, property_type, func
            )
        else:
            for row in rows_dict:
                row["__domain"] &= Domain(fullname, "=", row[fullname])
