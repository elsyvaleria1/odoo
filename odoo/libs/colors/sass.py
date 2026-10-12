import math
import re
from collections.abc import Sequence
from contextlib import suppress

from .conversions import _hsl, _luma, hex_to_rgb

SassColor = tuple[float, float, float, float]

__all__ = [
    "SASS_WHITE",
    "SassColor",
    "bootstrap_color_contrast",
    "bootstrap_contrast_ratio",
    "bootstrap_luminance",
    "parse_sass_color",
    "sass_channel",
    "sass_color_contrast",
    "sass_color_to_css",
    "sass_darken",
    "sass_flatten",
    "sass_increase_contrast",
    "sass_lighten",
    "sass_lightness",
    "sass_mix",
    "sass_scheme_contrast",
    "sass_shade",
    "sass_tint",
]

_EPSILON = 1e-11

SASS_WHITE: SassColor = (255.0, 255.0, 255.0, 1.0)
SASS_BLACK: SassColor = (0.0, 0.0, 0.0, 1.0)

_LUMINANCE = (
    0.0008,
    0.001,
    0.0011,
    0.0013,
    0.0015,
    0.0017,
    0.002,
    0.0022,
    0.0025,
    0.0027,
    0.003,
    0.0033,
    0.0037,
    0.004,
    0.0044,
    0.0048,
    0.0052,
    0.0056,
    0.006,
    0.0065,
    0.007,
    0.0075,
    0.008,
    0.0086,
    0.0091,
    0.0097,
    0.0103,
    0.011,
    0.0116,
    0.0123,
    0.013,
    0.0137,
    0.0144,
    0.0152,
    0.016,
    0.0168,
    0.0176,
    0.0185,
    0.0194,
    0.0203,
    0.0212,
    0.0222,
    0.0232,
    0.0242,
    0.0252,
    0.0262,
    0.0273,
    0.0284,
    0.0296,
    0.0307,
    0.0319,
    0.0331,
    0.0343,
    0.0356,
    0.0369,
    0.0382,
    0.0395,
    0.0409,
    0.0423,
    0.0437,
    0.0452,
    0.0467,
    0.0482,
    0.0497,
    0.0513,
    0.0529,
    0.0545,
    0.0561,
    0.0578,
    0.0595,
    0.0612,
    0.063,
    0.0648,
    0.0666,
    0.0685,
    0.0704,
    0.0723,
    0.0742,
    0.0762,
    0.0782,
    0.0802,
    0.0823,
    0.0844,
    0.0865,
    0.0887,
    0.0908,
    0.0931,
    0.0953,
    0.0976,
    0.0999,
    0.1022,
    0.1046,
    0.107,
    0.1095,
    0.1119,
    0.1144,
    0.117,
    0.1195,
    0.1221,
    0.1248,
    0.1274,
    0.1301,
    0.1329,
    0.1356,
    0.1384,
    0.1413,
    0.1441,
    0.147,
    0.15,
    0.1529,
    0.1559,
    0.159,
    0.162,
    0.1651,
    0.1683,
    0.1714,
    0.1746,
    0.1779,
    0.1812,
    0.1845,
    0.1878,
    0.1912,
    0.1946,
    0.1981,
    0.2016,
    0.2051,
    0.2086,
    0.2122,
    0.2159,
    0.2195,
    0.2232,
    0.227,
    0.2307,
    0.2346,
    0.2384,
    0.2423,
    0.2462,
    0.2502,
    0.2542,
    0.2582,
    0.2623,
    0.2664,
    0.2705,
    0.2747,
    0.2789,
    0.2831,
    0.2874,
    0.2918,
    0.2961,
    0.3005,
    0.305,
    0.3095,
    0.314,
    0.3185,
    0.3231,
    0.3278,
    0.3325,
    0.3372,
    0.3419,
    0.3467,
    0.3515,
    0.3564,
    0.3613,
    0.3663,
    0.3712,
    0.3763,
    0.3813,
    0.3864,
    0.3916,
    0.3968,
    0.402,
    0.4072,
    0.4125,
    0.4179,
    0.4233,
    0.4287,
    0.4342,
    0.4397,
    0.4452,
    0.4508,
    0.4564,
    0.4621,
    0.4678,
    0.4735,
    0.4793,
    0.4851,
    0.491,
    0.4969,
    0.5029,
    0.5089,
    0.5149,
    0.521,
    0.5271,
    0.5333,
    0.5395,
    0.5457,
    0.552,
    0.5583,
    0.5647,
    0.5711,
    0.5776,
    0.5841,
    0.5906,
    0.5972,
    0.6038,
    0.6105,
    0.6172,
    0.624,
    0.6308,
    0.6376,
    0.6445,
    0.6514,
    0.6584,
    0.6654,
    0.6724,
    0.6795,
    0.6867,
    0.6939,
    0.7011,
    0.7084,
    0.7157,
    0.7231,
    0.7305,
    0.7379,
    0.7454,
    0.7529,
    0.7605,
    0.7682,
    0.7758,
    0.7835,
    0.7913,
    0.7991,
    0.807,
    0.8148,
    0.8228,
    0.8308,
    0.8388,
    0.8469,
    0.855,
    0.8632,
    0.8714,
    0.8796,
    0.8879,
    0.8963,
    0.9047,
    0.9131,
    0.9216,
    0.9301,
    0.9387,
    0.9473,
    0.956,
    0.9647,
    0.9734,
    0.9823,
    0.9911,
    1.0,
)

_RE_RGB = re.compile(
    r"rgba?\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*(?:,\s*([-\d.]+)\s*)?\)"
)


def _gt(a: float, b: float) -> bool:
    return a > b and not math.isclose(a, b, rel_tol=0, abs_tol=_EPSILON)


def _ge(a: float, b: float) -> bool:
    return a > b or math.isclose(a, b, rel_tol=0, abs_tol=_EPSILON)


def _sass_round(value: float) -> int:
    return math.floor(value + 0.5)


def parse_sass_color(value: str) -> SassColor:
    value = value.strip()
    if value.startswith("#"):
        with suppress(ValueError):
            rgb = hex_to_rgb(value)
            return float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0
    if match := _RE_RGB.fullmatch(value):
        red, green, blue, alpha = match.groups()
        return (float(red), float(green), float(blue), float(alpha or 1))
    if value == "white":
        return SASS_WHITE
    if value == "black":
        return SASS_BLACK
    raise ValueError(f"{value!r} is not a colour this module reads")


def sass_color_to_css(color: SassColor) -> str:
    red, green, blue, alpha = color
    if all(float(c).is_integer() and 0 <= c <= 255 for c in (red, green, blue)):
        if alpha == 1:
            return f"#{int(red):02x}{int(green):02x}{int(blue):02x}"
    parts = ", ".join(_sass_number(c) for c in (red, green, blue))
    return f"rgba({parts}, {_sass_number(alpha)})" if alpha != 1 else f"rgb({parts})"


def _sass_number(value: float) -> str:
    return f"{round(value, 10):.10f}".rstrip("0").rstrip(".") or "0"


def sass_channel(color: SassColor, index: int) -> int:
    return _sass_round(color[index])


def sass_mix(color1: SassColor, color2: SassColor, weight: float = 50) -> SassColor:
    normalized = weight / 100 * 2 - 1
    alpha_distance = color1[3] - color2[3]
    combined = normalized * alpha_distance
    weight1 = (
        normalized if combined == -1 else (normalized + alpha_distance) / (1 + combined)
    )
    weight1 = (weight1 + 1) / 2
    weight2 = 1 - weight1
    return (
        color1[0] * weight1 + color2[0] * weight2,
        color1[1] * weight1 + color2[1] * weight2,
        color1[2] * weight1 + color2[2] * weight2,
        color1[3] * (weight / 100) + color2[3] * (1 - weight / 100),
    )


def sass_tint(color: SassColor, weight: float) -> SassColor:
    return sass_mix(SASS_WHITE, color, weight)


def sass_shade(color: SassColor, weight: float) -> SassColor:
    return sass_mix(SASS_BLACK, color, weight)


def _divide(dividend: float, divisor: float, precision: int = 10) -> float:
    sign = 1 if (dividend > 0 and divisor > 0) or (dividend < 0 and divisor < 0) else -1
    dividend, divisor = abs(dividend), abs(divisor)
    if dividend == 0:
        return 0.0
    remainder, result, factor = dividend, 0.0, 10.0
    while _gt(remainder, 0) and precision >= 0:
        quotient = 0
        while _ge(remainder, divisor):
            remainder -= divisor
            quotient += 1
        result = result * 10 + quotient
        factor *= 0.1
        remainder *= 10
        precision -= 1
        if precision < 0 and _ge(remainder, divisor * 5):
            result += 1
    return result * factor * sign


def bootstrap_luminance(color: SassColor) -> float:
    linear = []
    for index in range(3):
        value = min(max(_sass_round(sass_channel(color, index)), 0), 255)
        if _divide(value, 255) < 0.04045:
            linear.append(_divide(_divide(value, 255), 12.92))
        else:
            linear.append(_LUMINANCE[value])
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722


def sass_flatten(color: SassColor, background: SassColor) -> SassColor:
    return sass_mix((*color[:3], 1.0), background, color[3] * 100)


def bootstrap_contrast_ratio(
    background: SassColor, foreground: SassColor = SASS_WHITE
) -> float:
    l1 = bootstrap_luminance(background)
    l2 = bootstrap_luminance(sass_flatten(foreground, background))
    if l1 > l2:
        return _divide(l1 + 0.05, l2 + 0.05)
    return _divide(l2 + 0.05, l1 + 0.05)


def bootstrap_color_contrast(
    background: SassColor,
    dark: SassColor = SASS_BLACK,
    light: SassColor = SASS_WHITE,
    min_ratio: float = 4.5,
) -> SassColor:
    best, best_ratio = light, 0.0
    for foreground in (light, dark, SASS_WHITE, SASS_BLACK):
        ratio = bootstrap_contrast_ratio(background, foreground)
        if _ge(ratio, min_ratio):
            return foreground
        if _gt(ratio, best_ratio):
            best, best_ratio = foreground, ratio
    return best


def sass_color_contrast(
    background: SassColor,
    dark: SassColor = SASS_BLACK,
    light: SassColor = SASS_WHITE,
    min_ratio: float = 4.5,
    main_background: SassColor = SASS_WHITE,
) -> SassColor:
    real = sass_flatten(background, main_background)
    best, best_ratio = light, 0.0
    for foreground in (light, dark, SASS_WHITE, SASS_BLACK):
        ratio = bootstrap_contrast_ratio(real, foreground)
        if _gt(ratio, min_ratio):
            return foreground
        if _gt(ratio, best_ratio):
            best, best_ratio = foreground, ratio
    return best


def sass_scheme_contrast(
    background: SassColor, foregrounds: Sequence[SassColor], min_ratio: float
) -> SassColor:
    best, best_ratio = foregrounds[0], 0.0
    for foreground in foregrounds:
        ratio = bootstrap_contrast_ratio(background, foreground)
        if _gt(ratio, min_ratio):
            return foreground
        if _gt(ratio, best_ratio):
            best, best_ratio = foreground, ratio
    return best


def sass_has_enough_contrast(
    color1: SassColor, color2: SassColor, threshold: float = 500
) -> bool:
    difference = sum(
        abs(sass_channel(color1, i) - sass_channel(color2, i)) for i in range(3)
    )
    return _ge(difference, threshold)


def sass_luma(color: SassColor) -> float:
    return _luma([sass_channel(color, index) for index in range(3)]) * 100


def _to_hsl(color: SassColor) -> tuple[float, float, float]:
    hue, saturation, light = _hsl(color)
    return hue, saturation * 100, light * 100


def _hue_to_rgb(m1: float, m2: float, hue: float) -> float:
    if hue < 0:
        hue += 1
    if hue > 1:
        hue -= 1
    if hue < 1 / 6:
        return m1 + (m2 - m1) * hue * 6
    if hue < 1 / 2:
        return m2
    if hue < 2 / 3:
        return m1 + (m2 - m1) * (2 / 3 - hue) * 6
    return m1


def _from_hsl(hue: float, saturation: float, light: float, alpha: float) -> SassColor:
    hue = (hue % 360) / 360
    saturation /= 100
    light /= 100
    m2 = (
        light * (saturation + 1)
        if light <= 0.5
        else light + saturation - light * saturation
    )
    m1 = light * 2 - m2
    return (
        _hue_to_rgb(m1, m2, hue + 1 / 3) * 255,
        _hue_to_rgb(m1, m2, hue) * 255,
        _hue_to_rgb(m1, m2, hue - 1 / 3) * 255,
        alpha,
    )


def sass_lightness(color: SassColor) -> float:
    return _to_hsl(color)[2]


def sass_darken(color: SassColor, amount: float) -> SassColor:
    hue, saturation, light = _to_hsl(color)
    return _from_hsl(hue, saturation, min(max(light - amount, 0), 100), color[3])


def sass_lighten(color: SassColor, amount: float) -> SassColor:
    hue, saturation, light = _to_hsl(color)
    return _from_hsl(hue, saturation, min(max(light + amount, 0), 100), color[3])


def sass_adjust_lightness(color: SassColor, amount: float) -> SassColor:
    hue, saturation, light = _to_hsl(color)
    return _from_hsl(hue, saturation, light + amount, color[3])


def sass_increase_contrast(color1: SassColor, color2: SassColor) -> SassColor:
    light = sass_lightness(color1)
    step = -1 if sass_luma(color1) < sass_luma(color2) else 1
    iterations = 0
    while (
        _gt(light, 0.1)
        and _gt(99.9, light)
        and iterations < 25
        and not sass_has_enough_contrast(color1, color2)
    ):
        color1 = sass_adjust_lightness(color1, step)
        light += step
        iterations += 1
    return color1
