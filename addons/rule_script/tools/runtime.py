import builtins
import calendar
import contextvars
import datetime
from decimal import ROUND_HALF_UP, Decimal

from .grammar import (
    ENTRY_POINT,
    GUARDED_ATTRIBUTE,
    GUARDED_ITERATE,
    GUARDED_MULTIPLY,
    GUARDED_POWER,
    SAFE_BUILTIN_NAMES,
)
from .types import RuleValueError, coerce

MAX_RANGE = 10_000
MAX_CALL_DEPTH = 32
MAX_STEPS = 1_000_000
MAX_CALLS = 1_000
MAX_INT_BITS = 4_096


class RuleRuntimeError(RuntimeError):
    pass


class RuleBudget:

    __slots__ = ("calls", "steps")

    def __init__(self) -> None:
        self.steps = MAX_STEPS
        self.calls = MAX_CALLS

    def step(self) -> None:
        self.steps -= 1
        if self.steps < 0:
            raise RuleRuntimeError(
                f"a rule evaluation iterates at most {MAX_STEPS} times"
            )

    def call(self) -> None:
        self.calls -= 1
        if self.calls < 0:
            raise RuleRuntimeError(f"a rule evaluation calls at most {MAX_CALLS} rules")


_BUDGET = contextvars.ContextVar("rule_budget", default=None)


class RuleInputs:

    __slots__ = ("_values",)

    def __init__(self, signature, values) -> None:
        missing = sorted(signature.keys() - values.keys())
        unknown = sorted(values.keys() - signature.keys())
        if missing or unknown:
            raise RuleValueError(f"missing inputs {missing}, unknown inputs {unknown}")
        frozen = {}
        for name, value_type in signature.items():
            try:
                frozen[name] = coerce(value_type, values[name])
            except RuleValueError as error:
                raise RuleValueError(f"input {name!r}: {error}") from error
        object.__setattr__(self, "_values", frozen)

    def __getattr__(self, name):
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        raise AttributeError("rule inputs are read-only")


def _rule_range(*arguments):
    result = range(*arguments)
    if len(result) > MAX_RANGE:
        raise RuleRuntimeError(f"range() is limited to {MAX_RANGE} items")
    return result


def _rule_attribute(value, name):
    if name.startswith("_"):
        raise RuleRuntimeError(f"attribute {name!r} is not readable")
    result = getattr(value, name)
    if callable(result):
        raise RuleRuntimeError(f"{name!r} is a method; a rule reads values only")
    return result


def _check_int_size(value):
    if isinstance(value, int) and value.bit_length() > MAX_INT_BITS:
        raise RuleRuntimeError(f"an integer is limited to {MAX_INT_BITS} bits")
    return value


def _rule_power(base, exponent):
    if (
        isinstance(base, int)
        and isinstance(exponent, int)
        and exponent > 0
        and base.bit_length() * exponent > MAX_INT_BITS
    ):
        raise RuleRuntimeError(f"an integer is limited to {MAX_INT_BITS} bits")
    return base**exponent


def _rule_iterate(iterable):
    budget = _BUDGET.get() or RuleBudget()
    for item in iterable:
        budget.step()
        yield item


def _rule_multiply(left, right):
    if (
        isinstance(left, int)
        and isinstance(right, int)
        and left.bit_length() + right.bit_length() > MAX_INT_BITS
    ):
        raise RuleRuntimeError(f"an integer is limited to {MAX_INT_BITS} bits")
    for sequence, count in ((left, right), (right, left)):
        if (
            isinstance(sequence, (str, list, tuple))
            and isinstance(count, int)
            and len(sequence) * count > MAX_RANGE
        ):
            raise RuleRuntimeError(
                f"a repeated sequence is limited to {MAX_RANGE} items"
            )
    return left * right


SAFE_BUILTINS = {
    **{name: getattr(builtins, name) for name in SAFE_BUILTIN_NAMES},
    "range": _rule_range,
}


def compile_rule(module, filename):
    namespace = {
        "__builtins__": SAFE_BUILTINS,
        GUARDED_ATTRIBUTE: _rule_attribute,
        GUARDED_MULTIPLY: _rule_multiply,
        GUARDED_POWER: _rule_power,
        GUARDED_ITERATE: _rule_iterate,
    }
    exec(compile(module, filename, "exec"), namespace)
    return namespace[ENTRY_POINT]


class RuleContext:

    def __init__(self, on_date, resolve, depth=0, trace=None) -> None:
        self.on_date = on_date
        self._resolve = resolve
        self._depth = depth
        self._trace = trace

    def call(self, code, **inputs):
        return self.call_at(self.on_date, code, **inputs)

    def call_at(self, date, code, **inputs):
        (_BUDGET.get() or RuleBudget()).call()
        if self._depth >= MAX_CALL_DEPTH:
            raise RuleRuntimeError(f"rule calls nest deeper than {MAX_CALL_DEPTH}")
        return self._resolve(code, date, inputs, self._depth + 1, self._trace)

    def date(self, year, month, day):
        return datetime.date(year, month, day)

    def add_days(self, date, days):
        return date + datetime.timedelta(days=days)

    def add_months(self, date, months):
        month_index = date.year * 12 + date.month - 1 + months
        year, month = divmod(month_index, 12)
        month += 1
        return date.replace(
            year=year,
            month=month,
            day=min(date.day, calendar.monthrange(year, month)[1]),
        )

    def end_of_month(self, date):
        return date.replace(day=calendar.monthrange(date.year, date.month)[1])

    def weekday(self, date):
        return date.weekday()

    def round_half_up(self, value, digits=0):
        quantum = Decimal(1).scaleb(-digits)
        return float(Decimal(repr(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def run_rule(function, header, inputs, context):
    rule_inputs = RuleInputs(header.inputs, inputs)
    token = _BUDGET.set(RuleBudget()) if _BUDGET.get() is None else None
    try:
        result = function(rule_inputs, context)
    except RuleRuntimeError, RuleValueError:
        raise
    except Exception as error:
        raise RuleRuntimeError(
            f"{header.code}: {type(error).__name__}: {error}"
        ) from error
    finally:
        if token is not None:
            _BUDGET.reset(token)
    try:
        return coerce(header.output, result)
    except RuleValueError as error:
        raise RuleRuntimeError(f"{header.code} returned {result!r}: {error}") from error
