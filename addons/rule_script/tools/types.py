import datetime


class RuleValueError(TypeError):
    pass


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuleValueError(f"expected a number, got {value!r}")
    return float(value)


def _int(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuleValueError(f"expected an integer, got {value!r}")
    return value


def _bool(value):
    if not isinstance(value, bool):
        raise RuleValueError(f"expected a boolean, got {value!r}")
    return value


def _str(value):
    if not isinstance(value, str):
        raise RuleValueError(f"expected a string, got {value!r}")
    return value


def _date(value):
    if isinstance(value, datetime.datetime):
        raise RuleValueError(f"expected a date, got the datetime {value!r}")
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            pass
    raise RuleValueError(f"expected a date, got {value!r}")


def _list(value):
    if not isinstance(value, (list, tuple)):
        raise RuleValueError(f"expected a list, got {value!r}")
    return tuple(freeze(item) for item in value)


def _dict(value):
    if not isinstance(value, dict):
        raise RuleValueError(f"expected a mapping, got {value!r}")
    return {key: freeze(item) for key, item in value.items()}


def freeze(value):
    if isinstance(value, (list, tuple)):
        return _list(value)
    if isinstance(value, dict):
        return _dict(value)
    if isinstance(value, (int, float, str, bool, datetime.date, type(None))):
        return value
    raise RuleValueError(f"{type(value).__name__} is not a rule value")


VALUE_TYPES = {
    "number": _number,
    "int": _int,
    "bool": _bool,
    "str": _str,
    "date": _date,
    "list": _list,
    "dict": _dict,
    "any": freeze,
}


def coerce(value_type, value):
    return VALUE_TYPES[value_type](value)
