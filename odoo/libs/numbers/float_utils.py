import functools
import math
from decimal import Decimal
from typing import Literal

type RoundingMethod = Literal["UP", "DOWN", "HALF-UP", "HALF-DOWN", "HALF-EVEN"]

__all__ = [
    "RoundingMethod",
    "float_compare",
    "float_is_zero",
    "float_repr",
    "float_round",
    "float_split_str",
]


def _round_half_away_from_zero(f: float) -> float:
    # a tie is f an exact half away from its rounding; the old test on f + 1
    # lost the bits of an |f| below 1, so 0.49999999999999994 read as a tie
    roundf = round(f)
    if f - roundf in (0.5, -0.5):
        return f + math.copysign(0.5, f)
    return math.copysign(roundf, f)


def _float_check_precision(
    precision_digits: int | None = None,
    precision_rounding: float | None = None,
) -> float:
    if precision_rounding is not None and precision_digits is None:
        if not (math.isfinite(precision_rounding) and precision_rounding > 0):
            raise ValueError(
                f"precision_rounding must be positive and finite, got {precision_rounding}"
            )
    elif precision_digits is not None and precision_rounding is None:
        if not float(precision_digits).is_integer() or precision_digits < 0:
            raise ValueError(
                f"precision_digits must be a non-negative integer, got {precision_digits}"
            )
        precision_rounding = float(10**-precision_digits)
    else:
        msg = "exactly one of precision_digits and precision_rounding must be specified"
        raise ValueError(msg)
    return precision_rounding


def float_round(
    value: float,
    precision_digits: int | None = None,
    precision_rounding: float | None = None,
    rounding_method: RoundingMethod = "HALF-UP",
) -> float:
    return _round_r(
        value,
        _float_check_precision(precision_digits, precision_rounding),
        rounding_method,
    )


_EPSILON_SCALE = 2.0**-50
# Past 2**47 the epsilon grows beyond an eighth of a step and the float's own
# representation error can fake a tie: the float stops telling real digits from
# noise, so the shortest decimal that round-trips to it is rounded instead.
_EXACT_THRESHOLD = 2.0**47
# a double round-trips any decimal of at most this many significant digits
_FAITHFUL_DIGITS = 15


def _round_r(
    value: float,
    rounding_factor: float,
    rounding_method: RoundingMethod = "HALF-UP",
) -> float:
    if value == 0:
        return 0.0
    if rounding_factor == 0:
        # 10 ** -precision_digits underflowed: no step is fine enough to move it
        return float(value)

    step = rounding_factor
    inverted = rounding_factor < 1
    if inverted:
        rounding_factor = _float_invert(rounding_factor)
        normalized_value = value * rounding_factor
    else:
        normalized_value = value / rounding_factor

    if normalized_value == 0.0:  # noqa: RUF069  exact-zero fast path; 0.0 is representable
        return 0.0
    magnitude = abs(normalized_value)
    if not magnitude < _EXACT_THRESHOLD:
        if not math.isfinite(value):
            msg = f"cannot round a non-finite value: {value}"
            raise ValueError(msg)
        return _round_exact(value, step, rounding_method)

    epsilon = magnitude * _EPSILON_SCALE
    fraction = magnitude % 1.0
    if rounding_method in ("UP", "DOWN"):
        near_boundary = fraction < 2 * epsilon or fraction > 1 - 2 * epsilon
    else:
        near_boundary = abs(fraction - 0.5) < 2 * epsilon

    if rounding_method == "HALF-UP":
        result = _round_half_away_from_zero(
            normalized_value + math.copysign(epsilon, normalized_value)
        )
    elif rounding_method == "HALF-EVEN":
        integral = math.floor(normalized_value)
        remainder = abs(normalized_value - integral)
        is_half = remainder == 0.5 or abs(0.5 - remainder) < epsilon  # noqa: RUF069  exact fast path + epsilon fallback
        result = (
            integral + (integral & 1)
            if is_half
            else _round_half_away_from_zero(normalized_value)
        )
    elif rounding_method == "HALF-DOWN":
        integral = math.floor(abs(normalized_value))
        remainder = abs(normalized_value) - integral
        is_half = remainder == 0.5 or abs(0.5 - remainder) < epsilon  # noqa: RUF069  exact fast path + epsilon fallback, as above
        if is_half:
            result = math.copysign(integral, normalized_value)
        else:
            result = _round_half_away_from_zero(
                normalized_value - math.copysign(epsilon, normalized_value)
            )
    elif rounding_method == "UP":
        result = math.trunc(
            normalized_value + math.copysign(1 - epsilon, normalized_value)
        )
    elif rounding_method == "DOWN":
        result = math.trunc(normalized_value + math.copysign(epsilon, normalized_value))
    else:
        msg = f"unknown rounding method: {rounding_method}"
        raise ValueError(msg)

    if inverted and rounding_factor.is_integer():
        rounded = result / rounding_factor
    elif not inverted and (step.is_integer() or _spells_its_decimal(step)):
        rounded = float(result * rounding_factor)
    else:
        # 1/0.03 and 1.1 are not floats, so a multiple of either lands an ulp off
        rounded = float(Decimal(result) * Decimal(repr(step)))
    if (
        near_boundary
        and rounded != value
        and (
            rounding_method in ("UP", "DOWN")
            or abs(value) != _tie(magnitude, rounding_factor, inverted)
        )
        and _significant_digits(value) <= _FAITHFUL_DIGITS
    ):
        # the epsilon decided it, but the float spells a decimal off the
        # boundary: a real digit, not arithmetic noise, so round that instead
        return _round_exact(value, step, rounding_method)
    return rounded or 0.0


@functools.lru_cache(maxsize=256)
def _spells_its_decimal(step: float) -> bool:
    return Decimal(step) == Decimal(repr(step))


def _tie(magnitude: float, rounding_factor: float, inverted: bool) -> float:
    if not rounding_factor.is_integer():
        return math.nan
    halves = 2 * math.floor(magnitude) + 1
    if inverted:
        return halves / (2 * rounding_factor)
    return halves * rounding_factor / 2


def _significant_digits(value: float) -> int:
    mantissa = _decimal_text(abs(value)).partition("e")[0]
    return len(mantissa.replace(".", "").strip("0"))


def _shortest_decimal(value: float) -> tuple[int, int]:
    mantissa, _, exponent = _decimal_text(value).partition("e")
    whole, _, fraction = mantissa.partition(".")
    return int(whole + fraction), int(exponent or 0) - len(fraction)


def _decimal_text(value: float) -> str:
    # numpy's repr is "np.float64(2.5)"; an int keeps all its digits
    return repr(value if type(value) is int else float(value))


def _round_exact(
    value: float,
    step: float,
    rounding_method: RoundingMethod,
) -> float:
    value_digits, value_exponent = _shortest_decimal(abs(value))
    step_digits, step_exponent = _shortest_decimal(step)
    shift = value_exponent - step_exponent
    if shift >= 0:
        numerator, denominator = value_digits * 10**shift, step_digits
    else:
        numerator, denominator = value_digits, step_digits * 10**-shift
    quotient, remainder = divmod(numerator, denominator)
    if rounding_method == "HALF-UP":
        carry = 2 * remainder >= denominator
    elif rounding_method == "HALF-EVEN":
        carry = 2 * remainder > denominator or (
            2 * remainder == denominator and quotient & 1 == 1
        )
    elif rounding_method == "HALF-DOWN":
        carry = 2 * remainder > denominator
    elif rounding_method == "UP":
        carry = remainder > 0
    elif rounding_method == "DOWN":
        carry = False
    else:
        msg = f"unknown rounding method: {rounding_method}"
        raise ValueError(msg)
    steps = (quotient + carry) * step_digits
    if step_exponent < 0:
        rounded = steps / 10**-step_exponent
    else:
        rounded = float(steps * 10**step_exponent)
    return math.copysign(rounded, value) if rounded else 0.0


def _is_zero_r(value: float, epsilon: float) -> bool:
    return (
        value == 0.0  # noqa: RUF069  exact-zero fast path; the epsilon test after `or` is the real check
        or abs(_round_r(value, epsilon)) < epsilon
    )


def float_is_zero(
    value: float,
    precision_digits: int | None = None,
    precision_rounding: float | None = None,
) -> bool:
    return _is_zero_r(
        value, _float_check_precision(precision_digits, precision_rounding)
    )


def float_compare(
    value1: float,
    value2: float,
    precision_digits: int | None = None,
    precision_rounding: float | None = None,
) -> Literal[-1, 0, 1]:
    rounding_factor = _float_check_precision(precision_digits, precision_rounding)
    if value1 == value2:
        return 0
    rounded1 = _round_r(value1, rounding_factor)
    rounded2 = _round_r(value2, rounding_factor)
    if rounded1 == rounded2:
        return 0
    return -1 if rounded1 < rounded2 else 1


def float_repr(value: float, precision_digits: int) -> str:
    known = _REPR_STEPS.get(precision_digits)
    if (
        known is None
        or type(precision_digits) is not int
        or (type(value) is not float and type(value) is not int)
    ):
        rounded = _round_r(
            value, _float_check_precision(precision_digits=precision_digits)
        )
        return f"{rounded:.{precision_digits}f}"
    step, factor, spec = known
    return format(_round_half_up_by_factor(value, step, factor), spec)


def _round_half_up_by_factor(value: float, step: float, factor: float) -> float:
    # _round_r(value, step, "HALF-UP") unrolled for a float or int `value` and a
    # step that is 1 or whose inverse is the integer `factor`: both give the
    # same float, the error types included
    if value == 0:
        return 0.0
    normalized_value = value * factor
    if normalized_value == 0.0:  # noqa: RUF069  exact-zero fast path, as in _round_r
        return 0.0
    magnitude = abs(normalized_value)
    if not magnitude < _EXACT_THRESHOLD:
        if not math.isfinite(value):
            msg = f"cannot round a non-finite value: {value}"
            raise ValueError(msg)
        return _round_exact(value, step, "HALF-UP")
    epsilon = magnitude * _EPSILON_SCALE
    nudged = normalized_value + math.copysign(epsilon, normalized_value)
    nearest = round(nudged)
    # below 2**47 a double minus its nearest integer is exact, so a half apart
    # is exactly the tie round() would settle to even
    if nudged - nearest in (0.5, -0.5):
        result = nudged + math.copysign(0.5, nudged)
    else:
        result = math.copysign(nearest, nudged)
    rounded = result / factor
    if (
        abs(magnitude % 1.0 - 0.5) < 2 * epsilon
        and rounded != value
        and abs(value) != _tie(magnitude, factor, inverted=True)
        and _significant_digits(value) <= _FAITHFUL_DIGITS
    ):
        return _round_exact(value, step, "HALF-UP")
    return rounded or 0.0


def float_split_str(value: float, precision_digits: int) -> tuple[str, str]:
    whole, _, fraction = float_repr(value, precision_digits).partition(".")
    return (whole, fraction)


_INVERTDICT = {
    1e-1: 1e1,
    1e-2: 1e2,
    1e-3: 1e3,
    1e-4: 1e4,
    1e-5: 1e5,
    1e-6: 1e6,
    1e-7: 1e7,
    1e-8: 1e8,
    1e-9: 1e9,
    1e-10: 1e10,
    2e-1: 5e0,
    2e-2: 5e1,
    2e-3: 5e2,
    2e-4: 5e3,
    2e-5: 5e4,
    2e-6: 5e5,
    2e-7: 5e6,
    2e-8: 5e7,
    2e-9: 5e8,
    2e-10: 5e9,
    5e-1: 2e0,
    5e-2: 2e1,
    5e-3: 2e2,
    5e-4: 2e3,
    5e-5: 2e4,
    5e-6: 2e5,
    5e-7: 2e6,
    5e-8: 2e7,
    5e-9: 2e8,
    5e-10: 2e9,
}


def _float_invert(value: float) -> float:
    if not value:
        raise ZeroDivisionError("cannot invert 0")
    result = _INVERTDICT.get(value)
    if result is None:
        result = float(1 / Decimal(repr(value)))
    return result


def _repr_steps() -> dict[int, tuple[float, float, str]]:
    steps = {}
    for digits in range(16):
        step = _float_check_precision(precision_digits=digits)
        factor = _float_invert(step) if step < 1 else step
        if factor.is_integer():
            steps[digits] = (step, factor, f".{digits}f")
    return steps


_REPR_STEPS = _repr_steps()
