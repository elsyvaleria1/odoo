import colorsys
import re

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.libs.colors import parse_sass_color
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools.sass_embedded import close_sass_compiler

from odoo.addons.website.tools import GRAY_COLOR_PALETTE_URL, THEME_COLOR_PALETTE_URL

USER_VALUES = "/website/static/src/scss/options/user_values.scss"
CUSTOM_USER_VALUES = f"/_custom/web.assets_frontend{USER_VALUES}"
GRADIENT = "linear-gradient(135deg, #010203 0%, #040506 100%)"
PALETTE = "/website/static/src/scss/options/colors/user_color_palette.scss"
PRESETS = {
    "o-cc2-headings": "'o-color-5'",
    "o-cc2-btn-primary": "#ffd000",
    "o-cc2-text": "3",
    "o-cc3-bg": "#1e2a38",
    "o-cc3-h3": "'primary'",
    "o-cc3-btn-secondary-border": "#00b3a4",
    "o-cc4-bg": "'900'",
    "o-cc4-btn-primary-border": "#ffffff",
    "o-cc5-bg": "rgb(120, 200, 80)",
    "o-cc5-link": "'o-color-3'",
}
RE_ROOT = re.compile(r":root(?:,\[data-bs-theme=light\])?\{([^{}]*)\}")
RE_PRESET_DECLARATION = re.compile(r"(--o-cc[2-5]-[\w-]+):\s*([^;]*)")
RE_ELEMENT_DECLARATION = re.compile(
    r"(--(?:o-(?:menu|footer|copyright)-css-[\w-]+|(?:menu|footer|copyright)"
    r"(?:-custom)?|o-menu-color(?:-shade)?|o-footer-scrolltop-[\w-]+))"
    r":\s*([^;]*)"
)
LEGACY_MAP = """$o-user-website-values: map-merge(
    $o-user-website-values,
    o-map-omit(
        (
            'headings-margin-top': 2rem,
            'btn-padding-x': 1.2rem,
            'btn-font-size-lg': 1.5rem,
            'input-font-size': 18px,
            'o-cc4-bg-gradient': linear-gradient(135deg, #010203 0%, #040506 100%),
            'o-cc5-bg-gradient': NULL,
            'link-underline': 'never',
            'paragraph-margin-bottom': 1rem * 2,
            // -- hook --
        )
    )
);
"""


def _compiled_map(env, website, url):
    files, _external = (
        env["ir.qweb"]
        .with_context(website_id=website.id)
        ._get_asset_content("web.assets_frontend")
    )
    return next(spec["content"] for spec in files if spec["url"] == url) or None


@tagged("post_install", "-at_install")
class TestThemeValues(TransactionCase):
    def setUp(self):
        super().setUp()
        self.website = self.env.ref("website.default_website")
        self.assets = self.env["website.assets"].with_context(
            website_id=self.website.id
        )

    def _custom_user_values(self):
        return _compiled_map(self.env, self.website, USER_VALUES)

    def test_a_runtime_value_is_stored_without_touching_the_bundle(self):
        result = self.assets.update_scss_customization(
            USER_VALUES, {"headings-line-height": "1.5"}
        )
        self.assertEqual(
            result,
            {
                "reload_bundles": False,
                "theme_values_css": ":root{--headings-line-height:1.5}",
            },
        )
        self.assertEqual(self.website.theme_values, {"headings-line-height": "1.5"})
        self.assertIsNone(self._custom_user_values())

    def test_other_keys_in_the_same_call_still_compile(self):
        result = self.assets.update_scss_customization(
            USER_VALUES, {"paragraph-margin-top": "8px", "link-underline": "'always'"}
        )
        self.assertTrue(result["reload_bundles"])
        self.assertEqual(self.website.theme_values, {"paragraph-margin-top": "8px"})
        custom = self._custom_user_values()
        self.assertIn("'link-underline': 'always',", custom)
        self.assertNotIn("paragraph-margin-top", custom)

    def test_null_unsets_a_runtime_value(self):
        self.assets.update_scss_customization(
            USER_VALUES, {"headings-margin-top": "1rem"}
        )
        result = self.assets.update_scss_customization(
            USER_VALUES, {"headings-margin-top": "null"}
        )
        self.assertEqual(result["theme_values_css"], "")
        self.assertFalse(self.website.theme_values)

    def test_a_value_that_is_not_a_length_is_refused(self):
        with self.assertRaises(ValidationError):
            self.assets.update_scss_customization(
                USER_VALUES, {"headings-line-height": "1;}body{color:red"}
            )

    def test_resetting_the_user_values_map_clears_runtime_values(self):
        self.assets.update_scss_customization(
            USER_VALUES, {"headings-line-height": "2"}
        )
        self.assets.reset_asset(USER_VALUES, "web.assets_frontend")
        self.assertFalse(self.website.theme_values)

    def test_button_and_input_sizes_apply_at_runtime(self):
        result = self.assets.update_scss_customization(
            USER_VALUES,
            {"btn-padding-x": "1.4rem", "input-font-size": "18px"},
        )
        self.assertFalse(result["reload_bundles"])
        self.assertIsNone(self._custom_user_values())
        # RFS prints a px font size in rem, and so does the runtime value.
        self.assertEqual(
            result["theme_values_css"],
            ":root{--btn-padding-x:1.4rem;--input-font-size:1.125rem}",
        )

    def test_a_font_size_rfs_would_rescale_compiles(self):
        result = self.assets.update_scss_customization(
            USER_VALUES, {"btn-font-size-lg": "1.5rem"}
        )
        self.assertTrue(result["reload_bundles"])
        self.assertFalse(self.website.theme_values)
        self.assertIn("'btn-font-size-lg': 1.5rem,", self._custom_user_values())

    def test_a_heading_level_spacing_applies_at_runtime_once_its_rule_exists(self):
        first = self.assets.update_scss_customization(
            USER_VALUES, {"h3-margin-top": "12px"}
        )
        # The level equals the common heading margin, so no h3 rule is compiled
        # yet: setting it the first time compiles one.
        self.assertTrue(first["reload_bundles"])
        self.assertIn("'h3-margin-top': 12px,", self._custom_user_values())
        second = self.assets.update_scss_customization(
            USER_VALUES, {"h3-margin-top": "20px"}
        )
        self.assertFalse(second["reload_bundles"])
        self.assertEqual(second["theme_values_css"], ":root{--h3-margin-top:20px}")

    def test_a_heading_size_applies_at_runtime_with_its_fluid_value(self):
        result = self.assets.update_scss_customization(
            USER_VALUES, {"h1-font-size": "3.5rem", "h5-font-size": "18px"}
        )
        self.assertFalse(result["reload_bundles"])
        # Bootstrap's RFS: 3.5rem is past its 1.25rem base, so below 1200px it
        # shrinks fluidly; 18px (1.125rem) is not, and stays as it is.
        self.assertEqual(
            result["theme_values_css"],
            ":root{--h1-font-size:3.5rem;--h5-font-size:1.125rem;"
            "--h1-font-size-fluid:calc(1.475rem + 2.7vw);"
            "--h5-font-size-fluid:1.125rem}",
        )

    def test_sidebar_and_outline_widths_apply_at_runtime(self):
        result = self.assets.update_scss_customization(
            USER_VALUES,
            {"sidebar-width": "16rem", "btn-primary-outline-border-width": "3px"},
        )
        self.assertFalse(result["reload_bundles"])
        self.assertEqual(
            result["theme_values_css"],
            ":root{--btn-primary-outline-border-width:3px;--sidebar-width:16rem}",
        )

    def test_a_header_value_applies_at_runtime_once_the_compile_has_one(self):
        first = self.assets.update_scss_customization(
            USER_VALUES,
            {"header-font-size": "1.125rem", "header-text-color": "'o-color-2'"},
        )
        # Neither is set on the default website, so no rule reads them yet.
        self.assertTrue(first["reload_bundles"])
        second = self.assets.update_scss_customization(
            USER_VALUES,
            {"header-font-size": "1.25rem", "header-text-color": "#aa3300"},
        )
        self.assertFalse(second["reload_bundles"])
        self.assertEqual(
            second["theme_values_css"],
            ":root{--header-font-size:1.25rem;--header-text-color:#aa3300;"
            "--o-website-header-text-color:#aa3300}",
        )

    def test_body_line_height_and_small_size_apply_at_runtime(self):
        result = self.assets.update_scss_customization(
            USER_VALUES, {"body-line-height": "1.7", "small-font-size": "13px"}
        )
        self.assertFalse(result["reload_bundles"])
        # Bootstrap's `small` is the ratio to the base size, in em.
        self.assertEqual(
            result["theme_values_css"],
            ":root{--body-line-height:1.7;--small-font-size:0.8125rem;"
            "--small-font-size-em:0.8125em}",
        )

    def test_the_menu_box_applies_at_runtime_once_the_compile_has_it(self):
        box = {"menu-border-width": "2px", "menu-border-radius": "8px"}
        first = self.assets.update_scss_customization(USER_VALUES, dict(box))
        self.assertTrue(first["reload_bundles"])
        second = self.assets.update_scss_customization(
            USER_VALUES,
            {
                "menu-border-width": "4px",
                "menu-border-radius": "16px",
                "menu-border-style": "dotted",
            },
        )
        self.assertFalse(second["reload_bundles"])
        self.assertEqual(
            second["theme_values_css"],
            ":root{--o-website-menu-border-radius:16px;"
            "--o-website-menu-border-style:dotted;--o-website-menu-border-width:4px}",
        )
        color = self.assets.update_scss_customization(
            PALETTE, {"menu-border-color": "#aa3300"}
        )
        self.assertFalse(color["reload_bundles"])
        self.assertIn(
            "--o-website-menu-border-color:#aa3300", color["theme_values_css"]
        )

    def test_a_menu_box_value_that_is_not_one_is_refused(self):
        with self.assertRaises(ValidationError):
            self.assets.update_scss_customization(
                USER_VALUES, {"menu-border-style": "solid;color:red"}
            )
        with self.assertRaises(ValidationError):
            self.assets.update_scss_customization(
                USER_VALUES, {"menu-box-shadow": "0 0 1px red;}body{x:y"}
            )

    def test_the_fixed_logo_height_applies_at_runtime_with_its_fluid_size(self):
        result = self.assets.update_scss_customization(
            USER_VALUES, {"fixed-logo-height": "2rem"}
        )
        self.assertFalse(result["reload_bundles"])
        # The scrolled logo's font size is the height over the base line height,
        # which RFS makes fluid past 1.25rem.
        self.assertEqual(
            result["theme_values_css"],
            ":root{--fixed-logo-height:2rem;"
            "--fixed-logo-font-size:1.3333333333rem;"
            "--fixed-logo-font-size-fluid:calc(1.2583333333rem + 0.1vw)}",
        )

    def test_nothing_that_could_close_the_style_element_is_emitted(self):
        with self.assertLogs(
            "odoo.addons.website.models.website_theme_values", "WARNING"
        ):
            css = self.website._theme_css_markup(
                ("--btn-padding-y:4px", "--x:1px</style><script>alert(1)</script>"),
                (".o_cc2{background-image:none}", "</style><script>alert(2)</script>"),
            )
        self.assertEqual(
            str(css), ":root{--btn-padding-y:4px}.o_cc2{background-image:none}"
        )

    def test_the_input_radius_applies_at_runtime_once_the_compile_has_one(self):
        # Unset, the check boxes keep Bootstrap's .25em; set, they take
        # min(radius, .25rem): the first value compiles that rule.
        first = self.assets.update_scss_customization(
            USER_VALUES, {"input-border-radius": "8px"}
        )
        self.assertTrue(first["reload_bundles"])
        second = self.assets.update_scss_customization(
            USER_VALUES, {"input-border-radius": "2px"}
        )
        self.assertFalse(second["reload_bundles"])
        self.assertEqual(second["theme_values_css"], ":root{--input-border-radius:2px}")

    def test_the_theme_api_routes_each_group_to_its_storage(self):
        result = self.website._customize_theme(
            values={"headings-line-height": "1.5", "link-underline": "'always'"},
            theme_palette={"success": "#00aa00"},
            gray_palette={"100": "#f0f0f0"},
        )
        self.assertTrue(result["reload_bundles"])
        self.assertEqual(self.website.theme_values, {"headings-line-height": "1.5"})
        self.assertIn("--headings-line-height:1.5", result["theme_values_css"])
        self.assertIn("'link-underline': 'always',", self._custom_user_values())

        self.assertIn(
            "'success': #00aa00,",
            _compiled_map(self.env, self.website, THEME_COLOR_PALETTE_URL),
        )
        self.assertIn(
            "'100': #f0f0f0,",
            _compiled_map(self.env, self.website, GRAY_COLOR_PALETTE_URL),
        )

    def test_the_theme_api_leaves_the_bundle_alone_for_runtime_values(self):
        result = self.website._customize_theme(values={"btn-padding-y": "6px"})
        self.assertFalse(result["reload_bundles"])
        self.assertIsNone(self._custom_user_values())

    def test_the_rpc_entry_customizes_for_a_designer_only(self):
        employee = new_test_user(self.env, "theme_employee")
        designer = new_test_user(
            self.env, "theme_designer", groups="website.group_website_designer"
        )
        with self.assertRaises(AccessError):
            self.website.with_user(employee).customize_theme(
                values={"btn-padding-y": "6px"}
            )
        result = self.website.with_user(designer).customize_theme(
            values={"btn-padding-y": "6px"}
        )
        self.assertFalse(result["reload_bundles"])
        self.assertEqual(self.website.theme_values, {"btn-padding-y": "6px"})

    def test_a_null_for_an_absent_key_writes_nothing(self):
        result = self.assets.update_scss_customization(
            USER_VALUES, {"o-cc3-bg-gradient": "null"}
        )
        self.assertFalse(result["reload_bundles"])
        self.assertIsNone(self._custom_user_values())

    def test_a_preset_gradient_is_applied_without_touching_the_bundle(self):
        result = self.assets.update_scss_customization(
            USER_VALUES, {"o-cc3-bg-gradient": GRADIENT}
        )
        self.assertFalse(result["reload_bundles"])
        self.assertEqual(self.website.theme_values, {"o-cc3-bg-gradient": GRADIENT})
        self.assertIsNone(self._custom_user_values())
        css = result["theme_values_css"]
        self.assertIn(f'--o-cc3-bg-gradient:"{GRADIENT}"', css)
        self.assertIn(
            f".o_cc3{{background-color:rgba(0, 0, 0, 0);background-image:{GRADIENT}}}",
            css,
        )

    def test_the_runtime_gradient_rules_are_the_compiled_ones(self):
        self.addCleanup(close_sass_compiler)
        # The default footer is combination 2, so it takes that combination's
        # gradient too, through a rule of its own.
        css = self.assets.update_scss_customization(
            USER_VALUES, {"o-cc2-bg-gradient": GRADIENT}
        )["theme_values_css"]
        rules = re.findall(r"[^}]*\{[^}]*\}", css.split("}", 1)[1])
        self.assertEqual(
            [rule.split("{")[0] for rule in rules], [".o_cc2", ".o_footer"]
        )
        self.website.theme_values = {}
        self.assets._write_scss_customization(
            USER_VALUES, {"o-cc2-bg-gradient": GRADIENT}
        )
        bundle = (
            self.env["ir.qweb"]
            .with_context(website_id=self.website.id)
            ._get_asset_bundle("web.assets_frontend", css=True, js=False)
        )
        compiled = re.sub(r"\s+", "", bundle.preprocess_css())
        self.assertEqual(bundle.css_errors, [])
        for rule in rules:
            self.assertIn(re.sub(r"\s+", "", rule), compiled)

    def test_a_gradient_the_runtime_cannot_read_compiles(self):
        value = "linear-gradient(red, blue), url(x)"
        result = self.assets.update_scss_customization(
            USER_VALUES, {"o-cc2-bg-gradient": value}
        )
        self.assertTrue(result["reload_bundles"])
        self.assertFalse(self.website.theme_values)
        self.assertIn(f"'o-cc2-bg-gradient': {value},", self._custom_user_values())

    def test_unsetting_a_compiled_gradient_recompiles(self):
        self.assets._write_scss_customization(
            USER_VALUES, {"o-cc2-bg-gradient": GRADIENT}
        )
        result = self.assets.update_scss_customization(
            USER_VALUES, {"o-cc2-bg-gradient": "null"}
        )
        self.assertTrue(result["reload_bundles"])
        self.assertIsNone(self._custom_user_values())

    def test_a_compiled_customization_is_data_the_bundle_compiles(self):
        self.assets.update_scss_customization(
            USER_VALUES, {"link-underline": "'always'", "header-template": "'boxed'"}
        )
        self.assertEqual(
            self.website.theme_scss_values,
            {"values": {"header-template": "'boxed'", "link-underline": "'always'"}},
        )
        self.assertEqual(
            self._custom_user_values(),
            self.assets._get_scss_map_content(
                USER_VALUES,
                {"header-template": "'boxed'", "link-underline": "'always'"},
            ),
        )
        self.assertFalse(
            self.env["ir.attachment"].search([("url", "=", CUSTOM_USER_VALUES)])
        )

    def test_each_website_compiles_its_own_entries(self):
        other = self.env["website"].create({"name": "Theme W2"})
        self.assets.update_scss_customization(
            USER_VALUES, {"link-underline": "'always'"}
        )
        self.assertIn("'link-underline': 'always',", self._custom_user_values())
        self.assertIsNone(_compiled_map(self.env, other, USER_VALUES))

    def test_a_public_visitor_builds_the_bundle_with_the_entries(self):
        self.assets.update_scss_customization(
            USER_VALUES, {"link-underline": "'always'"}
        )
        public = self.env(user=self.env.ref("base.public_user"))
        self.assertIn(
            "'link-underline': 'always',",
            _compiled_map(public, self.website, USER_VALUES),
        )

    def test_the_bundle_version_follows_the_compiled_entries(self):
        def version():
            return (
                self.env["ir.qweb"]
                .with_context(website_id=self.website.id)
                ._get_asset_bundle("web.assets_frontend", js=False)
                .get_version("css")
            )

        before = version()
        self.assets.update_scss_customization(
            USER_VALUES, {"link-underline": "'always'"}
        )
        customized = version()
        self.assets.update_scss_customization(USER_VALUES, {"link-underline": "null"})
        self.assertNotEqual(customized, before)
        self.assertEqual(version(), before)

    def test_removing_the_last_compiled_entry_drops_the_custom_map(self):
        self.assets.update_scss_customization(
            USER_VALUES, {"link-underline": "'always'"}
        )
        self.assets.update_scss_customization(USER_VALUES, {"link-underline": "null"})
        self.assertFalse(self.website.theme_scss_values)
        self.assertIsNone(self._custom_user_values())
        self.assertFalse(
            self.env["ir.asset"].search([("path", "=", CUSTOM_USER_VALUES)])
        )

    def test_the_code_editor_saves_a_map_as_its_entries(self):
        self.assets.save_asset(USER_VALUES, "web.assets_frontend", LEGACY_MAP, "scss")
        self.assertEqual(
            self.website.theme_scss_values["values"]["link-underline"], "'never'"
        )
        self.assertIn("'link-underline': 'never',", self._custom_user_values())
        self.assertEqual(
            self.assets._get_content_from_url(USER_VALUES).decode(),
            self._custom_user_values(),
        )
        with self.assertRaises(UserError):
            self.assets.save_asset(
                USER_VALUES,
                "web.assets_frontend",
                LEGACY_MAP + "$o-extra: 1px;\n",
                "scss",
            )
        self.assertEqual(len(self.website.theme_scss_values["values"]), 8)

    def test_resetting_a_map_clears_its_compiled_entries(self):
        self.assets.update_scss_customization(
            USER_VALUES, {"link-underline": "'always'"}
        )
        self.assets.reset_asset(USER_VALUES, "web.assets_frontend")
        self.assertFalse(self.website.theme_scss_values)
        self.assertIsNone(self._custom_user_values())

    def test_the_frontend_bundle_reads_the_runtime_values(self):
        self.addCleanup(close_sass_compiler)
        bundle = (
            self.env["ir.qweb"]
            .with_context(website_id=self.website.id)
            ._get_asset_bundle("web.assets_frontend", css=True, js=False)
        )
        css = re.sub(r"\s+", "", bundle.preprocess_css())
        self.assertEqual(bundle.css_errors, [])
        for declaration in (
            (
                "h6{line-height:var(--headings-line-height);"
                "margin-top:var(--headings-margin-top);"
                "margin-bottom:var(--headings-margin-bottom)}"
            ),
            "margin-top:var(--paragraph-margin-top,",
            "margin-bottom:var(--paragraph-margin-bottom)",
            "--h2-line-height:var(--headings-line-height)",
            "--btn-border-radius:var(--o-website-btn-border-radius)",
            "--o-website-btn-padding-y:var(--btn-padding-y,",
            "--o-website-input-border-width:var(--input-border-width,",
            "--o-website-btn-padding-x:var(--btn-padding-x,",
            "--o-website-input-padding-y:var(--input-padding-y,",
            "--o-website-btn-font-size:var(--btn-font-size,",
            "margin:calc(-1*var(--o-website-input-padding-y))",
            "font-size:min(var(--o-website-h1-font-size),var(--o-website-h1-font-size-fluid))",
        ):
            self.assertIn(declaration, css)


@tagged("post_install", "-at_install")
class TestThemeValuesRendering(HttpCase):
    def test_the_layout_emits_runtime_presets(self):
        self.addCleanup(close_sass_compiler)
        self.env.ref("website.default_website")._set_theme_values(
            {"o-cc3-bg": "#1e2a38"}
        )
        html = self.url_open("/").text
        self.assertRegex(
            html, r'<style id="o_website_theme_values">:root\{[^<]*--o-cc3-bg:#1e2a38'
        )

    def test_a_cached_public_page_follows_a_runtime_change(self):
        website = self.env.ref("website.default_website")
        website._set_theme_values({"paragraph-margin-top": "12px"})
        self.assertIn("--paragraph-margin-top:12px", self.url_open("/").text)
        website._set_theme_values({"paragraph-margin-top": "20px"})
        html = self.url_open("/").text
        self.assertIn("--paragraph-margin-top:20px", html)
        self.assertNotIn("--paragraph-margin-top:12px", html)

    def test_the_layout_emits_runtime_values_after_the_frontend_bundle(self):
        self.env.ref("website.default_website")._set_theme_values(
            {"paragraph-margin-top": "12px"}
        )
        html = self.url_open("/").text
        style = '<style id="o_website_theme_values">:root{--paragraph-margin-top:12px}</style>'
        self.assertIn(style, html)
        bundle_link = re.search(r'<link[^>]*web\.assets_frontend[^>]*\.css"', html)
        self.assertTrue(bundle_link)
        self.assertLess(bundle_link.start(), html.index(style))


class ThemeColorsCase(TransactionCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(close_sass_compiler)
        self.website = self.env.ref("website.default_website")
        self.assets = self.env["website.assets"].with_context(
            website_id=self.website.id
        )

    def _custom_palette(self):
        return _compiled_map(self.env, self.website, PALETTE)

    def _compiled(self, declaration=RE_PRESET_DECLARATION):
        bundle = (
            self.env["ir.qweb"]
            .with_context(website_id=self.website.id)
            ._get_asset_bundle("web.assets_frontend", css=True, js=False)
        )
        css = bundle.preprocess_css()
        self.assertEqual(bundle.css_errors, [])
        declarations = {
            key: value.strip()
            for root in RE_ROOT.findall(css)
            for key, value in declaration.findall(root)
        }
        return declarations, css

    @staticmethod
    def _rendered(value):
        # Dart Sass prints a colour pushed past the gamut by an HSL adjustment as
        # hsl() with a lightness beyond 0-100%; ours prints the same colour as
        # rgb(). A browser clamps both to one colour, which is what is compared.
        if hsl := re.fullmatch(r"hsl\(([-\d.]+),\s*([-\d.]+)%,\s*([-\d.]+)%\)", value):
            hue, saturation, lightness = (float(x) for x in hsl.groups())
            clamp = min(max(lightness, 0), 100) / 100
            red, green, blue = colorsys.hls_to_rgb(hue / 360, clamp, saturation / 100)
            return (red * 255, green * 255, blue * 255, 1.0)
        color = parse_sass_color(value)
        return (*(min(max(channel, 0), 255) for channel in color[:3]), color[3])

    def assertSameValue(self, key, runtime, compiled):
        try:
            ours, theirs = self._rendered(runtime), self._rendered(compiled)
        except ValueError:
            self.assertEqual(
                re.sub(r"\s+", "", runtime), re.sub(r"\s+", "", compiled), key
            )
        else:
            for a, b in zip(ours, theirs, strict=True):
                self.assertAlmostEqual(a, b, delta=1e-6, msg=key)

    def _runtime(self, compiled, css, declaration=RE_ELEMENT_DECLARATION):
        root = re.match(r":root\{([^}]*)\}", css)[1]
        runtime = compiled | {
            match[1]: match[2] for match in declaration.finditer(root + ";")
        }
        return {key: value for key, value in runtime.items() if value != "initial"}

    def assertSameDeclarations(self, runtime, expected):
        self.assertEqual(runtime.keys(), expected.keys())
        for key, value in expected.items():
            self.assertSameValue(key, runtime[key], value)


@tagged("post_install", "-at_install")
class TestThemeColorPresets(ThemeColorsCase):
    def test_a_preset_colour_is_applied_without_touching_the_bundle(self):
        result = self.assets.update_scss_customization(PALETTE, {"o-cc3-bg": "#1e2a38"})
        self.assertFalse(result["reload_bundles"])
        self.assertEqual(self.website.theme_values, {"o-cc3-bg": "#1e2a38"})
        self.assertIsNone(self._custom_palette())
        css = result["theme_values_css"]
        for declaration in (
            "--o-cc3-bg:#1e2a38",
            "--o-cc3-css-bg:#1e2a38",
            "--has-customized-colors:true",
            ".o_cc3 .btn-close{--btn-close-filter:",
        ):
            self.assertIn(declaration, css)

    def test_runtime_presets_match_what_the_bundle_compiles(self):
        compiled, _css = self._compiled()
        result = self.assets.update_scss_customization(PALETTE, dict(PRESETS))
        self.assertFalse(result["reload_bundles"])
        root = re.match(r":root\{([^}]*)\}", result["theme_values_css"])[1]
        runtime = compiled | dict(
            declaration.split(":", 1)
            for declaration in root.split(";")
            if declaration.startswith("--o-cc")
        )
        runtime = {key: value for key, value in runtime.items() if value != "initial"}

        self.website.theme_values = {}
        self.assets._write_scss_customization(PALETTE, dict(PRESETS))
        expected, css = self._compiled()
        self.assertEqual(runtime.keys(), expected.keys())
        for key, value in expected.items():
            self.assertSameValue(key, runtime[key], value)
        compiled_rules = re.sub(r"\s+", "", css)
        runtime_rules = result["theme_values_css"].split("}", 1)[1]
        self.assertIn(".o_cc3 .btn-close,", runtime_rules)
        self.assertIn(".o_cc5 .btn-close:not(.btn-close-white),", runtime_rules)
        for rule in re.findall(r"[^}]*\.o_cc3 \.btn-close[^}]*\}", runtime_rules):
            self.assertIn(re.sub(r"\s+", "", rule), compiled_rules)

    def test_a_change_the_compiled_rules_cannot_follow_compiles_every_preset(self):
        self.assets.update_scss_customization(PALETTE, {"o-cc2-bg": "#223344"})
        result = self.assets.update_scss_customization(
            PALETTE, {"o-cc4-bg": "rgba(0, 0, 0, 0)"}
        )
        self.assertTrue(result["reload_bundles"])
        self.assertFalse(self.website.theme_values)
        custom = self._custom_palette()
        self.assertIn("'o-cc2-bg': #223344,", custom)
        self.assertIn("'o-cc4-bg': rgba(0, 0, 0, 0),", custom)

    def test_combination_1_always_compiles(self):
        result = self.assets.update_scss_customization(PALETTE, {"o-cc1-bg": "#fafafa"})
        self.assertTrue(result["reload_bundles"])
        self.assertFalse(self.website.theme_values)
        self.assertIn("'o-cc1-bg': #fafafa,", self._custom_palette())

    def test_unsetting_a_compiled_preset_recompiles(self):
        self.assets._write_scss_customization(PALETTE, {"o-cc3-bg": "#1e2a38"})
        self.assets.update_scss_customization(PALETTE, {"o-cc2-bg": "#445566"})
        result = self.assets.update_scss_customization(PALETTE, {"o-cc3-bg": "null"})
        self.assertTrue(result["reload_bundles"])
        self.assertFalse(self.website.theme_values)
        custom = self._custom_palette()
        self.assertNotIn("o-cc3-bg", custom)
        self.assertIn("'o-cc2-bg': #445566,", custom)

    def test_a_colour_the_runtime_cannot_read_compiles(self):
        result = self.assets.update_scss_customization(PALETTE, {"o-cc5-text": "red"})
        self.assertTrue(result["reload_bundles"])
        self.assertIn("'o-cc5-text': red,", self._custom_palette())

    def test_changing_the_palette_clears_runtime_presets(self):
        self.website._set_theme_values({"o-cc3-bg": "#1e2a38", "btn-padding-y": "4px"})
        self.assets.update_scss_customization(
            USER_VALUES, {"color-palettes-name": "'base-2'"}
        )
        self.assertEqual(self.website.theme_values, {"btn-padding-y": "4px"})


@tagged("post_install", "-at_install")
class TestThemeElementColors(ThemeColorsCase):
    def test_switching_a_part_to_another_combination_is_applied_at_runtime(self):
        result = self.assets.update_scss_customization(
            PALETTE, {"menu": 3, "footer": "5"}
        )
        self.assertFalse(result["reload_bundles"])
        self.assertEqual(self.website.theme_values, {"menu": "3", "footer": "5"})
        self.assertIsNone(self._custom_palette())
        css = result["theme_values_css"]
        self.assertIn("--o-menu-css-bg:var(--o-cc3-css-bg)", css)
        self.assertIn("--o-footer-css-link:var(--o-cc5-css-link)", css)
        self.assertIn("--menu:3", css)

    def test_runtime_parts_match_what_the_bundle_compiles(self):
        base = {"copyright": "1"}
        runtime = {"menu": "3", "footer": "5", "copyright": "4"}
        self.assets._write_scss_customization(PALETTE, dict(base))
        compiled, _css = self._compiled(RE_ELEMENT_DECLARATION)
        result = self.assets.update_scss_customization(PALETTE, dict(runtime))
        self.assertFalse(result["reload_bundles"])
        applied = self._runtime(compiled, result["theme_values_css"])

        self.website.theme_values = {}
        self.assets._write_scss_customization(PALETTE, dict(runtime))
        expected, css = self._compiled(RE_ELEMENT_DECLARATION)
        self.assertSameDeclarations(applied, expected)
        compiled_rules = re.sub(r"\s+", "", css)
        for rule in re.findall(
            r"[^}]*\.btn-close[^}]*\}", result["theme_values_css"].split("}", 1)[1]
        ):
            self.assertIn(re.sub(r"\s+", "", rule).split("{")[1], compiled_rules)

    def test_a_menu_turning_dark_restates_the_dark_navbar(self):
        base = {"menu-custom": "#fafafa", "footer-custom": "#eeeeee"}
        runtime = {"menu-custom": "#1e2a38", "footer-custom": "'o-color-2'"}
        self.assets._write_scss_customization(PALETTE, dict(base))
        compiled, _css = self._compiled(RE_ELEMENT_DECLARATION)
        result = self.assets.update_scss_customization(PALETTE, dict(runtime))
        self.assertFalse(result["reload_bundles"])
        applied = self._runtime(compiled, result["theme_values_css"])

        self.website.theme_values = {}
        self.assets._write_scss_customization(PALETTE, dict(runtime))
        expected, css = self._compiled(RE_ELEMENT_DECLARATION)
        self.assertSameDeclarations(applied, expected)
        dark = re.search(r"\.navbar-dark,[^{]*\.navbar-light[^{]*\{([^}]*)\}", css)
        self.assertTrue(dark, "the compiled dark menu extends .navbar-dark")
        self.assertIn(
            f".navbar-light{{{dark[1]}}}".replace(" ", ""),
            result["theme_values_css"].replace(" ", ""),
        )

    def test_giving_a_part_its_first_combination_compiles(self):
        result = self.assets.update_scss_customization(PALETTE, {"copyright": "2"})
        self.assertTrue(result["reload_bundles"])
        self.assertFalse(self.website.theme_values)
        self.assertIn("'copyright': 2,", self._custom_palette())

    def test_a_translucent_part_colour_compiles(self):
        result = self.assets.update_scss_customization(
            PALETTE, {"menu-custom": "rgba(0, 0, 0, 0.2)"}
        )
        self.assertTrue(result["reload_bundles"])
        self.assertIn("'menu-custom': rgba(0, 0, 0, 0.2),", self._custom_palette())

    def test_changing_the_header_template_compiles_the_sales_header_colours(self):
        self.website._set_theme_values({"header-sales_one": "4", "footer": "5"})
        self.assets.update_scss_customization(
            USER_VALUES, {"header-template": "'sales_two'"}
        )
        self.assertEqual(self.website.theme_values, {"footer": "5"})
        self.assertIn("'header-sales_one': 4,", self._custom_palette())

    def test_a_part_gradient_is_applied_at_runtime(self):
        result = self.assets.update_scss_customization(
            USER_VALUES, {"menu-gradient": GRADIENT}
        )
        self.assertFalse(result["reload_bundles"])
        self.assertIn(
            ".navbar-light,.navbar-light .o_navbar_mobile{background-color:"
            f"rgba(0, 0, 0, 0);background-image:{GRADIENT}}}",
            result["theme_values_css"],
        )
