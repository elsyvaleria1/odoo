import logging

from markupsafe import Markup

from odoo import _, fields, models, tools
from odoo.exceptions import ValidationError

from odoo.addons.base.models.assetsbundle.assets import PreprocessedCSS
from odoo.addons.base.models.assetsbundle.css_pipeline import CssPipeline
from odoo.addons.website import theme_colors
from odoo.addons.website.tools import (
    RE_MENU_BOX_VALUES,
    RE_THEME_LENGTH,
    RFS_BASE_REM,
    RFS_REM_PX,
    RUNTIME_FONT_SIZE_KEYS,
    RUNTIME_GRADIENT_KEYS,
    RUNTIME_HEADING_KEYS,
    RUNTIME_HEADING_SIZE_KEYS,
    RUNTIME_KEYS,
    RUNTIME_PALETTE_KEYS,
    RUNTIME_SET_ONLY_KEYS,
    RUNTIME_THEME_COLOR_KEYS,
    RUNTIME_THEME_KEYS,
    THEME_CUSTOMIZATION_GROUPS,
    THEME_CUSTOMIZATION_URLS,
    UNSET_OVERRIDE_VALUES,
    UNSET_THEME_VALUES,
    is_theme_gradient,
)

_logger = logging.getLogger(__name__)


class Website(models.Model):
    _inherit = "website"

    theme_values = fields.Json(
        copy=False,
        help="Theme customizations applied at runtime, as CSS custom properties "
        "on :root, instead of being compiled into the website's frontend bundle.",
    )
    theme_scss_values = fields.Json(
        copy=False,
        help="Theme customizations compiled into the website's frontend bundle, by "
        "customization group. The website's customized SCSS maps are generated "
        "from it.",
    )

    def write(self, vals):
        result = super().write(vals)
        if "theme_scss_values" in vals:
            self.env.registry.clear_cache("assets")
        return result

    def customize_theme(
        self, values=None, palette=None, theme_palette=None, gray_palette=None
    ):
        self.check_access("write")
        return self._customize_theme(
            values=values,
            palette=palette,
            theme_palette=theme_palette,
            gray_palette=gray_palette,
        )

    def _customize_theme(
        self, values=None, palette=None, theme_palette=None, gray_palette=None
    ) -> dict:
        self.check_singleton()
        assets = self.env["website.assets"].with_context(website_id=self.id)
        reload_bundles = False
        for group, group_values in (
            ("values", values),
            ("palette", palette),
            ("theme_palette", theme_palette),
            ("gray_palette", gray_palette),
        ):
            if group_values:
                result = assets.update_scss_customization(
                    THEME_CUSTOMIZATION_URLS[group], dict(group_values)
                )
                reload_bundles |= result["reload_bundles"]
        return {
            "reload_bundles": reload_bundles,
            "theme_values_css": str(self._get_theme_values_css()),
        }

    @staticmethod
    def _theme_value_is_unset(key, value) -> bool:
        if (
            key
            in RUNTIME_PALETTE_KEYS | RUNTIME_GRADIENT_KEYS | RUNTIME_THEME_COLOR_KEYS
        ):
            return value in UNSET_OVERRIDE_VALUES
        return value in UNSET_THEME_VALUES

    @staticmethod
    def _theme_value_is_valid(key, value):
        if key in RUNTIME_PALETTE_KEYS:
            try:
                theme_colors.parse_user_color(value)
            except ValueError:
                return False
            return True
        if key in RUNTIME_GRADIENT_KEYS:
            return is_theme_gradient(value)
        if key in RUNTIME_THEME_COLOR_KEYS:
            try:
                return theme_colors.parse_user_color(value) is not None
            except ValueError:
                return False
        if key in RE_MENU_BOX_VALUES:
            return RE_MENU_BOX_VALUES[key].fullmatch(value) is not None
        return RE_THEME_LENGTH.fullmatch(value) is not None

    @staticmethod
    def _theme_font_size_rem(value):
        match = RE_THEME_LENGTH.fullmatch(value)
        if not match or not value.endswith(("px", "rem")):
            return None
        number = float(value.removesuffix("px").removesuffix("rem"))
        return number / RFS_REM_PX if value.endswith("px") else number

    def _is_theme_value_compile_needed(self, key, value) -> bool:
        if key in RUNTIME_GRADIENT_KEYS:
            return not is_theme_gradient(value)
        if key in RUNTIME_FONT_SIZE_KEYS:
            rem = self._theme_font_size_rem(value)
            if rem is not None and rem > RFS_BASE_REM:
                return True
            context = self._get_theme_color_context()
            return context is None or key not in context.captured
        if key in RUNTIME_HEADING_KEYS:
            context = self._get_theme_color_context()
            return context is None or key not in context.heading_rules
        if key in RUNTIME_HEADING_SIZE_KEYS:
            context = self._get_theme_color_context()
            return context is None or key not in context.heading_sizes
        if key == "fixed-logo-height" and self._theme_font_size_rem(value) is None:
            return True
        if key in RUNTIME_SET_ONLY_KEYS:
            if key in RE_MENU_BOX_VALUES and not self._theme_value_is_valid(key, value):
                return False
            if key in RUNTIME_THEME_COLOR_KEYS and not self._theme_value_is_valid(
                key, value
            ):
                return True
            context = self._get_theme_color_context()
            return context is None or key not in context.set_values
        return False

    def _set_theme_values(self, values) -> None:
        self.check_singleton()
        stored = dict(self.theme_values or {})
        for key, raw in values.items():
            if key not in RUNTIME_KEYS:
                raise ValidationError(_("%s is not a runtime theme value.", key))
            value = str(raw or "").strip()
            if self._theme_value_is_unset(key, value):
                stored.pop(key, None)
            elif self._theme_value_is_valid(key, value):
                stored[key] = value
            else:
                raise ValidationError(
                    _(
                        "“%(value)s” is not a valid value for %(key)s.",
                        value=value,
                        key=key,
                    )
                )
        self._write_theme_values(stored)

    def _write_theme_values(self, stored) -> None:
        if stored != (self.theme_values or {}):
            self.theme_values = stored

    def _theme_palette_fits_runtime(self, values):
        self.check_singleton()
        try:
            palette = {
                key: theme_colors.parse_user_color(value)
                for key, value in {**(self.theme_values or {}), **values}.items()
                if key in RUNTIME_PALETTE_KEYS
                and str(value or "").strip() not in UNSET_OVERRIDE_VALUES
            }
        except ValueError:
            return False
        context = self._get_theme_color_context()
        return context is not None and theme_colors.fits_runtime(
            context, palette, self._get_runtime_gradients()
        )

    def _get_runtime_gradients(self) -> dict:
        return {
            key: value
            for key, value in (self.theme_values or {}).items()
            if key in RUNTIME_GRADIENT_KEYS and is_theme_gradient(value)
        }

    def _get_theme_values_css(self):
        self.check_singleton()
        values = self.theme_values or {}
        declarations = tuple(
            f"--{key}:{self._theme_length_css(key, value)}"
            for key, value in sorted(values.items())
            if key in RUNTIME_THEME_KEYS
            and key not in RE_MENU_BOX_VALUES
            and RE_THEME_LENGTH.fullmatch(value)
        )
        declarations += tuple(
            f"--o-website-{key}:{value}"
            for key, value in sorted(values.items())
            if key in RE_MENU_BOX_VALUES and RE_MENU_BOX_VALUES[key].fullmatch(value)
        )
        fixed = values.get("fixed-logo-height")
        if fixed and (rem := self._theme_font_size_rem(fixed)) is not None:
            context = self._get_theme_color_context()
            if context:
                font = f"{theme_colors.sass_number(rem / context.line_height_base)}rem"
                declarations += (
                    f"--fixed-logo-font-size:{font}",
                    f"--fixed-logo-font-size-fluid:{theme_colors.rfs_fluid_value(context, font)}",
                )
        small = values.get("small-font-size")
        if small and (rem := self._theme_font_size_rem(small)) is not None:
            context = self._get_theme_color_context()
            if context and (em := theme_colors.small_font_size_em(context, rem)):
                declarations += (f"--small-font-size-em:{em}",)
        if colors := sorted(
            (key, value)
            for key, value in values.items()
            if key in RUNTIME_THEME_COLOR_KEYS
        ):
            context = self._get_theme_color_context()
            for key, value in colors:
                if context and (css := theme_colors.named_color_css(context, value)):
                    declarations += (f"--{key}:{value}", f"--o-website-{key}:{css}")
        if sizes := sorted(
            (key, value)
            for key, value in values.items()
            if key in RUNTIME_HEADING_SIZE_KEYS and RE_THEME_LENGTH.fullmatch(value)
        ):
            context = self._get_theme_color_context()
            declarations += tuple(
                f"--{key}-fluid:{theme_colors.rfs_fluid_value(context, value)}"
                for key, value in sizes
                if context is not None
            )
        rules = ()
        palette = tuple(
            sorted(item for item in values.items() if item[0] in RUNTIME_PALETTE_KEYS)
        )
        gradients = tuple(
            sorted(
                (key, value)
                for key, value in values.items()
                if key in RUNTIME_GRADIENT_KEYS and is_theme_gradient(value)
            )
        )
        if palette or gradients:
            color_declarations, rules = self._get_color_css(
                self._get_frontend_css_links(), palette, gradients
            )
            declarations += color_declarations
        return self._theme_css_markup(declarations, rules)

    def _theme_css_markup(self, declarations, rules):
        safe_declarations = [item for item in declarations if "<" not in item]
        safe_rules = [item for item in rules if "<" not in item]
        if len(safe_declarations) != len(declarations) or len(safe_rules) != len(rules):
            _logger.warning(
                "Website %s: dropped runtime theme CSS that contains '<'.", self.id
            )
        if not safe_declarations:
            return Markup()
        css = ":root{" + ";".join(safe_declarations) + "}" + "".join(safe_rules)
        return Markup(css)

    def _theme_length_css(self, key, value):
        if key in RUNTIME_FONT_SIZE_KEYS | RUNTIME_HEADING_SIZE_KEYS and value.endswith(
            "px"
        ):
            return f"{self._theme_font_size_rem(value):.10g}rem"
        return value

    @tools.ormcache("self.id", "links", "palette", "gradients", cache="assets")
    def _get_color_css(self, links, palette, gradients) -> tuple:
        context = self.with_context(website_id=self.id)._extract_theme_color_context(
            links
        )
        overrides = {
            key: theme_colors.parse_user_color(value) for key, value in palette
        }
        declarations, rules = [], []
        if palette and context is not None:
            palette_declarations, rules = theme_colors.palette_css(context, overrides)
            declarations += [f"{k}:{v}" for k, v in palette_declarations.items()]
            declarations.append("--has-customized-colors:true")
        declarations += [f'--{key}:"{gradient}"' for key, gradient in gradients]
        rules += theme_colors.gradient_css(context, overrides, dict(gradients))
        return tuple(declarations), tuple(rules)

    def _get_frontend_css_links(self):
        website = self.with_context(website_id=self.id)
        return tuple(
            website.env["ir.qweb"]._get_asset_links_cached(
                "web.assets_frontend",
                css=True,
                js=False,
                assets_params=website.env["ir.asset"]._prepare_assets_params(),
            )
        )

    def _get_theme_color_context(self):
        self.check_singleton()
        return self.with_context(website_id=self.id)._extract_theme_color_context(
            self._get_frontend_css_links()
        )

    @tools.ormcache("self.id", "links", cache="assets")
    def _extract_theme_color_context(self, links):
        bundle = self.env["ir.qweb"]._get_asset_bundle(
            "web.assets_frontend", css=True, js=False
        )
        assets = [a for a in bundle.stylesheets if isinstance(a, PreprocessedCSS)]
        source = "\n".join(
            [
                theme_colors.EXTRACTION_USE,
                *(asset.get_source() for asset in assets),
                theme_colors.EXTRACTION,
            ]
        )
        try:
            return theme_colors.parse_extraction(
                CssPipeline(bundle).compile_css(assets[0], source)
            )
        except ValueError:
            _logger.warning(
                "Website %s: could not read its palette from web.assets_frontend "
                "(%s); its runtime colours are not applied.",
                self.id,
                ", ".join(links),
            )
            return None

    def _pop_theme_values(self, keys):
        self.check_singleton()
        stored = dict(self.theme_values or {})
        popped = {key: stored.pop(key) for key in list(stored) if key in keys}
        self._write_theme_values(stored)
        return popped

    def _get_scss_customization(self, url):
        self.check_singleton()
        group = THEME_CUSTOMIZATION_GROUPS[url]
        return dict((self.theme_scss_values or {}).get(group, {}))

    def _set_scss_customization(self, url, entries) -> None:
        self.check_singleton()
        stored = dict(self.theme_scss_values or {})
        group = THEME_CUSTOMIZATION_GROUPS[url]
        if entries:
            stored[group] = entries
        else:
            stored.pop(group, None)
        self.theme_scss_values = stored


class IrQweb(models.AbstractModel):
    _inherit = "ir.qweb"

    def _get_asset_content(self, bundle, assets_params=None):
        if assets_params is None:
            assets_params = self.env["ir.asset"]._prepare_assets_params()
        files, external_assets = super()._get_asset_content(bundle, assets_params)
        if website_id := assets_params.get("website_id"):
            website = self.env["website"].browse(website_id)
            assets = self.env["website.assets"]
            for spec in files:
                url = spec["url"]
                if url in THEME_CUSTOMIZATION_GROUPS and (
                    entries := website._get_scss_customization(url)
                ):
                    spec["content"] = assets._get_scss_map_content(url, entries)
        return files, external_assets
