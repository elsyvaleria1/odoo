import re
from dataclasses import dataclass
from typing import Any

from odoo.libs.colors import (
    SassColor,
    parse_sass_color,
    sass_channel,
    sass_color_contrast,
    sass_color_to_css,
    sass_darken,
    sass_flatten,
    sass_increase_contrast,
    sass_lightness,
    sass_mix,
    sass_scheme_contrast,
    sass_shade,
)

# The header and footer parts website.scss colours with `o-element-colors`, by
# the selector of the rule it includes them in.
ELEMENT_SELECTORS = {
    "menu": ".navbar-light",
    "footer": ".o_footer",
    "copyright": ".o_footer .o_footer_copyright",
    "header-sales_one": "#wrapwrap .o_header_sales_one_bot",
    "header-sales_two": "#wrapwrap .o_header_sales_two_top",
    "header-sales_three": "#wrapwrap .o_header_sales_three_top",
    "header-sales_four": "#wrapwrap .o_header_sales_four_bot",
}

ELEMENT_KEYS = frozenset(
    key for name in ELEMENT_SELECTORS for key in (name, f"{name}-custom")
)

PRESET_KEYS = (
    "bg",
    "text",
    "headings",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "link",
    "btn-primary",
    "btn-primary-border",
    "btn-secondary",
    "btn-secondary-border",
)

EXTRACTION_USE = '@use "sass:color" as o-extract-color;\n'

EXTRACTION = """
@function o-extract($-value) {
    @if type-of($-value) == "color" {
        @return "c "
            + o-extract-color.channel($-value, "red", $space: rgb) + " "
            + o-extract-color.channel($-value, "green", $space: rgb) + " "
            + o-extract-color.channel($-value, "blue", $space: rgb) + " "
            + o-extract-color.channel($-value, "alpha", $space: rgb);
    }
    @if type-of($-value) == "number" {
        @return "n #{$-value}";
    }
    @return "s #{$-value}";
}
@mixin o-extract-map($-prefix, $-map) {
    @each $-key, $-value in $-map {
        @if $-value != null {
            --o-x-#{$-prefix}--#{$-key}: #{o-extract($-value)};
        }
    }
}
:root {
    @include o-extract-map("colors", $colors);
    @include o-extract-map("theme", $theme-colors);
    @include o-extract-map("grays", $grays);
    @include o-extract-map("palette", $o-color-palette);
    @include o-extract-map("theme-palette", $o-theme-color-palette);
    @include o-extract-map("gray-palette", $o-gray-color-palette);
    $-scheme: o-light-scheme();
    $-i: 0;
    @each $-foreground in map-get($-scheme, "foregrounds") {
        $-i: $-i + 1;
        --o-x-scheme--foreground-#{$-i}: #{o-extract($-foreground)};
    }
    --o-x-scheme--min-contrast-ratio: #{o-extract(map-get($-scheme, "min-contrast-ratio"))};
    --o-x-scheme--tint-mix: #{o-extract(map-get($-scheme, "tint-mix"))};
    --o-x-scheme--shade-mix: #{o-extract(map-get($-scheme, "shade-mix"))};
    --o-x-misc--body-bg: #{o-extract($body-bg)};
    --o-x-misc--contrast-dark: #{o-extract($color-contrast-dark)};
    --o-x-misc--contrast-light: #{o-extract($color-contrast-light)};
    --o-x-misc--min-contrast-ratio: #{o-extract($min-contrast-ratio)};
    --o-x-misc--combinations: #{o-extract(length($o-color-combinations))};
    --o-x-misc--btn-active-box-shadow: #{o-extract(inspect($btn-active-box-shadow))};
    --o-x-misc--btn-close-filter: #{o-extract(inspect($btn-close-filter))};
    --o-x-misc--btn-close-filter-dark: #{o-extract(inspect($btn-close-filter-dark))};
    --o-x-misc--nesting-selector: #{o-extract($o-color-extras-nesting-selector)};
    --o-x-misc--yiq-threshold: #{o-extract($o-yiq-min-opacity-threshold)};
    --o-x-misc--navbar-dark-active: #{o-extract($navbar-dark-active-color)};
    --o-x-misc--btn-close-white-filter: #{o-extract(inspect($btn-close-white-filter))};
    --o-x-misc--header-template: #{o-extract(o-website-value("header-template") or "")};
    --o-x-misc--layout: #{o-extract(o-website-value("layout") or "")};
    --o-x-misc--footer-scrolltop: #{o-extract(inspect(o-website-value("footer-scrolltop")))};
    @for $-n from 1 through 5 {
        @if o-website-value("o-cc#{$-n}-bg-gradient") {
            --o-x-gradient--#{$-n}: #{o-extract(o-website-value("o-cc#{$-n}-bg-gradient"))};
        }
    }
    @each $-name in (
        "btn-hover-bg-shade-amount",
        "btn-hover-bg-tint-amount",
        "btn-hover-border-shade-amount",
        "btn-hover-border-tint-amount",
        "btn-active-bg-shade-amount",
        "btn-active-bg-tint-amount",
        "btn-active-border-shade-amount",
        "btn-active-border-tint-amount"
    ) {
        --o-x-misc--#{$-name}: #{o-extract(map-get((
            "btn-hover-bg-shade-amount": $btn-hover-bg-shade-amount,
            "btn-hover-bg-tint-amount": $btn-hover-bg-tint-amount,
            "btn-hover-border-shade-amount": $btn-hover-border-shade-amount,
            "btn-hover-border-tint-amount": $btn-hover-border-tint-amount,
            "btn-active-bg-shade-amount": $btn-active-bg-shade-amount,
            "btn-active-bg-tint-amount": $btn-active-bg-tint-amount,
            "btn-active-border-shade-amount": $btn-active-border-shade-amount,
            "btn-active-border-tint-amount": $btn-active-border-tint-amount,
        ), $-name))};
    }
    @each $-level in ("h2", "h3", "h4", "h5", "h6", "display-1", "display-2", "display-3", "display-4") {
        @each $-prop, $-levels, $-base in (
            ("line-height", $heading-line-heights, $headings-line-height),
            ("margin-top", $heading-margin-tops, $headings-margin-top),
            ("margin-bottom", $heading-margin-bottoms, $headings-margin-bottom)
        ) {
            @if o-website-value("#{$-level}-#{$-prop}") != null or map-get($-levels, $-level) != $-base {
                --o-x-heading--#{$-level}-#{$-prop}: #{o-extract("1")};
            }
        }
    }
    @each $-key, $-value in (
        "header-font-size": o-website-value("header-font-size"),
        "logo-height": $o-theme-navbar-logo-height,
        "header-text-color": o-website-value("header-text-color"),
        "menu-border-width": o-website-value("menu-border-width"),
        "menu-border-radius": o-website-value("menu-border-radius"),
        "menu-box-shadow": o-website-value("menu-box-shadow"),
        "input-border-radius": o-website-value("input-border-radius"),
        "fixed-logo-height": if(type-of($o-theme-navbar-fixed-logo-height) == "number", 1, null)
    ) {
        @if $-value != null {
            --o-x-set--#{$-key}: #{o-extract("1")};
        }
    }
    @each $-key in map-keys($o-website-heading-sizes) {
        --o-x-heading-size--#{$-key}: #{o-extract("1")};
    }
    --o-x-misc--font-size-base: #{o-extract(inspect($font-size-base))};
    --o-x-misc--line-height-base: #{o-extract($line-height-base)};
    --o-x-misc--rfs: #{o-extract(inspect(($enable-rfs, $rfs-base-value, $rfs-factor, $rfs-breakpoint, $rfs-rem-value, $rfs-two-dimensional)))};
    @each $-key in map-keys($o-website-bootstrap-runtime) {
        --o-x-captured--#{$-key}: #{o-extract("1")};
    }
    $-j: 0;
    @each $-name in $o-we-auto-contrast-exclusions {
        $-j: $-j + 1;
        --o-x-exclusion--#{$-j}: #{o-extract($-name)};
    }
}
"""

_RE_EXTRACTED = re.compile(r"--o-x-([\w-]+?)--([\w-]+):\s*\"?([^;\"}]*)\"?[;}]")


@dataclass(frozen=True)
class ColorContext:
    colors: dict
    theme: dict
    grays: dict
    palette: dict
    theme_palette: dict
    gray_palette: dict
    foregrounds: tuple
    scheme_min_ratio: float
    tint_mix: SassColor
    shade_mix: SassColor
    body_bg: SassColor
    contrast_dark: SassColor
    contrast_light: SassColor
    min_contrast_ratio: float
    combinations: int
    btn_active_box_shadow: str
    btn_close_filter: str
    btn_close_filter_dark: str
    nesting_selector: str
    selectors: dict
    yiq_threshold: float
    navbar_dark_active: SassColor
    btn_close_white_filter: str
    header_template: str
    layout: str
    footer_scrolltop: bool
    captured: frozenset
    heading_rules: frozenset
    heading_sizes: frozenset
    set_values: frozenset
    rfs: tuple
    font_size_base: str
    line_height_base: float
    cc_gradients: dict
    navbar_dark_rules: tuple
    amounts: dict
    exclusions: frozenset


def _value(encoded):
    kind, _, rest = encoded.partition(" ")
    if kind == "c":
        return tuple(float(x) for x in rest.split())
    if kind == "n":
        number = rest.rstrip("%")
        return float(number)
    return rest


def _palette(values) -> dict:
    return {
        key: int(value) if isinstance(value, float) else value
        for key, value in values.items()
    }


_RE_COMBINATION_BG = re.compile(r"--o-cc-bg:\s*var\(--o-cc(\d+)-css-bg\)")


def _split_selectors(selectors):
    parts, depth, start = [], 0, 0
    for position, char in enumerate(selectors):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            parts.append(selectors[start:position].strip())
            start = position + 1
    parts.append(selectors[start:].strip())
    return tuple(part for part in parts if part)


def _combination_selectors(css):
    # What `@extend .o_ccN` added (a footer or header set to a combination)
    # rides the combination's own rule, so a runtime rule must repeat it.
    selectors = {}
    for prelude, body in _top_level_rules(css):
        if not prelude.startswith("@") and (match := _RE_COMBINATION_BG.search(body)):
            selectors.setdefault(int(match[1]), _split_selectors(prelude))
    return selectors


def _top_level_rules(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    rules, depth, start, prelude = [], 0, 0, ""
    for brace in re.finditer(r"[{}]", css):
        position = brace.start()
        if brace[0] == "{":
            if depth == 0:
                prelude = css[start:position].strip()
                start = position + 1
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                rules.append((prelude, css[start:position]))
                start = position + 1
    return rules


def _navbar_dark_rules(css):
    # What `@extend .navbar-dark` gives a dark header, as `.navbar-light` rules;
    # None when one sits in an at-rule, which a runtime rule does not restate.
    rules = []
    for prelude, body in _top_level_rules(css):
        if ".navbar-dark" not in prelude and ".navbar-dark" not in body:
            continue
        if prelude.startswith("@"):
            return None
        selectors = [
            selector.replace(".navbar-dark", ".navbar-light")
            for selector in _split_selectors(prelude)
            if ".navbar-dark" in selector
        ]
        if selectors:
            rules.append(f"{','.join(selectors)}{{{body}}}")
    return tuple(rules)


def named_color_css(context, value):
    # website.scss's format-color(): a palette name resolves through o-color().
    color = parse_user_color(value)
    if isinstance(color, str):
        r = _Resolver(context, {})
        color = r.color(color) or context.theme.get(color) or context.grays.get(color)
    return _css(color) if isinstance(color, tuple) else None


def small_font_size_em(context, rem) -> str | None:
    # Bootstrap's `small`: `$o-small-font-size / $font-size-base * 1em`.
    match = re.fullmatch(r"([\d.]+)(px|rem)", context.font_size_base)
    if not match:
        return None
    base = float(match[1]) / (context.rfs[4] if match[2] == "px" else 1)
    return f"{sass_number(rem / base)}em"


def _rfs_parameters(encoded) -> tuple:
    enabled, base, factor, breakpoint_px, rem, two_dimensional = (
        part.strip() for part in encoded.strip("()").split(",")
    )
    return (
        enabled == "true",
        float(base),
        float(factor),
        float(breakpoint_px),
        float(rem),
        two_dimensional == "true",
    )


def sass_number(value):
    return f"{round(value, 10):.10f}".rstrip("0").rstrip(".") or "0"


def rfs_fluid_value(context, value):
    enabled, base, factor, breakpoint_px, rem, two_dimensional = context.rfs
    match = re.fullmatch(r"(-?[\d.]+)(px|rem)", value)
    if not match:
        return value
    number = float(match[1]) * (rem if match[2] == "rem" else 1)
    if abs(number) <= base or not enabled:
        return f"{sass_number(number / rem)}rem"
    minimum = base + (abs(number) - base) / factor
    variable = (abs(number) - minimum) * 100 / breakpoint_px
    sign = "-" if number < 0 else "+"
    minimum_rem = f"{'-' if number < 0 else ''}{sass_number(minimum / rem)}rem"
    unit = "vmin" if two_dimensional else "vw"
    return f"calc({minimum_rem} {sign} {sass_number(variable)}{unit})"


def parse_extraction(css):
    groups = {}
    for group, key, encoded in _RE_EXTRACTED.findall(css):
        groups.setdefault(group, {})[key] = _value(encoded)
    if "scheme" not in groups or "misc" not in groups:
        raise ValueError("the compiled stylesheet carries no palette extraction")
    scheme, misc = groups["scheme"], groups["misc"]
    foregrounds = tuple(
        scheme[k]
        for k in sorted(
            (k for k in scheme if k.startswith("foreground-")),
            key=lambda k: int(k.rsplit("-", 1)[1]),
        )
    )
    return ColorContext(
        colors=groups.get("colors", {}),
        theme=groups.get("theme", {}),
        grays=groups.get("grays", {}),
        palette=_palette(groups.get("palette", {})),
        theme_palette=_palette(groups.get("theme-palette", {})),
        gray_palette=_palette(groups.get("gray-palette", {})),
        foregrounds=foregrounds,
        scheme_min_ratio=scheme["min-contrast-ratio"],
        tint_mix=scheme["tint-mix"],
        shade_mix=scheme["shade-mix"],
        body_bg=misc["body-bg"],
        contrast_dark=misc["contrast-dark"],
        contrast_light=misc["contrast-light"],
        min_contrast_ratio=misc["min-contrast-ratio"],
        combinations=int(misc["combinations"]),
        btn_active_box_shadow=misc["btn-active-box-shadow"],
        btn_close_filter=misc["btn-close-filter"],
        btn_close_filter_dark=misc["btn-close-filter-dark"],
        nesting_selector=misc["nesting-selector"],
        selectors=_combination_selectors(css),
        yiq_threshold=misc["yiq-threshold"],
        navbar_dark_active=misc["navbar-dark-active"],
        btn_close_white_filter=misc["btn-close-white-filter"],
        header_template=misc.get("header-template", ""),
        layout=misc.get("layout", "").strip("'\""),
        footer_scrolltop=misc.get("footer-scrolltop") == "true",
        captured=frozenset(groups.get("captured", {})),
        heading_rules=frozenset(groups.get("heading", {})),
        heading_sizes=frozenset(groups.get("heading-size", {})),
        set_values=frozenset(groups.get("set", {})),
        rfs=_rfs_parameters(misc["rfs"]),
        font_size_base=misc.get("font-size-base", "1rem"),
        line_height_base=misc.get("line-height-base", 1.5),
        cc_gradients={
            int(index): gradient
            for index, gradient in groups.get("gradient", {}).items()
        },
        navbar_dark_rules=_navbar_dark_rules(css),
        amounts={k: v for k, v in misc.items() if k.endswith("-amount")},
        exclusions=frozenset(groups.get("exclusion", {}).values()),
    )


def parse_user_color(raw):
    value = str(raw or "").strip()
    if value in ("", "null", "NULL"):
        return None
    if value[:1] in "'\"" and value[-1:] == value[:1]:
        return value[1:-1]
    if value.isdigit():
        return int(value)
    return parse_sass_color(value)


def _normalize_elements(palette):
    # website's secondary_variables.scss: a part given a colour instead of a
    # combination is combination 1 with that colour as its custom one.
    palette = dict(palette)
    for name in ELEMENT_SELECTORS:
        base = palette.get(name)
        if base is not None and not isinstance(base, int):
            palette[f"{name}-custom"] = palette.get(f"{name}-custom") or base
            palette[name] = 1
    return palette


class _Resolver:
    def __init__(self, context, overrides) -> None:
        self.context = context
        self.overrides = overrides
        self.palette = _normalize_elements({**context.palette, **overrides})
        # website's secondary_variables.scss excludes every user-set colour
        # from auto-contrast: `map-keys($o-user-color-palette)`.
        self.exclusions = context.exclusions | set(overrides)

    def _chain(self, value, palette):
        # o-related-color: at most ten redirections through the three palettes;
        # a name found in none of them, or still a name past the limit, is null.
        for _ in range(11):
            if isinstance(value, int):
                value = f"o-cc{value}-bg"
            if value is None or isinstance(value, tuple):
                return value
            for table in (
                palette,
                self.context.theme_palette,
                self.context.gray_palette,
            ):
                if value in table:
                    value = table[value]
                    break
            else:
                return None
        return None

    def related(self, name):
        # o-related-color without use-cc-bg: a combination number stays one.
        value = name
        for _ in range(11):
            if value is None or isinstance(value, (int, tuple)):
                return value
            for table in (
                self.palette,
                self.context.theme_palette,
                self.context.gray_palette,
            ):
                if value in table:
                    value = table[value]
                    break
            else:
                return None
        return None

    def color(self, key):
        value = self._chain(self.palette.get(key), self.palette)
        if key in self.overrides:
            return value
        compiled = self._chain(self.context.palette.get(key), self.context.palette)
        return self.context.colors.get(key) if value == compiled else value

    def scheme_contrast(self, background):
        return sass_scheme_contrast(
            background, self.context.foregrounds, self.context.scheme_min_ratio
        )

    def auto_contrast(self, color1, color2, name):
        if name in self.exclusions:
            return color1
        return sass_increase_contrast(color1, color2)


def _css(value):
    if isinstance(value, tuple):
        return sass_color_to_css(value)
    return str(value)


def _rgb_list(color) -> str:
    return ", ".join(str(sass_channel(color, i)) for i in range(3))


def _prepare_button_vals(r, background, border) -> dict[str, Any]:
    ctx = r.context
    color = r.scheme_contrast(background)
    shades = color == ctx.foregrounds[0]

    def shift(value, action):
        amount = ctx.amounts[f"btn-{action}-{'shade' if shades else 'tint'}-amount"]
        target = ctx.shade_mix if shades else ctx.tint_mix
        return sass_mix(target, value, amount)

    hover_bg = shift(background, "hover-bg")
    active_bg = shift(background, "active-bg")
    return {
        "btn-color": color,
        "btn-bg": background,
        "btn-border-color": border,
        "btn-hover-color": r.scheme_contrast(hover_bg),
        "btn-hover-bg": hover_bg,
        "btn-hover-border-color": shift(border, "hover-border"),
        "btn-focus-shadow-rgb": _rgb_list(sass_mix(color, border, 15)),
        "btn-active-color": r.scheme_contrast(active_bg),
        "btn-active-bg": active_bg,
        "btn-active-border-color": shift(border, "active-border"),
        "btn-active-shadow": ctx.btn_active_box_shadow,
        "btn-disabled-color": r.scheme_contrast(background),
        "btn-disabled-bg": background,
        "btn-disabled-border-color": border,
    }


def _outline_button(r, color) -> dict:
    contrast = r.scheme_contrast(color)
    return {
        "btn-color": color,
        "btn-border-color": color,
        "btn-hover-color": contrast,
        "btn-hover-bg": color,
        "btn-hover-border-color": color,
        "btn-focus-shadow-rgb": _rgb_list(color),
        "btn-active-color": contrast,
        "btn-active-bg": color,
        "btn-active-border-color": color,
        "btn-active-shadow": r.context.btn_active_box_shadow,
        "btn-disabled-color": color,
        "btn-disabled-bg": "transparent",
        "btn-disabled-border-color": color,
        "gradient": "none",
    }


def css_values(r, index) -> dict:
    cc = f"o-cc{index}"
    bg = r.color(f"{cc}-bg")
    text = r.color(f"{cc}-text")
    values = {"bg": bg}
    if text is not None:
        values["color"] = text
    elif bg is not None and bg[3] > 0:
        values["color"] = sass_color_contrast(
            bg,
            r.context.contrast_dark,
            r.context.contrast_light,
            r.context.min_contrast_ratio,
            r.context.body_bg,
        )
    if bg is not None and bg[3] > 0:
        values["muted"] = _mute(values["color"])
    values["heading"] = r.color(f"{cc}-headings")
    for level in (2, 3, 4, 5, 6):
        values[f"heading-{level}"] = r.color(f"{cc}-h{level}")

    link_color = r.color(f"{cc}-link") or r.context.theme["primary"]
    values["link"] = r.auto_contrast(link_color, bg, f"{cc}-link")
    values["link-hover"] = r.auto_contrast(
        sass_darken(link_color, 15), bg, f"{cc}-link"
    )

    for kind in ("primary", "secondary"):
        button = r.color(f"{cc}-btn-{kind}")
        button_color = button or r.context.theme[kind]
        border_color = r.color(f"{cc}-btn-{kind}-border") or button_color
        outline = button or sass_increase_contrast(border_color, bg)
        for key, value in _prepare_button_vals(r, button_color, border_color).items():
            values[f"btn-fill-{kind}-{key}"] = value
        for key, value in _outline_button(r, outline).items():
            values[f"btn-outline-{kind}-{key}"] = value
        if kind == "primary":
            values["btn-primary"] = button_color
            values["btn-primary-contrast"] = r.scheme_contrast(button_color)
    return {
        f"--o-cc{index}-css-{key}": _css(value)
        for key, value in values.items()
        if value is not None
    }


def tokens(r, index) -> dict:
    cc = f"o-cc{index}"
    bg = r.color(f"{cc}-bg")
    raw = {key: r.color(f"{cc}-{key}") for key in PRESET_KEYS}
    out = {
        key: raw[key]
        for key in ("bg", "headings", "h2", "h3", "h4", "h5", "h6", "text")
        if raw[key] is not None
    }
    text = out.get("text") or r.scheme_contrast(bg)
    headings = out.get("headings") or text
    out.setdefault("text", text)
    out.setdefault("headings", headings)
    for level in ("h2", "h3", "h4", "h5", "h6"):
        out.setdefault(level, headings)
    link_color = raw["link"] or r.context.theme["primary"]
    out["link"] = r.auto_contrast(link_color, bg, f"{cc}-link")
    for kind in ("primary", "secondary"):
        button_color = raw[f"btn-{kind}"] or r.context.theme[kind]
        out[f"btn-{kind}"] = button_color
        out[f"btn-{kind}-text"] = r.scheme_contrast(button_color)
        out[f"btn-{kind}-border"] = raw[f"btn-{kind}-border"] or button_color
    return {
        f"--{cc}-{key}": _css(value) for key, value in out.items() if value is not None
    }


def _declarations(r, index):
    return tokens(r, index) | css_values(r, index)


def _is_dark(color) -> bool:
    return sass_lightness(color) < 50


def _mute(color) -> tuple:
    red, green, blue, alpha = color
    return (red, green, blue, alpha - alpha * 0.3)


def _cc_shape(r, index) -> dict:
    # html_editor.common.scss's o-cc-shape.
    cc = f"o-cc{index}"
    bg = r.color(f"{cc}-bg")
    opaque = bg is not None and bg[3] > 0
    headings = opaque or r.color(f"{cc}-headings") is not None
    return {
        "background": bg is not None,
        "color": opaque or r.color(f"{cc}-text") is not None,
        "color-property": True,
        "extras": opaque,
        "headings": headings,
        "levels": tuple(
            headings or r.color(f"{cc}-h{level}") is not None
            for level in (2, 3, 4, 5, 6)
        ),
        "components": True,
    }


def _element_state(r, name) -> tuple:
    # website.scss's o-element-color-state.
    index, custom = r.related(name), r.related(f"{name}-custom")
    legacy = (index is not None and not isinstance(index, int)) or isinstance(
        custom, int
    )
    return (
        index if isinstance(index, int) else None,
        None if isinstance(custom, int) else custom,
        legacy,
    )


def _element_background(r, name):
    if name != "copyright":
        return r.context.body_bg
    return r.color("footer-custom") or r.color("footer") or r.context.body_bg


def _element_shape(r, name) -> str | dict:
    # website.scss's o-element-color-shape.
    index, custom, legacy = _element_state(r, name)
    if legacy:
        return "legacy"
    extras = custom is not None and custom[3] > r.context.yiq_threshold
    if index is None:
        cc = {
            "background": False,
            "color": False,
            "extras": False,
            "headings": False,
            "levels": (False,) * 5,
        }
    else:
        cc = _cc_shape(r, index)
    return {
        "background": cc["background"] or custom is not None,
        "color": cc["color"] or extras,
        "color-property": extras if custom is not None else True,
        "extras": cc["extras"] or extras,
        "headings": cc["headings"] or extras,
        "levels": tuple(level or extras for level in cc["levels"]),
        "components": index is not None,
    }


def _element_declarations(r, name):
    # website.scss's o-element-color-values, plus what the builder reads back:
    # `--menu` (the combination) and `--menu-custom` (the colour).
    index, custom, legacy = _element_state(r, name)
    if legacy:
        return {}
    values = {}
    if index is not None:
        prefix = f"--o-cc{index}-css-"
        for key in css_values(r, index):
            values[key.removeprefix(prefix)] = f"var({key})"
        values["cc-bg"] = f"var({prefix}bg)"
    if custom is not None:
        values["bg"] = _css(custom)
        if custom[3] > r.context.yiq_threshold:
            yiq = sass_color_contrast(
                custom,
                r.context.contrast_dark,
                r.context.contrast_light,
                r.context.min_contrast_ratio,
                _element_background(r, name),
            )
            values["color"] = _css(yiq)
            values["muted"] = _css(_mute(yiq))
    declarations = {f"--o-{name}-css-{key}": value for key, value in values.items()}
    if index is not None:
        declarations[f"--{name}"] = str(index)
    custom_color = r.color(f"{name}-custom")
    if custom_color is not None:
        declarations[f"--{name}-custom"] = _css(custom_color)
    return declarations


def _menu_color(r):
    return r.color("menu-custom") or r.color("menu")


def _menu_declarations(r) -> dict:
    color = _menu_color(r)
    if color is None:
        return {}
    return {
        "--o-menu-color": _css(color),
        "--o-menu-color-shade": _css(sass_shade(color, 5)),
    }


def _contrast(r, color, main_background):
    return sass_color_contrast(
        color,
        r.context.contrast_dark,
        r.context.contrast_light,
        r.context.min_contrast_ratio,
        main_background,
    )


def _same_color(color1, color2) -> bool:
    return all(abs(a - b) < 1e-11 for a, b in zip(color1, color2, strict=True))


def _scrolltop_declarations(r) -> dict:
    # website.scss's o-footer-scrolltop-colors.
    transparent = (0.0, 0.0, 0.0, 0.0)
    footer = r.color("footer-custom") or r.color("footer") or transparent
    footer = sass_flatten(footer, r.context.body_bg)
    copyright_color = r.color("copyright-custom") or r.color("copyright")
    copyright_color = sass_flatten(copyright_color or transparent, footer)
    color = _contrast(r, footer, footer)
    text = color
    if _same_color(footer, copyright_color):
        text = (*_contrast(r, footer, r.context.body_bg)[:3], 0.5)
    values = {
        "bg": footer,
        "color": color,
        "text": text,
        "hover-bg": copyright_color,
        "hover-color": _contrast(r, copyright_color, footer),
    }
    return {f"--o-footer-scrolltop-{key}": _css(value) for key, value in values.items()}


def _layout_shape(r) -> tuple:
    # A layout other than full width drops its header padding when the menu
    # has no colour of its own, or the body's.
    color = _menu_color(r)
    if r.context.layout == "full":
        return (color is not None,)
    body = r.color("body")
    return (
        color is not None,
        color is None or (body is not None and _same_color(color, body)),
    )


def _menu_is_dark(r) -> bool:
    # website.scss: `color-contrast(o-menu-color()) != $color-contrast-dark`.
    color = _menu_color(r)
    if color is None:
        return False
    return _contrast(r, color, r.context.body_bg) != r.context.contrast_dark


def _active_sales_header(context) -> str | None:
    template = context.header_template.strip("'\"")
    if template in ("sales_one", "sales_two", "sales_three", "sales_four"):
        return f"header-{template}"
    return None


def _compiled_elements(context):
    sales = _active_sales_header(context)
    return tuple(
        name
        for name in ELEMENT_SELECTORS
        if not name.startswith("header-sales_") or name == sales
    )


def _combination_gradient(context, gradients, index):
    if index is None:
        return None
    key = f"o-cc{index}-bg-gradient"
    return gradients[key] if key in gradients else context.cc_gradients.get(index)


def fits_runtime(context, overrides, gradients):
    r, compiled = _Resolver(context, overrides), _Resolver(context, {})
    for name in _compiled_elements(context):
        # A part's combination gradient is a rule the runtime can restate but
        # not take back.
        compiled_index = _element_state(compiled, name)[0]
        if context.cc_gradients.get(compiled_index) and not _combination_gradient(
            context, gradients, _element_state(r, name)[0]
        ):
            return False
    if _declarations(r, 1) != _declarations(compiled, 1):
        return False
    if any(
        _cc_shape(r, index) != _cc_shape(compiled, index)
        for index in range(1, context.combinations + 1)
    ):
        return False
    elements = _compiled_elements(context)
    for name in ELEMENT_SELECTORS:
        if name not in elements:
            if _element_declarations(r, name) != _element_declarations(compiled, name):
                return False
            continue
        shape = _element_shape(r, name)
        if shape == "legacy" or shape != _element_shape(compiled, name):
            return False
    if _layout_shape(r) != _layout_shape(compiled):
        return False
    menu_dark = _menu_is_dark(r)
    compiled_dark = _menu_is_dark(compiled)
    return menu_dark == compiled_dark or (
        menu_dark and context.navbar_dark_rules is not None
    )


def _selectors(context, index):
    extended = context.selectors.get(index) if context else None
    return extended or (f".o_cc{index}",)


def _btn_close_filter(context, dark):
    if dark:
        return context.btn_close_filter_dark
    return "initial" if context.btn_close_filter == "null" else context.btn_close_filter


def _btn_close_rule(context, selectors, bg, compiled_bg) -> str | None:
    if not bg or not compiled_bg or _is_dark(bg) == _is_dark(compiled_bg):
        return None
    dark = _is_dark(bg)
    suffix = ".btn-close" if dark else ".btn-close:not(.btn-close-white)"
    nested = ",".join(
        f"{nesting.replace('&', selector)} {suffix}"
        for selector in selectors
        for nesting in _split_selectors(context.nesting_selector)
    )
    return f"{nested}{{--btn-close-filter:{_btn_close_filter(context, dark)}}}"


def _element_bg(r, name):
    index = _element_state(r, name)[0]
    return r.color(f"o-cc{index}-bg") if index is not None else None


def _menu_dark_rules(context) -> tuple:
    active = context.navbar_dark_active
    variables = ";".join(
        f"--{name}:{_css((*active[:3], alpha))}"
        for name, alpha in (
            ("NavLinkWithBackground-bg-color", 0.1),
            ("NavLinkWithBackground-bg-color--hover", 0.2),
            ("NavStretch-placeholder-color", 0.3),
            ("HeaderSeparator-bg-color", 0.15),
        )
    )
    return (
        f".navbar-light{{{variables}}}",
        *context.navbar_dark_rules,
        f".navbar-light .btn-close{{filter:{context.btn_close_white_filter}}}",
    )


def _gradient_selectors(context, key):
    # Where website.scss includes o-add-gradient for each gradient value.
    if match := re.fullmatch(r"o-cc(\d)-bg-gradient", key):
        return _selectors(context, int(match[1]))
    if key == "menu-gradient":
        return (
            ELEMENT_SELECTORS["menu"],
            f"{ELEMENT_SELECTORS['menu']} .o_navbar_mobile",
        )
    if key == "menu-secondary-gradient":
        sales = _active_sales_header(context) if context else None
        return (ELEMENT_SELECTORS[sales],) if sales else ()
    return (ELEMENT_SELECTORS[key.removesuffix("-gradient")],)


def gradient_css(context, overrides, gradients):
    # website.scss order: each gradient value's own rule, then the rule that
    # gives a part its combination's gradient (which wins where both apply).
    rules = [
        rule
        for key, gradient in sorted(gradients.items())
        if (rule := gradient_rule(context, key, gradient))
    ]
    if context is None:
        return rules
    r, compiled = _Resolver(context, overrides), _Resolver(context, {})
    for name in _compiled_elements(context):
        index = _element_state(r, name)[0]
        gradient = _combination_gradient(context, gradients, index)
        compiled_gradient = context.cc_gradients.get(_element_state(compiled, name)[0])
        own = (
            f"{'menu-secondary' if name.startswith('header-sales_') else name}-gradient"
        )
        if gradient and (gradient != compiled_gradient or own in gradients):
            rules.append(
                f"{ELEMENT_SELECTORS[name]}{{background-color:rgba(0, 0, 0, 0);"
                f"background-image:{gradient}}}"
            )
    return rules


def gradient_rule(context, key, gradient) -> str | None:
    selectors = ",".join(_gradient_selectors(context, key))
    if not selectors:
        return None
    return (
        f"{selectors}{{background-color:rgba(0, 0, 0, 0);background-image:{gradient}}}"
    )


def palette_css(context, overrides) -> tuple:
    r, compiled = _Resolver(context, overrides), _Resolver(context, {})
    declarations, rules = {}, []

    def restate(ours, theirs):
        for key in sorted(ours.keys() | theirs.keys()):
            value = ours.get(key, "initial")
            if value != theirs.get(key):
                declarations[key] = value

    for index in range(2, context.combinations + 1):
        restate(_declarations(r, index), _declarations(compiled, index))
        rule = _btn_close_rule(
            context,
            _selectors(context, index),
            r.color(f"o-cc{index}-bg"),
            compiled.color(f"o-cc{index}-bg"),
        )
        if rule:
            rules.append(rule)
    for name in _compiled_elements(context):
        restate(_element_declarations(r, name), _element_declarations(compiled, name))
        rule = _btn_close_rule(
            context,
            (ELEMENT_SELECTORS[name],),
            _element_bg(r, name),
            _element_bg(compiled, name),
        )
        if rule:
            rules.append(rule)
    restate(_menu_declarations(r), _menu_declarations(compiled))
    if context.footer_scrolltop:
        restate(_scrolltop_declarations(r), _scrolltop_declarations(compiled))
    if _menu_is_dark(r) and not _menu_is_dark(compiled):
        rules.extend(_menu_dark_rules(context))
    return declarations, rules
