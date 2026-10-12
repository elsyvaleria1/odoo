from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.models import (
    READ_GROUP_NUMBER_GRANULARITY,
    READ_GROUP_TIME_GRANULARITY,
)
from odoo.tools import (
    DEFAULT_SERVER_DATE_FORMAT,
    DEFAULT_SERVER_DATETIME_FORMAT,
    get_lang,
    unique,
)


def AND(domains: Iterable[Any]) -> list[Any]:
    return list(Domain.AND(domains))


def OR(domains: Iterable[Any]) -> list[Any]:
    return list(Domain.OR(domains))


def _get_display_name_visible_ids(values: Iterable[Any]) -> set[int]:
    first = None
    ids: dict[int, None] = {}
    for value in values:
        if value:
            first = first if first is not None else value
            ids.update(dict.fromkeys(value._ids))
    if first is None:
        return set()
    records = first.browse(list(ids)).with_prefetch(first._prefetch_ids)
    return set(records._filtered_display_name_access()._ids)


class Base(models.AbstractModel):
    _inherit = "base"

    def _web_read_group_get_field_expand(
        self, groupby: Sequence[str]
    ) -> fields.Field | None:
        if (
            len(groupby) == 1
            and self.env.context.get("read_group_expand")
            and "." not in groupby[0]
            and (field := self._fields[groupby[0].split(":")[0]])
            and field.group_expand
        ):
            return field
        return None

    def _web_read_group_expand(
        self,
        domain: Any,
        groups: list[tuple[Any, ...]],
        groupby_spec: str,
        aggregates: tuple[str, ...],
        order: str,
    ) -> list[tuple[Any, ...]]:
        field_name = groupby_spec.split(".", maxsplit=1)[0].split(":", maxsplit=1)[0]
        field = self._fields[field_name]

        values = [group_value for group_value, *__ in groups if group_value]

        if field.relational:
            values = self.env[field.comodel_name].browse(value.id for value in values)
            expand_values = field.get_expanded_groups(self, values, domain)
            all_record_ids = tuple(unique(expand_values._ids + values._ids))
        else:
            expand_values = field.get_expanded_groups(self, values, domain)

        is_desc = any(
            parts[0] == groupby_spec.lower() and len(parts) > 1 and parts[1] == "desc"
            for part in order.lower().split(",")
            if (parts := part.strip().split())
        )
        if is_desc:
            expand_values = reversed(expand_values)

        empty_aggregates = tuple(
            self._read_group_empty_value(spec) for spec in aggregates
        )
        result = dict.fromkeys(expand_values, empty_aggregates)
        result.update(
            {group_value: aggregate_values for group_value, *aggregate_values in groups}
        )

        if field.relational:
            return [
                (value.with_prefetch(all_record_ids), *aggregate_values)
                for value, aggregate_values in result.items()
            ]
        return [
            (value, *aggregate_values) for value, aggregate_values in result.items()
        ]

    @api.model
    def _web_read_group_fill_temporal(
        self,
        groups: list[tuple[Any, ...]],
        groupby: Sequence[str],
        aggregates: Sequence[str],
        fill_from: str | bool = False,
        fill_to: str | bool = False,
        min_groups: int | bool = False,
    ) -> list[tuple[Any, ...]]:
        groupby_name = groupby[0]
        if ":" not in groupby_name:
            return groups
        granularity = groupby_name.split(":")[1]
        if granularity not in READ_GROUP_TIME_GRANULARITY:
            return groups
        is_datetime = self._read_group_temporal_is_datetime(groupby_name)
        if is_datetime is None:
            return groups
        days_offset = 0
        if granularity == "week":
            first_week_day = int(get_lang(self.env).week_start) - 1
            days_offset = first_week_day and 7 - first_week_day
        existing = sorted(
            group_value for group in groups if (group_value := group[0])
        ) or [None]
        fill_from, fill_to = self._web_read_group_get_temporal_bounds(
            is_datetime, granularity, days_offset, existing, fill_from, fill_to
        )
        if not fill_from and not fill_to:
            return groups

        interval = READ_GROUP_TIME_GRANULARITY[granularity]
        if min_groups > 0:
            fill_to = max(fill_to, fill_from + (min_groups - 1) * interval)

        if fill_from > fill_to:
            return groups

        empty_item = tuple(
            self._read_group_empty_value(spec) for spec in (*groupby[1:], *aggregates)
        )
        required_dates = list(
            self._read_group_period_starts(fill_from, fill_to, granularity, interval)
        )

        if existing[0] is None:
            existing = list(required_dates)
        else:
            existing = sorted(set().union(existing, required_dates))

        groups_mapped = defaultdict(list)
        for group in groups:
            groups_mapped[group[0]].append(group)

        result = []
        for dt in existing:
            if dt in groups_mapped:
                result.extend(groups_mapped[dt])
            else:
                result.append((dt, *empty_item))

        if False in groups_mapped:
            result.extend(groups_mapped[False])

        return result

    def _web_read_group_get_temporal_bounds(
        self,
        is_datetime: bool,
        granularity: str,
        days_offset: int,
        existing: list[Any],
        fill_from: Any,
        fill_to: Any,
    ) -> tuple[Any, Any]:
        existing_from, existing_to = existing[0], existing[-1]

        if fill_from:
            fill_from = self._read_group_fill_temporal_bound(
                is_datetime, granularity, days_offset, fill_from
            )
        elif existing_from:
            fill_from = existing_from
        if fill_to:
            fill_to = self._read_group_fill_temporal_bound(
                is_datetime, granularity, days_offset, fill_to
            )
        elif existing_to:
            fill_to = existing_to

        if not fill_to and fill_from:
            fill_to = fill_from
        elif not fill_from and fill_to:
            fill_from = fill_to
        return fill_from, fill_to

    def _web_read_group_get_groupby_formatter(
        self, groupby_spec: str, values: Any
    ) -> Callable[[Any], tuple[Any, list[Any]]]:
        field_path = groupby_spec.split(":", maxsplit=1)[0]
        field_name, _dot, remaining_path = field_path.partition(".")
        field = self._fields[field_name]

        if remaining_path and field.type == "many2one":
            model = self.env[field.comodel_name]
            sub_formatter = model._web_read_group_get_groupby_formatter(
                groupby_spec.split(".", 1)[1], values
            )

            def formatter_follow_many2one(value: Any) -> tuple[Any, list[Any]]:
                value, domain = sub_formatter(value)
                if not value:
                    return value, [
                        "|",
                        (field_name, "not any", []),
                        (field_name, "any", domain),
                    ]
                return value, [(field_name, "any", domain)]

            return formatter_follow_many2one

        if field.type == "many2many":
            visible_ids = _get_display_name_visible_ids(values)

            def formatter_many2many(value: Any) -> tuple[Any, list[Any]]:
                if not value:
                    return False, [(field_name, "not any", [])]
                id_ = value.id
                name = value.sudo().display_name if id_ in visible_ids else ""
                return (id_, name), [(field_name, "=", id_)]

            return formatter_many2many

        if field.type == "many2one" or field_name == "id":
            visible_ids = _get_display_name_visible_ids(values)

            def formatter_many2one(value: Any) -> tuple[Any, list[Any]]:
                if not value:
                    return False, [(field_name, "=", False)]
                id_ = value.id
                name = value.sudo().display_name if id_ in visible_ids else ""
                return (id_, name), [(field_name, "=", id_)]

            return formatter_many2one

        if field.type in ("date", "datetime"):
            return self._web_read_group_get_date_formatter(
                field, field_name, groupby_spec
            )

        if field.type == "properties":
            return self._web_read_group_get_groupby_formatter_properties(
                groupby_spec, values
            )

        return lambda value: (value, [(field_name, "=", value)])

    def _web_read_group_get_date_formatter(
        self, field: fields.Field, field_name: str, groupby_spec: str
    ) -> Callable[[Any], tuple[Any, list[Any]]]:
        if ":" not in groupby_spec:
            raise ValueError(
                f"Granularity is missing from date/datetime groupby: {groupby_spec!r}"
            )
        return self._web_read_group_get_temporal_formatter(
            field_name, field.type == "datetime", groupby_spec.split(":")[1]
        )

    def _web_read_group_get_temporal_formatter(
        self, field_name: str, is_datetime: bool, granularity: str
    ) -> Callable[[Any], tuple[Any, list[Any]]]:
        if granularity in READ_GROUP_NUMBER_GRANULARITY:

            def formatter_date_number_granularity(value: Any) -> tuple[Any, list[Any]]:
                if value is None:
                    return None, [(field_name, "=", value)]
                return value, [(f"{field_name}.{granularity}", "=", value)]

            return formatter_date_number_granularity

        if granularity not in READ_GROUP_TIME_GRANULARITY:
            raise ValueError(f"{granularity!r} isn't a valid granularity")

        locale = get_lang(self.env).code
        fmt = (
            DEFAULT_SERVER_DATETIME_FORMAT
            if is_datetime
            else DEFAULT_SERVER_DATE_FORMAT
        )
        interval = READ_GROUP_TIME_GRANULARITY[granularity]

        def formatter_time_granularity(value: Any) -> tuple[Any, list[Any]]:
            if not value:
                return value, [(field_name, "=", value)]
            label, start, spans = self._read_group_temporal_range(
                value, is_datetime, interval, granularity, locale, fmt
            )
            return (start, label), list(
                self._read_group_temporal_domain(field_name, spans)
            )

        return formatter_time_granularity

    def _web_read_group_get_groupby_formatter_properties(
        self,
        groupby_spec: str,
        values: Any,
    ) -> Callable[[Any], tuple[Any, list[Any]]]:
        if "." not in groupby_spec:
            msg = "You must choose the property you want to group by."
            raise ValueError(msg)

        fullname, __, func = groupby_spec.partition(":")
        definition = self.get_property_definition(fullname)
        property_type = definition.get("type")
        if property_type == "selection":
            options = definition.get("selection") or []
            options = tuple(option[0] for option in options)

            def formatter_property_selection(value: Any) -> tuple[Any, list[Any]]:
                if not value:
                    return value, [
                        "|",
                        (fullname, "=", False),
                        (fullname, "not in", options),
                    ]
                return value, [(fullname, "=", value)]

            return formatter_property_selection

        if property_type in ("many2one", "many2many"):
            return self._web_read_group_get_property_relational_formatter(
                fullname, definition, property_type, values
            )

        if property_type == "tags":
            tags = definition.get("tags") or []
            tags = {tag[0]: tuple(tag) for tag in tags}

            def formatter_property_tags(value: Any) -> tuple[Any, list[Any]]:
                if not value:
                    return value, (
                        OR(
                            [
                                [(fullname, "=", False)],
                                AND([[(fullname, "not in", [tag])] for tag in tags]),
                            ]
                        )
                        if tags
                        else []
                    )

                return tags.get(value), [(fullname, "in", [value])]

            return formatter_property_tags

        if property_type in ("date", "datetime"):
            return self._web_read_group_get_property_date_formatter(
                fullname, property_type, func
            )

        return lambda value: (value, [(fullname, "=", value)])

    def _web_read_group_get_property_relational_formatter(
        self, fullname: str, definition: dict[str, Any], property_type: str, values: Any
    ) -> Callable[[Any], tuple[Any, list[Any]]]:
        comodel = definition["comodel"]
        all_groups = tuple(value for value in values if value)

        if property_type == "many2one":

            def formatter_property_many2one(value: Any) -> tuple[Any, list[Any]]:
                if not value:
                    return value, [
                        "|",
                        (fullname, "=", False),
                        (fullname, "not in", all_groups),
                    ]
                record = self.env[comodel].browse(value).with_prefetch(all_groups)
                return (value, record.display_name), [(fullname, "=", value)]

            return formatter_property_many2one

        def formatter_property_many2many(value: Any) -> tuple[Any, list[Any]]:
            if not value:
                return value, (
                    OR(
                        [
                            [(fullname, "=", False)],
                            AND(
                                [
                                    [(fullname, "not in", [group])]
                                    for group in all_groups
                                ]
                            ),
                        ]
                    )
                    if all_groups
                    else []
                )
            record = self.env[comodel].browse(value).with_prefetch(all_groups)
            return (value, record.display_name), [(fullname, "in", [value])]

        return formatter_property_many2many

    def _web_read_group_get_property_date_formatter(
        self, fullname: str, property_type: str, func: str
    ) -> Callable[[Any], tuple[Any, list[Any]]]:
        formatter = self._web_read_group_get_temporal_formatter(
            fullname, property_type == "datetime", func
        )
        if func in READ_GROUP_NUMBER_GRANULARITY:
            return formatter

        no_date = self._read_group_property_date_domain(fullname, has_date=False)
        has_date = self._read_group_property_date_domain(fullname, has_date=True)

        def formatter_property_temporal(value: Any) -> tuple[Any, list[Any]]:
            if not value:
                return False, list(no_date)
            group_value, domain = formatter(value)
            return group_value, list(has_date & Domain(domain))

        return formatter_property_temporal
