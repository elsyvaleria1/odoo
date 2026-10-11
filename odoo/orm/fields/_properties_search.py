import typing
from collections import abc
from collections.abc import Set as AbstractSet
from datetime import date, datetime
from typing import override

from odoo.libs.collections import OrderedSet
from odoo.libs.datetime import all_timezones
from odoo.libs.datetime import timezone as get_timezone
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.sql import SQL

from .._recordset import is_recordset
from ..domain import Domain
from ..domain.ast import DomainCondition, OptimizationLevel
from ..parsing import parse_field_expr
from ..primitives import COLLECTION_TYPES, SQL_OPERATORS
from ._field_sql import PYTHON_INEQUALITY_OPERATOR
from ._property_values import (
    RELATIONAL_PROPERTY_TYPES,
    _temporal_property_range_sql,
    _temporal_type_of,
    check_property_field_value_name,
    local_temporal_property,
    parse_temporal_property,
    render_temporal_property,
    split_temporal_part,
    temporal_property_bound,
    temporal_property_sql,
    temporal_property_text_sql,
    temporal_property_type,
)
from .base import Field
from .temporal import (
    _value_to_date,
    _value_to_datetime,
    refuse_boolean_part_comparand,
    temporal_part_getter,
)

if typing.TYPE_CHECKING:
    from odoo.tools import Query

    from .._typing import ModelLike
    from ..models import BaseModel
    from .properties import Property

    _PropertiesMixinBase = Field[Property]
else:
    _PropertiesMixinBase = object

_debug = DebugLog("odoo.orm.fields.properties")


def _optimize_property_temporal_comparand(
    condition: DomainCondition, model: BaseModel
) -> Domain:
    operator = condition.operator
    if (
        operator not in ("in", "not in", ">", "<", ">=", "<=")
        or condition.field_expr.count(".") != 1
        or not isinstance(condition.value, (str, date, AbstractSet))
    ):
        return condition
    definition = model.get_property_definition(condition.field_expr)
    property_type = definition.get("type")

    value: object
    if property_type == "date":
        value = _value_to_date(condition.value, model.env)
    elif property_type == "datetime":
        value, _ = _value_to_datetime(condition.value, model.env)
    elif operator in ("in", "not in") and isinstance(condition.value, AbstractSet):
        if not any(isinstance(item, date) for item in condition.value):
            return condition
        value = OrderedSet(
            render_temporal_property(item, _temporal_type_of(item))
            if isinstance(item, date)
            else item
            for item in condition.value
        )
        property_type = "text"
    else:
        return condition
    if isinstance(value, COLLECTION_TYPES):
        value = OrderedSet(
            render_temporal_property(item, property_type)
            if isinstance(item, date)
            else item
            for item in value
        )
    elif isinstance(value, date):
        value = (
            render_temporal_property(value, property_type)
            if operator in ("in", "not in")
            else temporal_property_bound(value)
        )

    _debug.logic(
        "field.properties.temporal_comparand",
        model=model._name,
        field_expr=condition.field_expr,
        operator=operator,
        property_type=property_type,
    )
    return DomainCondition(condition.field_expr, operator, value)


def _is_unset(value: typing.Any) -> bool:
    return (
        value is False
        or value is None
        or (type(value) is list and not value)
        or (is_recordset(value) and not value)
    )


def _same_value(domain_value: typing.Any, value: typing.Any) -> bool:
    return domain_value == value and isinstance(domain_value, bool) is isinstance(
        value, bool
    )


def _unset_property_sql(raw_sql_field: SQL, property_name: str) -> tuple[SQL, SQL]:
    return (
        SQL("%s IS NULL", raw_sql_field),
        SQL("NOT (%s ? %s)", raw_sql_field, property_name),
    )


class _PropertiesSearchMixin(_PropertiesMixinBase):
    __slots__ = ()

    if typing.TYPE_CHECKING:

        def _get_properties_definition(
            self, record: ModelLike
        ) -> list[dict[str, typing.Any]] | None: ...

    @override
    def _optimize_condition(
        self, condition: DomainCondition, model: BaseModel, level: OptimizationLevel
    ) -> Domain:
        if level == OptimizationLevel.BASIC:
            _fname, property_name = parse_field_expr(condition.field_expr)
            if property_name:
                name, part = split_temporal_part(property_name)
                check_property_field_value_name(name)
                refuse_boolean_part_comparand(condition, part)
            if condition.operator in PYTHON_INEQUALITY_OPERATOR and (
                condition.value is False or condition.value is None
            ):
                _debug.logic(
                    "field.properties.unset_comparand_ordered",
                    model=model._name,
                    field_expr=condition.field_expr,
                    operator=condition.operator,
                )
                return Domain.FALSE
            return condition
        if level != OptimizationLevel.DYNAMIC_VALUES:
            return condition
        return _optimize_property_temporal_comparand(condition, model)

    @override
    def get_expression_getter(self, field_expr: str) -> typing.Any:
        _fname, property_name = parse_field_expr(field_expr)
        if not property_name:
            raise ValueError(f"Missing property name for {self}")
        name, part = split_temporal_part(property_name)
        if part is not None:
            return self._get_temporal_part_getter(name, part)

        def get_property(record: BaseModel) -> typing.Any:
            property_value = self.__get__(
                record.with_context(property_selection_get_key=True)
            )
            value = property_value.get(property_name)
            if value:
                return value
            for definition in self._get_properties_definition(record) or ():
                if definition.get("name") == property_name:
                    break
            else:
                return value or False

            if not value and definition["type"] in RELATIONAL_PROPERTY_TYPES:
                comodel = definition.get("comodel")
                return record.env.get(comodel) if comodel else None
            return value

        return get_property

    def _get_temporal_part_getter(self, name: str, part: str) -> typing.Any:
        resolved: list[tuple[str, typing.Any]] = []

        def getter(record: BaseModel) -> typing.Any:
            if not resolved:
                property_type = temporal_property_type(
                    record.browse(), f"{self.name}.{name}", part
                )
                resolved.append(
                    (
                        property_type,
                        temporal_part_getter(
                            part, is_datetime=property_type == "datetime"
                        ),
                    )
                )
            property_type, get_part = resolved[0]
            raw = (self.__get__(record)._values or {}).get(name)
            value = parse_temporal_property(raw, property_type)
            if value is None:
                return False
            if (
                isinstance(value, datetime)
                and (tz_name := record.env.context.get("tz"))
                and tz_name in all_timezones()
            ):
                value = local_temporal_property(value, get_timezone(tz_name))
                if value is None:
                    return False
            return get_part(value)

        return getter

    @override
    def filter_function(
        self, records: BaseModel, field_expr: str, operator: str, value: typing.Any
    ) -> typing.Any:
        getter = self.get_expression_getter(field_expr)
        _debug.logic(
            "field.properties.filter_function",
            model=self.model_name,
            field_expr=field_expr,
            operator=operator,
            strategy="relational_domain"
            if operator == "any" or isinstance(value, Domain)
            else "collection"
            if operator == "in" and isinstance(value, COLLECTION_TYPES)
            else "scalar",
        )
        if operator == "any" or isinstance(value, Domain):
            domain = Domain(value).optimize(records)

            def matches_any(rec: BaseModel) -> bool:
                corecords = getter(rec)
                return is_recordset(corecords) and bool(
                    corecords.filtered_domain(domain)
                )

            return matches_any
        if operator == "in" and isinstance(value, COLLECTION_TYPES):
            return self._filter_property_in(getter, value)
        if operator in PYTHON_INEQUALITY_OPERATOR and isinstance(value, date):
            return self._filter_property_temporal(getter, operator, value)
        return super().filter_function(records, field_expr, operator, value)

    @staticmethod
    def _filter_property_temporal(
        getter: abc.Callable[[BaseModel], typing.Any], operator: str, value: date
    ) -> abc.Callable[[BaseModel], bool]:
        property_type = _temporal_type_of(value)
        compare = PYTHON_INEQUALITY_OPERATOR[operator]
        bound = temporal_property_bound(value)

        def matches(rec: BaseModel) -> bool:
            parsed = parse_temporal_property(getter(rec), property_type)
            return parsed is not None and compare(parsed, bound)

        return matches

    @staticmethod
    def _filter_property_in(
        getter: abc.Callable[[BaseModel], typing.Any],
        value: abc.Collection[typing.Any],
    ) -> abc.Callable[[BaseModel], bool]:
        values = list(value)
        if len(values) == 1 and values[0] is True:
            return lambda rec: not _is_unset(getter(rec))
        match_unset = any(v is False for v in values)
        values = [v for v in values if v is not False]

        def matches(rec: BaseModel) -> bool:
            rec_value = getter(rec)
            if _is_unset(rec_value):
                return match_unset
            if is_recordset(rec_value):
                items: abc.Iterable[typing.Any] = rec_value._ids
            elif type(rec_value) is list:
                items = rec_value
            else:
                items = (rec_value,)
            return any(_same_value(v, item) for v in values for item in items)

        return matches

    def property_to_sql(
        self,
        field_sql: SQL,
        property_name: str,
        model: ModelLike,
        alias: str,
        query: Query,
    ) -> SQL:
        name, part = split_temporal_part(property_name)
        check_property_field_value_name(name)
        sql_property = SQL("(%s -> %s)", field_sql, name)
        if part is None:
            return sql_property
        property_type = temporal_property_type(
            typing.cast("BaseModel", model), f"{self.name}.{name}", part
        )
        return temporal_property_sql(
            temporal_property_text_sql(field_sql, name), property_type, model.env, part
        )

    @staticmethod
    def _property_in_to_sql(
        operator: str,
        value: typing.Any,
        sql_left: SQL,
        raw_sql_field: SQL,
        property_name: str,
    ) -> SQL:
        assert isinstance(value, COLLECTION_TYPES)
        if len(value) == 1 and any(v is True for v in value):
            check_null_op_false = "!=" if operator == "in" else "="
            value = []
            operator = "in" if operator == "not in" else "not in"
        elif any(v is False for v in value):
            check_null_op_false = "=" if operator == "in" else "!="
            value = [v for v in value if v is not False]
        else:
            value = list(value)
            check_null_op_false = None

        sqls = []
        if check_null_op_false:
            sqls.append(
                SQL(
                    "%s%s'false'::jsonb",
                    sql_left,
                    SQL_OPERATORS[check_null_op_false],
                )
            )
            if check_null_op_false == "=":
                sqls.extend(_unset_property_sql(raw_sql_field, property_name))
        for one_value in value:
            sql_value = SQL("%s", json_dumps(one_value))
            sql_array = SQL("%s", json_dumps([one_value]))
            if operator == "in":
                sqls.append(
                    SQL(
                        "(%s = %s OR %s @> %s)",
                        sql_left,
                        sql_value,
                        sql_left,
                        sql_array,
                    )
                )
            else:
                sqls.append(
                    SQL(
                        "(%s != %s AND NOT %s @> %s)",
                        sql_left,
                        sql_value,
                        sql_left,
                        sql_array,
                    )
                )
        assert sqls, "No SQL generated for property"
        if operator == "not in" and check_null_op_false is None:
            return SQL(
                "(%s OR %s)",
                SQL(" AND ").join(sqls),
                SQL(" OR ").join(_unset_property_sql(raw_sql_field, property_name)),
            )
        if len(sqls) == 1:
            return sqls[0]
        combine_sql = SQL(" OR ") if operator == "in" else SQL(" AND ")
        return SQL("(%s)", combine_sql.join(sqls))

    def _temporal_part_condition_to_sql(
        self, sql_part: SQL, operator: str, value: typing.Any, model: BaseModel
    ) -> SQL:
        if operator in ("in", "not in"):
            return self._condition_in_to_sql(
                sql_part, operator, value, lambda v: v, can_be_null=True
            )
        if operator in PYTHON_INEQUALITY_OPERATOR:
            return self._condition_inequality_to_sql(
                sql_part, operator, value, model, lambda v: v, can_be_null=True
            )
        raise ValueError(f"Invalid operator {operator} for a date part of a property")

    @override
    def condition_to_sql(
        self,
        field_expr: str,
        operator: str,
        value: typing.Any,
        model: BaseModel,
        alias: str,
        query: Query,
    ) -> SQL:
        fname, property_name = parse_field_expr(field_expr)
        if not property_name:
            raise ValueError(f"Missing property name for {self}")
        if split_temporal_part(property_name)[1] is not None:
            return self._temporal_part_condition_to_sql(
                model._field_to_sql(alias, field_expr, query), operator, value, model
            )
        raw_sql_field = model._field_to_sql(alias, fname, query)
        sql_left = model._field_to_sql(alias, field_expr, query)

        _debug.logic(
            "field.properties.condition_to_sql",
            model=model._name,
            field_expr=field_expr,
            operator=operator,
            shape="in"
            if operator in ("in", "not in")
            else "text"
            if isinstance(value, str) or operator.endswith("like")
            else "json",
        )
        if operator in ("in", "not in"):
            return self._property_in_to_sql(
                operator, value, sql_left, raw_sql_field, property_name
            )
        if operator in PYTHON_INEQUALITY_OPERATOR and isinstance(value, date):
            return _temporal_property_range_sql(
                temporal_property_text_sql(raw_sql_field, property_name),
                operator,
                value,
            )

        def unaccent(x: SQL) -> SQL:
            return x

        unaccent_fn: typing.Callable[..., typing.Any] = unaccent

        if operator.endswith("like"):
            if operator.endswith("ilike"):
                unaccent_fn = model.env.registry.unaccent
            if "=" in operator:
                value = str(value)
            else:
                value = f"%{value}%"

        try:
            sql_operator = SQL_OPERATORS[operator]
        except KeyError:
            raise ValueError(f"Invalid operator {operator} for Properties") from None

        if isinstance(value, str):
            sql_json = sql_left
            sql_left = SQL(
                "(CASE WHEN jsonb_typeof(%s) IN ('boolean', 'null')"
                " THEN NULL ELSE %s ->> %s END)",
                sql_json,
                raw_sql_field,
                property_name,
            )
            sql_right = SQL("%s", value)
            sql = SQL(
                "%s%s%s",
                unaccent_fn(sql_left),
                sql_operator,
                unaccent_fn(sql_right),
            )
            if operator in Domain.NEGATIVE_OPERATORS:
                sql = SQL("(%s OR %s IS NULL)", sql, sql_left)
            elif operator in PYTHON_INEQUALITY_OPERATOR:
                sql = SQL("(jsonb_typeof(%s) = 'string' AND %s)", sql_json, sql)
            return sql

        sql_right = SQL("%s", json_dumps(value))
        sql = SQL("%s%s%s", sql_left, sql_operator, sql_right)
        if operator in PYTHON_INEQUALITY_OPERATOR and isinstance(value, int | float):
            json_type = "boolean" if isinstance(value, bool) else "number"
            sql = SQL("(jsonb_typeof(%s) = %s AND %s)", sql_left, json_type, sql)
        return sql
