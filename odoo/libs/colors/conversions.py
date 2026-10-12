import re
from collections.abc import Sequence
from hashlib import sha512

__all__ = [
    "get_brightness",
    "get_hsl_from_seed",
    "get_lightness",
    "get_palette_color",
    "get_saturation",
    "hex_to_rgb",
    "lighten_hex",
    "rgb_to_hex",
]


def _hsl(rgb: Sequence[float]) -> tuple[float, float, float]:
    red, green, blue = (channel / 255 for channel in rgb[:3])
    high, low = max(red, green, blue), min(red, green, blue)
    delta = high - low
    if delta == 0:
        hue = 0.0
    elif high == red:
        hue = (60 * (green - blue) / delta) % 360
    elif high == green:
        hue = 60 * (blue - red) / delta + 120
    else:
        hue = 60 * (red - green) / delta + 240
    light = (high + low) / 2
    saturation = 0.0 if light in {0, 1} else delta / (1 - abs(2 * light - 1))
    return hue, saturation, light


def _luma(rgb: Sequence[float]) -> float:
    red, green, blue = rgb[:3]
    return (0.299 * red + 0.587 * green + 0.114 * blue) / 255


def get_saturation(rgb: Sequence[int]) -> float:
    return _hsl(rgb)[1]


def get_lightness(rgb: Sequence[int]) -> float:
    return _hsl(rgb)[2]


_HEX_COLOR_RE = re.compile(r"#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\Z")


def hex_to_rgb(hx: str) -> tuple[int, int, int]:
    if not _HEX_COLOR_RE.match(hx):
        raise ValueError(f"not a hexadecimal color: {hx!r}")
    digits = hx.removeprefix("#")
    if len(digits) == 3:
        digits = "".join(d * 2 for d in digits)
    red, green, blue = (int(digits[i : i + 2], 16) for i in range(0, 6, 2))
    return red, green, blue


def rgb_to_hex(rgb: Sequence[int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def get_brightness(color: str) -> float:
    return _luma(hex_to_rgb(color))


def get_palette_color(index: int, palette: Sequence[str], *, wrap: bool = False) -> str:
    if wrap:
        if not palette:
            raise ValueError("a color palette cannot be empty")
        index %= len(palette)
    if not 0 <= index < len(palette):
        raise IndexError(index)
    return palette[index]


def get_hsl_from_seed(seed: str) -> str:
    hashed_seed = sha512(seed.encode()).hexdigest()
    hue = int(hashed_seed[0:2], 16) * 360 / 255
    sat = int(hashed_seed[2:4], 16) * ((70 - 40) / 255) + 40
    lig = 45
    return f"hsl({hue:.0f}, {sat:.0f}%, {lig:.0f}%)"


def lighten_hex(color: str, factor: float) -> str:
    factor = max(0.0, min(factor, 1.0))
    return rgb_to_hex(
        tuple(
            round(channel + (255 - channel) * factor) for channel in hex_to_rgb(color)
        )
    )
