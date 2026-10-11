import base64
import re
from itertools import pairwise

from odoo.libs.colors import hex_to_rgb
from odoo.libs.colors.contrast import WCAG_AA_NON_TEXT, WCAG_AA_TEXT, contrast_ratio
from odoo.tests import TransactionCase, tagged
from odoo.tests.css import (
    composite,
    parse_colour,
    parse_per_selector,
    pick_dark,
    resolve,
    scheme_scopes,
    settle,
    token_colour,
)

DARK_BUNDLE = "web.assets_web_dark"

LIST_HEADER = ".o_list_renderer .o_list_table thead th"

TEXT_TOKENS = (
    "--o-label-1",
    "--o-label-2",
    "--o-text",
    "--o-text-muted",
    "--o-action-text",
    "--o-success-text",
    "--o-info-text",
    "--o-warning-text",
    "--o-danger-text",
    "--heading-color",
    "--link-color",
    "--body-color",
    "--emphasis-color",
    "--secondary-color",
)

SURFACE_TOKENS = (
    "--body-bg",
    "--o-bg-view",
    "--o-bg-raised",
    "--o-bg-active",
    "--o-dropdown-bg",
    "--o-popover-bg",
    "--o-gray-100",
    "--o-gray-200",
    "--secondary-bg",
    "--tertiary-bg",
)


RFS_REFERENCE_WIDTH = 1200
ROOT_FONT_SIZE = 16


def _font_size_px(css_value):
    css_value = css_value.strip()
    calc = re.fullmatch(r"calc\(\s*([\d.]+)rem\s*\+\s*([\d.]+)vw\s*\)", css_value)
    if calc:
        rem, vw = (float(g) for g in calc.groups())
        return rem * ROOT_FONT_SIZE + vw * RFS_REFERENCE_WIDTH / 100
    rem = re.fullmatch(r"([\d.]+)rem", css_value)
    if not rem:
        raise ValueError(f"not a font size: {css_value!r}")
    return float(rem.group(1)) * ROOT_FONT_SIZE


def _matching_paren(css_value, open_index):
    depth = 0
    for index in range(open_index, len(css_value)):
        if css_value[index] == "(":
            depth += 1
        elif css_value[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _top_level_comma(css_value):
    depth = 0
    for index, char in enumerate(css_value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            return index
    return -1


def _resolve_var_fallbacks(css_value):
    out = []
    index = 0
    while index < len(css_value):
        if not css_value.startswith("var(", index):
            out.append(css_value[index])
            index += 1
            continue
        end = _matching_paren(css_value, index + 3)
        if end == -1:
            out.append(css_value[index:])
            break
        inner = css_value[index + 4 : end]
        comma = _top_level_comma(inner)
        if comma == -1:
            out.append(css_value[index : end + 1])
        else:
            out.append(_resolve_var_fallbacks(inner[comma + 1 :].strip()))
        index = end + 1
    return "".join(out)


def _parse_color(css_value):
    css_value = _resolve_var_fallbacks(css_value.strip())
    hex_match = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", css_value)
    if hex_match:
        digits = hex_match.group(1)
        if len(digits) == 3:
            digits = "".join(d * 2 for d in digits)
        return [int(digits[i : i + 2], 16) for i in (0, 2, 4)], 1.0
    fn_match = re.fullmatch(r"rgba?\(([^)]*)\)", css_value, re.IGNORECASE)
    if not fn_match:
        raise ValueError(f"not a colour: {css_value!r}")
    numbers = [float(n) for n in re.findall(r"-?[\d.]+", fn_match.group(1))]
    if len(numbers) < 3:
        raise ValueError(f"not a colour: {css_value!r}")
    return numbers[:3], (numbers[3] if len(numbers) > 3 else 1.0)


def _composite(fg, alpha, bg):
    return [alpha * f + (1 - alpha) * b for f, b in zip(fg, bg, strict=True)]


def _declaration(css, prop):
    match = re.search(rf"(?:^|[;{{])\s*{re.escape(prop)}\s*:\s*([^;}}]+)", css)
    return match.group(1).strip() if match else None


@tagged("-at_install", "post_install")
class TestScssDesignSystem(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = cls._compiled("web.assets_backend")

    @classmethod
    def _compiled(cls, bundle_name):
        attachments = (
            cls.env["ir.qweb"]._get_asset_bundle(bundle_name, css=True, js=False).css()
        )
        if not attachments:
            raise AssertionError(f"{bundle_name} produced no CSS attachment")
        return "".join(
            base64.b64decode(attachment.datas).decode() for attachment in attachments
        )

    def _matches(self, selector, css=None):
        pattern = (
            r"(?:^|(?<=[}\s;]))([^{}@]*" + re.escape(selector) + r"[^{}]*)\{([^}]*)\}"
        )
        haystack = self.css if css is None else css
        return re.findall(pattern, haystack, re.MULTILINE)

    def _rule(self, selector, declaring=None, css=None):
        candidates = [
            (selectors, body)
            for selectors, body in self._matches(selector, css=css)
            if declaring is None or _declaration(body, declaring) is not None
        ]
        exact = [
            (selectors, body)
            for selectors, body in candidates
            if any(part.strip() == selector for part in selectors.split(","))
        ]
        bodies = [body for _, body in (exact or candidates)]
        self.assertTrue(
            bodies, f"no rule found for {selector} (declaring {declaring!r})"
        )
        return bodies[-1]

    def _page_background(self):
        value = _declaration(self.css, "--body-bg")
        self.assertTrue(value, "--body-bg is not defined")
        return _parse_color(value)[0]

    def test_every_text_token_meets_wcag_aa_on_every_surface(self):
        light, dark = scheme_scopes(self._compiled("web.assets_web"))
        failures = []
        for scheme, scope in (("light", light), ("dark", dark)):
            is_dark = scope is dark
            page = token_colour("--body-bg", scope, dark=is_dark)
            for surface_name in SURFACE_TOKENS:
                surface = composite(
                    token_colour(surface_name, scope, dark=is_dark), page
                )
                for text_name in TEXT_TOKENS:
                    text = composite(
                        token_colour(text_name, scope, dark=is_dark), surface
                    )
                    ratio = contrast_ratio(text, surface)
                    if ratio < WCAG_AA_TEXT:
                        failures.append(
                            f"{scheme}: {text_name} on {surface_name} {ratio:.2f}:1"
                        )
        self.assertFalse(
            failures,
            f"{len(failures)} text/surface pair(s) fall below WCAG AA "
            f"({WCAG_AA_TEXT}:1):\n  " + "\n  ".join(failures),
        )

    def test_every_app_accent_meets_wcag_aa_on_every_surface(self):
        apps = self.env["ir.ui.menu"].search(
            [("parent_id", "=", False), ("web_accent", "!=", False)]
        )
        self.assertTrue(apps, "no installed app has an accent to check")
        light, dark = scheme_scopes(self._compiled("web.assets_web"))
        failures = []
        for scheme, scope in (("light", light), ("dark", dark)):
            is_dark = scope is dark
            page = token_colour("--body-bg", scope, dark=is_dark)
            for surface_name in SURFACE_TOKENS:
                surface = composite(
                    token_colour(surface_name, scope, dark=is_dark), page
                )
                for app in apps:
                    accent = hex_to_rgb(app[f"web_accent_{scheme}"])
                    ratio = contrast_ratio(accent, surface)
                    if ratio < WCAG_AA_TEXT:
                        failures.append(
                            f"{scheme}: {app.name} {app.web_accent} on "
                            f"{surface_name} {ratio:.2f}:1"
                        )
        self.assertFalse(
            failures,
            f"{len(failures)} app accent/surface pair(s) fall below WCAG AA "
            f"({WCAG_AA_TEXT}:1); ir.ui.menu's ACCENT_SURFACES no longer bound "
            "the surfaces:\n  " + "\n  ".join(failures),
        )

    def test_text_meets_wcag_aa_on_every_app_accented_active_background(self):
        apps = self.env["ir.ui.menu"].search(
            [("parent_id", "=", False), ("web_accent", "!=", False)]
        )
        self.assertTrue(apps, "no installed app has an accent to check")
        css = self._compiled("web.assets_web")
        active_by_scheme = {}
        for selectors, body in self._matches(".o_web_client.o_app_accented", css=css):
            active = _declaration(body, "--o-bg-active")
            if active is not None:
                dark_rule = re.search(r"data-color-scheme=[\"']?dark", selectors)
                active_by_scheme["dark" if dark_rule else "light"] = active
        self.assertEqual(set(active_by_scheme), {"light", "dark"})
        light, dark = scheme_scopes(css)
        failures = []
        for scheme, scope, extreme in (
            ("light", light, "#000000"),
            ("dark", dark, "#ffffff"),
        ):
            is_dark = scope is dark
            page = token_colour("--body-bg", scope, dark=is_dark)
            accents = [(f"any accent ({extreme})", extreme)] + [
                (app.name, app[f"web_accent_{scheme}"]) for app in apps
            ]
            for name, accent in accents:
                accented = {
                    **scope,
                    "--o-app-accent": accent,
                    "--o-bg-active": active_by_scheme[scheme],
                }
                surface = composite(
                    token_colour("--o-bg-active", accented, dark=is_dark), page
                )
                for text_name in TEXT_TOKENS:
                    text = composite(
                        token_colour(text_name, accented, dark=is_dark), surface
                    )
                    ratio = contrast_ratio(text, surface)
                    if ratio < WCAG_AA_TEXT:
                        failures.append(
                            f"{scheme}: {text_name} on {name}'s active "
                            f"background {ratio:.2f}:1"
                        )
        self.assertFalse(
            failures,
            f"{len(failures)} text token(s) fall below WCAG AA "
            f"({WCAG_AA_TEXT}:1) on an app-accented active background:\n  "
            + "\n  ".join(failures),
        )

    def test_subdued_text_meets_wcag_aa_in_both_schemes(self):
        failures = []
        for scheme, css in (("light", self.css), ("dark", self._compiled(DARK_BUNDLE))):
            page = _declaration(css, "--body-bg")
            self.assertTrue(page, f"{scheme}: --body-bg is not defined")
            background = _parse_color(page)[0]

            body = self._rule(LIST_HEADER, declaring="color", css=css)
            colour = _declaration(body, "color")
            rgb, alpha = _parse_color(colour)

            ratio = contrast_ratio(_composite(rgb, alpha, background), background)
            if ratio < WCAG_AA_TEXT:
                failures.append(f"{scheme}: {colour} on {page} = {ratio:.2f}:1")
        self.assertFalse(
            failures, f"below WCAG AA ({WCAG_AA_TEXT}:1): {', '.join(failures)}"
        )

    def test_check_input_boundary_is_perceivable_in_both_schemes(self):
        failures = []
        for scheme, css in (("light", self.css), ("dark", self._compiled(DARK_BUNDLE))):
            body = self._rule(".form-check-input", declaring="border", css=css)
            border = re.search(
                r"\bsolid\s+(#[0-9a-fA-F]{3,6}|rgba?\([^)]*\))",
                _declaration(body, "border"),
                re.IGNORECASE,
            )
            self.assertTrue(
                border, f"{scheme}: .form-check-input declares no border colour"
            )
            rgb, alpha = _parse_color(border.group(1))

            for surface in ("--body-bg", "--card-bg"):
                value = _declaration(css, surface)
                self.assertTrue(value, f"{scheme}: {surface} is not defined")
                background = (
                    [255, 255, 255] if value == "white" else _parse_color(value)[0]
                )
                ratio = contrast_ratio(_composite(rgb, alpha, background), background)
                if ratio < WCAG_AA_NON_TEXT:
                    failures.append(
                        f"{scheme}: {border.group(1)} on {surface} "
                        f"({value}) = {ratio:.2f}:1"
                    )
        self.assertFalse(
            failures, f"below SC 1.4.11 ({WCAG_AA_NON_TEXT}:1): {', '.join(failures)}"
        )

    def _heading_size_px(self, level):
        match = re.search(
            rf"(?:^|[;}}])h{level},\.h{level}\{{([^}}]*)\}}", self.css, re.MULTILINE
        )
        self.assertTrue(match, f"h{level} declares no rule")
        size = re.search(r"(?:^|;)font-size:\s*([^;}]+)", match.group(1))
        self.assertTrue(size, f"h{level} declares no font-size")
        return _font_size_px(size.group(1))

    def test_heading_scale_is_a_single_ratio(self):
        sizes = [self._heading_size_px(level) for level in range(1, 7)]
        ratios = [big / small for big, small in pairwise(sizes)]

        self.assertAlmostEqual(
            min(ratios),
            max(ratios),
            delta=0.02,
            msg=f"heading ratios drift: {[round(r, 3) for r in ratios]}",
        )

    def test_headings_are_optically_tracked(self):
        tracking = []
        for level in range(1, 7):
            body = self._rule(f"h{level}", declaring="letter-spacing")
            declared = re.search(r"(?:^|;)letter-spacing:\s*(-?[\d.]+)em", body)
            self.assertTrue(declared, f"h{level} declares no em letter-spacing")
            tracking.append(float(declared.group(1)))

        self.assertLess(max(tracking), 0, f"headings are not tracked in: {tracking}")
        self.assertEqual(
            tracking,
            sorted(tracking),
            f"tracking must not loosen as headings grow: {tracking}",
        )

    def test_opacity_vars_do_not_inherit(self):
        for name in ("--bg-opacity", "--text-opacity"):
            match = re.search(r"@property\s*" + name + r"\s*\{([^}]*)\}", self.css)
            self.assertTrue(match, f"@property {name} is not declared")
            self.assertIn("inherits:false", match.group(1).replace(" ", ""))

    def test_text_utilities_meet_wcag_aa(self):
        background = self._page_background()
        failures = []
        for name in ("primary", "success", "info", "warning", "danger"):
            colour = _declaration(
                self._rule(f".text-{name}", declaring="--color"), "--color"
            )
            rgb, alpha = _parse_color(colour)
            ratio = contrast_ratio(_composite(rgb, alpha, background), background)
            if ratio < WCAG_AA_TEXT:
                failures.append(f".text-{name}: {ratio:.2f}:1")
        self.assertFalse(
            failures, f"below WCAG AA ({WCAG_AA_TEXT}:1): {', '.join(failures)}"
        )

    def test_action_colour_is_readable_as_text(self):
        backgrounds = {"page": self._page_background()}
        view = _declaration(self.css, "--o-view-background-color")
        backgrounds["view"] = _parse_color(view)[0] if view else [255, 255, 255]

        link = _declaration(self.css, "--link-color")
        self.assertTrue(link, "--link-color is not defined")
        candidates = {"--link-color": _parse_color(link)}

        action = self._rule(".text-action", declaring="--color")
        candidates[".text-action"] = _parse_color(_declaration(action, "--color"))

        failures = []
        for label, (rgb, alpha) in candidates.items():
            for surface, background in backgrounds.items():
                ratio = contrast_ratio(_composite(rgb, alpha, background), background)
                if ratio < WCAG_AA_TEXT:
                    failures.append(f"{label} on {surface}: {ratio:.2f}:1")
        self.assertFalse(
            failures, f"below WCAG AA ({WCAG_AA_TEXT}:1): {', '.join(failures)}"
        )

    def _schemes(self):
        light, dark = scheme_scopes(self.css)
        return (("light", light), ("dark", dark))

    def _component(self, selector, scheme):
        dark_selector = f":root[data-color-scheme=dark] {selector}"
        light, dark = {}, {}
        for _, settled, prop, value in settle(parse_per_selector(self.css)):
            if settled == selector:
                light[prop] = value
            elif settled == dark_selector:
                dark[prop] = value
        return {**light, **dark} if scheme == "dark" else light

    @staticmethod
    def _scheme_colour(value, scope, scheme):
        value = resolve(value, scope)
        return parse_colour(pick_dark(value) if scheme == "dark" else value)

    def test_filled_button_labels_meet_wcag_aa(self):
        failures = []
        for scheme, scope in self._schemes():
            is_dark = scheme == "dark"
            page = token_colour("--body-bg", scope, dark=is_dark)
            for name in ("primary", "secondary"):
                declared = self._component(f".btn-{name}", scheme)
                label, fill = declared.get("--btn-color"), declared.get("--btn-bg")
                self.assertTrue(label, f"{scheme}: .btn-{name} declares no --btn-color")
                self.assertTrue(fill, f"{scheme}: .btn-{name} declares no --btn-bg")
                for surface_name in SURFACE_TOKENS:
                    surface = composite(
                        token_colour(surface_name, scope, dark=is_dark), page
                    )
                    under = composite(self._scheme_colour(fill, scope, scheme), surface)
                    text = composite(self._scheme_colour(label, scope, scheme), under)
                    ratio = contrast_ratio(text, under)
                    if ratio < WCAG_AA_TEXT:
                        failures.append(
                            f"{scheme}: .btn-{name} {label} on {fill} over "
                            f"{surface_name} = {ratio:.2f}:1"
                        )
        self.assertFalse(
            failures, f"below WCAG AA ({WCAG_AA_TEXT}:1): {', '.join(failures)}"
        )

    def test_text_bg_pairs_meet_wcag_aa(self):
        failures = []
        for name in (
            "primary",
            "secondary",
            "success",
            "info",
            "warning",
            "danger",
            "light",
            "dark",
        ):
            body = self._rule(f".text-bg-{name}", declaring="--color")
            fg = _declaration(body, "--color")
            channels = _declaration(self.css, f"--{name}-rgb")
            self.assertTrue(channels, f"--{name}-rgb is not defined")
            surface = [float(c) for c in channels.split(",")]
            fg_rgb, fg_alpha = _parse_color(fg)
            ratio = contrast_ratio(_composite(fg_rgb, fg_alpha, surface), surface)
            if ratio < WCAG_AA_TEXT:
                failures.append(f".text-bg-{name}: {ratio:.2f}:1")
        self.assertFalse(
            failures, f"below WCAG AA ({WCAG_AA_TEXT}:1): {', '.join(failures)}"
        )

    _RING_COLOUR = (
        r"outline:\s*[\d.]+px\s+solid\s+"
        r"(?:var\(\s*--o-ring-color\s*,\s*)?(rgba?\([^)]*\)|#[0-9a-fA-F]{3,6})"
    )

    def _ring_default(self):
        outline = re.search(
            self._RING_COLOUR, self._rule("a:focus-visible"), re.IGNORECASE
        )
        self.assertTrue(outline, "no focus outline colour found")
        return _parse_color(outline.group(1))

    def test_focus_ring_is_opaque_and_visible(self):
        background = self._page_background()
        rgb, alpha = self._ring_default()
        self.assertEqual(alpha, 1.0, "focus ring colour must be opaque")
        ratio = contrast_ratio(_composite(rgb, alpha, background), background)
        self.assertGreaterEqual(
            ratio, WCAG_AA_NON_TEXT, f"focus ring contrast {ratio:.2f}:1"
        )

    def test_focus_ring_is_visible_on_the_navbar(self):
        failures = []
        for scheme, scope in self._schemes():
            declared = self._component(".o_main_navbar", scheme)
            ring_value = declared.get("--o-ring-color")
            bar_value = declared.get("background")
            self.assertTrue(ring_value, f"{scheme}: .o_main_navbar has no ring colour")
            self.assertTrue(bar_value, f"{scheme}: .o_main_navbar has no background")
            ring = self._scheme_colour(ring_value, scope, scheme)
            self.assertEqual(ring[3], 1.0, "navbar ring colour must be opaque")
            page = token_colour("--body-bg", scope, dark=scheme == "dark")
            bar = composite(self._scheme_colour(bar_value, scope, scheme), page)
            ratio = contrast_ratio(ring[:3], bar)
            if ratio < WCAG_AA_NON_TEXT:
                failures.append(
                    f"{scheme}: focus ring {ring_value} on {bar_value}: {ratio:.2f}:1"
                )
        self.assertFalse(failures, "; ".join(failures))

    def test_no_cascade_layers(self):
        layers = set(re.findall(r"@layer\s+([\w-]+)", self.css))
        self.assertFalse(layers, f"unexpected cascade layer(s): {sorted(layers)}")

    def test_color_scheme_values_are_recognised(self):
        allowed = {"normal", "light", "dark", "only light", "only dark", "light dark"}
        for bundle in ("web.assets_backend", "web.assets_web_print"):
            css = self.css if bundle == "web.assets_backend" else self._compiled(bundle)
            declared = {
                value.strip()
                for value in re.findall(r"[;{]color-scheme:\s*([^;}]+)", css)
            }
            self.assertTrue(declared, f"{bundle}: no color-scheme declaration")
            self.assertFalse(
                declared - allowed,
                f"{bundle}: unrecognised color-scheme {sorted(declared - allowed)}",
            )

    _FONT_DECLARATION = re.compile(r"[\w-]*font[\w-]*\s*:\s*([^;{}]+)", re.IGNORECASE)
    _GENERICS = frozenset(
        [
            "serif",
            "sans-serif",
            "monospace",
            "cursive",
            "fantasy",
            "system-ui",
            "ui-serif",
            "ui-sans-serif",
            "ui-monospace",
            "ui-rounded",
            "math",
            "emoji",
            "fangsong",
        ]
    )

    def _font_stacks(self, css=None):
        for match in self._FONT_DECLARATION.finditer(
            css if css is not None else self.css
        ):
            families = [f.strip() for f in match.group(1).split(",")]
            if len(families) > 1 and self._GENERICS.intersection(
                f.lower() for f in families
            ):
                yield families

    def test_font_stacks_list_no_family_twice(self):
        for bundle in ("web.assets_backend", "web.report_assets_common"):
            css = self.css if bundle == "web.assets_backend" else self._compiled(bundle)
            stacks = list(self._font_stacks(css))
            self.assertTrue(stacks, f"{bundle}: no font stacks found to check")
            for families in stacks:
                lowered = [f.lower() for f in families]
                repeated = {f for f in lowered if lowered.count(f) > 1}
                self.assertFalse(
                    repeated,
                    f"{bundle}: {sorted(repeated)} listed more than once; every "
                    f"entry between the copies is dead:\n  {', '.join(families)}",
                )

    def test_only_emoji_fonts_follow_the_generic_family(self):
        allowed = re.compile(r"emoji|symbol", re.IGNORECASE)
        for families in self._font_stacks():
            first_generic = next(
                i for i, f in enumerate(families) if f.lower() in self._GENERICS
            )
            for family in families[first_generic + 1 :]:
                self.assertRegex(
                    family,
                    allowed,
                    f"{family!r} sits behind a generic family and is unreachable:"
                    f"\n  {', '.join(families)}",
                )

    def test_monospace_stack_is_the_design_system_one(self):
        declared = _declaration(self.css, "--font-monospace")
        self.assertTrue(declared, "--font-monospace is not defined")
        self.assertIn(
            "Odoo Unicode Support Noto",
            declared,
            "--font-monospace is not the stack built by "
            "o-add-unicode-support-font(); it is Bootstrap's default",
        )

    def _keyframes(self):
        blocks = []
        for match in re.finditer(r"@keyframes\s+([\w-]+)\s*\{", self.css):
            depth, index = 0, match.end() - 1
            while index < len(self.css):
                if self.css[index] == "{":
                    depth += 1
                elif self.css[index] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                index += 1
            blocks.append((match.group(1), self.css[match.end() : index]))
        return blocks

    def test_keyframes_use_animation_timing_function(self):
        keyframes = self._keyframes()
        self.assertTrue(keyframes, "no @keyframes parsed - the matcher is broken")
        offenders = [n for n, body in keyframes if "transition-timing-function" in body]
        self.assertFalse(
            offenders, f"@keyframes using transition-timing-function: {offenders}"
        )

    def test_odoo_keyframes_are_namespaced(self):
        known_foreign = (
            "fa-",
            "bs-",
            "progress-bar-stripes",
            "placeholder-glow",
            "placeholder-wave",
        )
        names = set(re.findall(r"@keyframes\s+([\w-]+)", self.css))
        unprefixed = sorted(
            n
            for n in names
            if not n.startswith(("o-", "o_")) and not n.startswith(known_foreign)
        )
        self.assertNotIn("pulse", unprefixed)
        self.assertNotIn("flash", unprefixed)
        self.assertNotIn("bounceIn", unprefixed)
