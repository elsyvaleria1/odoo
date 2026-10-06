import contextlib
import typing
from datetime import date, datetime, time, timedelta, tzinfo

from odoo.libs.datetime import utc
from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import SQL

from ..constants import READ_GROUP_NUMBER_GRANULARITY
from ..primitives import SQL_OPERATORS
from ..validation import regex_alphanumeric
from .temporal import _resolve_sql_timezone_name

if typing.TYPE_CHECKING:
    from ..models import BaseModel

_debug = DebugLog("odoo.orm.fields.properties")


def check_property_field_value_name(property_name: str) -> None:
    if not (0 < len(property_name) <= 512) or not regex_alphanumeric.fullmatch(
        property_name
    ):
        raise ValueError(f"Wrong property field value name {property_name!r}.")


def split_temporal_part(property_name: str) -> tuple[str, str | None]:
    name, dot, part = property_name.rpartition(".")
    if dot and part in READ_GROUP_NUMBER_GRANULARITY:
        return name, part
    return property_name, None


# The ISO shapes a temporal property accepts on write, before it stores the
# value in its canonical form: a value is held to them by its skeleton, every
# digit read as 9. Hour 24 reads as the next midnight.
_DIGIT_SKELETON = str.maketrans("0123456789", "9" * 10)
_TEMPORAL_PROPERTY_INPUT_SKELETONS = frozenset(
    (
        "9999-99-99",
        *(
            f"9999-99-99{separator}{clock}{offset}"
            for separator in " T"
            for clock in (
                "99:99",
                "99:99:99",
                *(f"99:99:99.{'9' * digits}" for digits in range(1, 7)),
            )
            for offset in ("", "Z", "+99", "-99", "+99:99", "-99:99", "+9999", "-9999")
        ),
    )
)
# the stored form: the skeleton of a date and of a naive UTC datetime
_TEMPORAL_PROPERTY_SKELETONS = {"date": "9999-99-99", "datetime": "9999-99-99 99:99:99"}
TEMPORAL_PROPERTY_TYPES = frozenset(_TEMPORAL_PROPERTY_SKELETONS)
# PostgreSQL refuses an offset past 15:59, and offset minutes past 59
_MAX_TEMPORAL_PROPERTY_OFFSET = timedelta(hours=16)
_TEMPORAL_PROPERTY_RANGE = ("0001-01-01 00:00:00", "9999-12-31 23:59:59.999999")


def _parse_temporal_property_input(
    value: str, property_type: str
) -> date | datetime | None:
    if (
        value.translate(_DIGIT_SKELETON) not in _TEMPORAL_PROPERTY_INPUT_SKELETONS
        or value[17:19] >= "60"
    ):
        return None
    # a date property takes the date of its text, but only of a text that is
    # a valid instant: '2024-03-28 99:99' is no date
    try:
        # alone: fromisoformat rolls day 00 over to the 1st under hour 24
        day = date.fromisoformat(value[:10])
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    offset = parsed.utcoffset()
    if offset is not None:
        # fromisoformat reads +05:75 as 6h15
        if abs(offset) >= _MAX_TEMPORAL_PROPERTY_OFFSET or (
            value[-3] != "+"
            and value[-3] != "-"
            and value[-1] != "Z"
            and value[-2:] >= "60"
        ):
            return None
        try:
            parsed = (parsed - offset).replace(tzinfo=None)
        except OverflowError:
            return None
    return day if property_type == "date" else parsed


def render_temporal_property(value: date, property_type: str) -> str:
    if property_type == "date":
        return (value.date() if isinstance(value, datetime) else value).isoformat()
    if not isinstance(value, datetime):
        value = datetime.combine(value, time.min)
    return value.isoformat(" ", "seconds")


def canonical_temporal_property(value: typing.Any, property_type: str) -> str | None:
    parsed: date | datetime | None = None
    if isinstance(value, str):
        parsed = _parse_temporal_property_input(value, property_type)
    elif isinstance(value, datetime) and value.tzinfo and property_type == "datetime":
        with contextlib.suppress(OverflowError):
            parsed = value.astimezone(utc).replace(tzinfo=None)
    elif isinstance(value, date):
        parsed = value
    return None if parsed is None else render_temporal_property(parsed, property_type)


def parse_temporal_property(
    value: typing.Any, property_type: str | None
) -> date | datetime | None:
    # a write stores the canonical form: any other value, written before the
    # property was temporal or under another definition of its name, is no value
    skeleton = _TEMPORAL_PROPERTY_SKELETONS.get(property_type or "")
    if not isinstance(value, str) or value.translate(_DIGIT_SKELETON) != skeleton:
        return None
    try:
        if property_type == "date":
            return date.fromisoformat(value)
        # both tiers would read hour 24 as the next midnight, PostgreSQL second
        # 60 as the next minute: neither is the canonical text of its instant
        if value[11:13] >= "24" or value[17:19] >= "60":
            return None
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def local_temporal_property(value: datetime, tz: tzinfo) -> datetime | None:
    try:
        return value.replace(tzinfo=utc).astimezone(tz)
    except OverflowError:
        return None


def temporal_property_type(model: BaseModel, field_expr: str, part: str) -> str:
    property_type: str | None = model.get_property_definition(field_expr).get("type")
    if property_type not in TEMPORAL_PROPERTY_TYPES:
        raise ValueError(
            f"{part!r} reads a date or datetime property, not "
            f"{field_expr} ({property_type or 'undefined'})"
        )
    return property_type


def temporal_property_bound(value: date) -> date:
    # held to the stored precision, as fields.Datetime holds a domain value
    return value.replace(microsecond=0) if isinstance(value, datetime) else value


# parse_temporal_property's test in SQL: the text is the canonical rendering
# of the valid instant it reads as. A round trip, not the skeleton: translate()
# costs more than the cast, and PostgreSQL reads '2024-03-05 a0:00:00' or
# ' 024-03-05' as instants. ->> renders a json array or number as its json
# text, which no rendering is.
_TEMPORAL_PROPERTY_SQL = {
    "date": (10, "date", SQL("date"), "YYYY-MM-DD"),
    "datetime": (19, "timestamp", SQL("timestamp"), "YYYY-MM-DD HH24:MI:SS"),
}


def temporal_property_text_sql(sql_field: SQL, property_name: str) -> SQL:
    # one operator, where (field -> name) ->> 0 costs two: the guard reads
    # the text four times, and PostgreSQL computes each read anew
    return SQL("(%s ->> %s)", sql_field, property_name)


def _temporal_property_guard_sql(sql_text: SQL, property_type: str) -> SQL:
    length, type_name, sql_type, template = _TEMPORAL_PROPERTY_SQL[property_type]
    return SQL(
        "CASE WHEN length(%s) = %s AND pg_input_is_valid(%s, %s)"
        " THEN to_char(CAST(%s AS %s), %s) = %s ELSE false END",
        sql_text,
        length,
        sql_text,
        type_name,
        sql_text,
        sql_type,
        template,
        sql_text,
    )


def _temporal_property_cast_sql(
    sql_text: SQL, property_type: str, sql_tz: str = "UTC"
) -> SQL:
    guard = _temporal_property_guard_sql(sql_text, property_type)
    if property_type == "date":
        return SQL("CASE WHEN %s THEN CAST(%s AS date) END", guard, sql_text)
    sql_value = SQL("CAST(%s AS timestamp)", sql_text)
    if sql_tz != "UTC":
        # only the reader's zone moves an instant past year 1 or 9999, where
        # Python overflows and psycopg cannot load what PostgreSQL computes
        sql_value = SQL(
            "timezone(%s, timezone('UTC', %s))", SQL.literal(sql_tz), sql_value
        )
        first, last = (SQL.literal(bound) for bound in _TEMPORAL_PROPERTY_RANGE)
        guard = SQL(
            "%s AND (left(%s, 4) NOT IN ('0001', '9999') OR %s BETWEEN %s AND %s)",
            guard,
            sql_text,
            sql_value,
            first,
            last,
        )
    return SQL("CASE WHEN %s THEN %s END", guard, sql_value)


def _temporal_property_range_sql(sql_text: SQL, operator: str, value: date) -> SQL:
    # the canonical text sorts as its instant, so the text compare decides and
    # the guard only vets the rows it kept: PostgreSQL runs a row's quals
    # cheapest first, and the guard is one CASE, costed as a whole
    property_type = _temporal_type_of(value)
    return SQL(
        '(%s COLLATE "C"%s%s AND %s)',
        sql_text,
        SQL_OPERATORS[operator],
        render_temporal_property(temporal_property_bound(value), property_type),
        _temporal_property_guard_sql(sql_text, property_type),
    )


def _temporal_type_of(value: date) -> str:
    return "datetime" if isinstance(value, datetime) else "date"


def temporal_property_sql(
    sql_text: SQL, property_type: str, env: typing.Any, part: str | None = None
) -> SQL:
    sql_tz = "UTC"
    if (
        property_type == "datetime"
        and (tz_name := env.context.get("tz"))
        and (resolved := _resolve_sql_timezone_name(env, tz_name))
    ):
        sql_tz = resolved
    sql_expr = _temporal_property_cast_sql(sql_text, property_type, sql_tz)
    if part is None:
        return sql_expr
    return SQL(
        "date_part(%s, %s)",
        SQL.literal(READ_GROUP_NUMBER_GRANULARITY[part]),
        sql_expr,
    )


RELATIONAL_PROPERTY_TYPES = frozenset(("many2one", "many2many"))
