import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = [
    "WCAG_AA_NON_TEXT",
    "WCAG_AA_TEXT",
    "contrast_ratio",
    "rgb_to_oklch",
    "with_contrast",
]

WCAG_AA_TEXT = 4.5
WCAG_AA_NON_TEXT = 3.0

_SEARCH_STEPS = 24
_GRID_STEPS = 1024


def _linear(channel: float) -> float:
    channel /= 255
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _gamma(channel: float) -> float:
    if channel <= 0.0031308:
        return 255 * 12.92 * channel
    return 255 * (1.055 * channel ** (1 / 2.4) - 0.055)


def relative_luminance(rgb: Sequence[float]) -> float:
    red, green, blue = (_linear(channel) for channel in rgb[:3])
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: Sequence[float], background: Sequence[float]) -> float:
    lighter, darker = sorted(
        (relative_luminance(foreground), relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def rgb_to_oklch(rgb: Sequence[float]) -> tuple[float, float, float]:
    red, green, blue = (_linear(channel) for channel in rgb[:3])
    long = math.cbrt(0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue)
    medium = math.cbrt(0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue)
    short = math.cbrt(0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue)
    lightness = 0.2104542553 * long + 0.7936177850 * medium - 0.0040720468 * short
    a = 1.9779984951 * long - 2.4285922050 * medium + 0.4505937099 * short
    b = 0.0259040371 * long + 0.7827717662 * medium - 0.8086757660 * short
    return lightness, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def _oklch_to_linear(
    lightness: float, chroma: float, hue: float
) -> tuple[float, float, float]:
    a = chroma * math.cos(math.radians(hue))
    b = chroma * math.sin(math.radians(hue))
    long = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    medium = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    short = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        4.0767416621 * long - 3.3077115913 * medium + 0.2309699292 * short,
        -1.2684380046 * long + 2.6097574011 * medium - 0.3413193965 * short,
        -0.0041960863 * long - 0.7034186147 * medium + 1.7076147010 * short,
    )


def _in_gamut(lightness: float, chroma: float, hue: float) -> bool:
    return all(
        -1e-6 <= channel <= 1 + 1e-6
        for channel in _oklch_to_linear(lightness, chroma, hue)
    )


def oklch_to_rgb(lightness: float, chroma: float, hue: float) -> tuple[int, int, int]:
    lightness = min(max(lightness, 0.0), 1.0)
    if not _in_gamut(lightness, chroma, hue):
        low, high = 0.0, chroma
        for _ in range(_SEARCH_STEPS):
            middle = (low + high) / 2
            if _in_gamut(lightness, middle, hue):
                low = middle
            else:
                high = middle
        chroma = low
    red, green, blue = (
        round(min(max(_gamma(min(max(c, 0.0), 1.0)), 0.0), 255.0))
        for c in _oklch_to_linear(lightness, chroma, hue)
    )
    return red, green, blue


def with_contrast(
    rgb: Sequence[float], surfaces: Iterable[Sequence[float]], minimum: float
) -> tuple[int, int, int]:
    surfaces = tuple(surfaces)

    def passes(candidate: Sequence[float]) -> bool:
        return all(
            contrast_ratio(candidate, surface) >= minimum for surface in surfaces
        )

    lightness, chroma, hue = rgb_to_oklch(rgb)
    start = oklch_to_rgb(lightness, chroma, hue)
    if passes(start):
        return start

    def passes_at(candidate: float) -> bool:
        return passes(oklch_to_rgb(candidate, chroma, hue))

    def nearest_passing(far: float) -> float:
        near = lightness
        for _ in range(_SEARCH_STEPS):
            middle = (near + far) / 2
            if passes_at(middle):
                far = middle
            else:
                near = middle
        return far

    reachable = [bound for bound in (0.0, 1.0) if passes_at(bound)]
    if not reachable:
        band = [
            step / _GRID_STEPS
            for step in range(1, _GRID_STEPS)
            if passes_at(step / _GRID_STEPS)
        ]
        if band:
            reachable = [min(band, key=lambda candidate: abs(candidate - lightness))]
    if not reachable:
        msg = f"no lightness gives {minimum}:1 against {surfaces}"
        raise ValueError(msg)
    best = min(
        (nearest_passing(bound) for bound in reachable),
        key=lambda candidate: abs(candidate - lightness),
    )
    return oklch_to_rgb(best, chroma, hue)
