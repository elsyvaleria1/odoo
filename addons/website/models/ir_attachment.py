import copy
import logging

from lxml import etree

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools.misc import file_open

from odoo.addons.html_editor.models.ir_attachment import (
    SAFE_XML_PARSER,
    SVG_NAMESPACE,
    is_json_number,
    parse_css_rgba,
)
from odoo.addons.html_editor.tools import format_js_number

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

HOVER_EFFECTS_PATH = "website/static/src/svg/hover_effects.svg"
HOVER_EFFECT_PARAMS = (
    "hover_effect",
    "hover_effect_color",
    "hover_effect_stroke_width",
    "hover_effect_intensity",
)
ZOOM_HOVER_EFFECTS = ("image_zoom_in", "image_zoom_out", "dolly_zoom")


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    key = fields.Char()
    website_id = fields.Many2one(comodel_name="website")

    @api.model_create_multi
    def create(self, vals_list):
        website = self.env["website"].get_current_website(fallback=False)
        for vals in vals_list:
            if (
                website
                and "website_id" not in vals
                and "not_force_website_id" not in self.env.context
            ):
                vals["website_id"] = website.id
        _debug.lifecycle(
            "attachment_website_defaulted",
            website=website.id if website else None,
            count=len(vals_list),
        )
        return super().create(vals_list)

    @api.model
    def get_groups_allowed_to_serve(self):
        return super().get_groups_allowed_to_serve() + [
            "website.group_website_designer"
        ]

    def _get_serve_attachment(self, url, extra_domain=None, order=None):
        website = self.env["website"].get_current_website()
        extra_domain = Domain(extra_domain or []) & website.website_domain()
        order = ("website_id, %s" % order) if order else "website_id"
        return super()._get_serve_attachment(url, extra_domain, order)

    @api.model
    def _apply_image_shape_effects(self, root, params: dict) -> None:
        params = dict(params)
        hover = {key: params.pop(key) for key in HOVER_EFFECT_PARAMS if key in params}
        super()._apply_image_shape_effects(root, params)
        if hover:
            self._add_image_shape_hover_effect(
                root,
                hover.get("hover_effect"),
                hover.get("hover_effect_color"),
                hover.get("hover_effect_stroke_width"),
                hover.get("hover_effect_intensity"),
            )

    @api.model
    def _add_image_shape_hover_effect(
        self,
        root,
        effect: str | None,
        color: str | None,
        stroke_width: int | None,
        intensity: int | None,
    ) -> None:
        with file_open(HOVER_EFFECTS_PATH, "rb") as file:
            effects = {
                group.get("id"): group
                for group in etree.fromstring(
                    file.read(), SAFE_XML_PARSER
                ).iterchildren(f"{SVG_NAMESPACE}g")
            }
        if not isinstance(effect, str) or effect not in effects:
            raise self._prepare_image_shape_error("hover_effect")
        if any(
            value is not None and not is_json_number(value, int)
            for value in (stroke_width, intensity)
        ):
            raise self._prepare_image_shape_error("hover_effect_number")
        rgb = opacity = None
        if color:
            try:
                red, green, blue, percent = parse_css_rgba(color)
            except TypeError, ValueError:
                raise self._prepare_image_shape_error("hover_effect_color") from None
            rgb, opacity = f"rgb({red},{green},{blue})", format_js_number(percent / 100)

        for element in effects[effect].iterchildren(etree.Element):
            root.append(copy.deepcopy(element))
        animate = next(root.iter(f"{SVG_NAMESPACE}animate"), None)
        animate_transforms = list(root.iter(f"{SVG_NAMESPACE}animateTransform"))

        def replace_values(element, placeholder, value):
            element.set("values", element.get("values").replace(placeholder, value, 1))

        if rgb and effect not in ("outline", "image_mirror_blur"):
            root.find(".//*[@fill='hover_effect_color']").set("fill", rgb)
            replace_values(animate, "hover_effect_opacity", opacity)
        if effect == "outline":
            if rgb:
                root.find(".//*[@stroke='hover_effect_color']").set("stroke", rgb)
                root.find(".//*[@stroke-opacity='hover_effect_opacity']").set(
                    "stroke-opacity", opacity
                )
            if stroke_width is not None:
                replace_values(
                    animate, "hover_effect_stroke_width", str(stroke_width * 2)
                )
        elif effect in ZOOM_HOVER_EFFECTS:
            image = next(root.iter(f"{SVG_NAMESPACE}image"))
            clip_path = root.find(".//*[@id='clip-path']")
            image.set("id", "shapeImage")
            image.set("style", "transform-origin: center; width: 100%; height: 100%")
            image.set("preserveAspectRatio", "none")
            root.set("viewBox", "0 0 1 1")
            root.set("preserveAspectRatio", "none")
            clip_path.set("clipPathUnits", "userSpaceOnUse")
            group = image.makeelement(f"{SVG_NAMESPACE}g")
            if (image_clip_path := image.attrib.pop("clip-path", None)) is not None:
                group.set("clip-path", image_clip_path)
            group.tail, image.tail = image.tail, None
            image.getparent().replace(image, group)
            group.append(image)
            if intensity is not None:
                zoom = format_js_number(1.01 + intensity / 200)
                replace_values(animate_transforms[0], "hover_effect_zoom", zoom)
                if effect == "image_zoom_out":
                    style = next(root.iter(f"{SVG_NAMESPACE}style"))
                    text = "".join(style.itertext()).replace(
                        "hover_effect_zoom", zoom, 1
                    )
                    style[:] = []
                    style.text = text
                if effect == "dolly_zoom":
                    dolly = format_js_number(0.99 - intensity / 2000)
                    for animate_transform in animate_transforms[1:]:
                        replace_values(animate_transform, "hover_effect_zoom", dolly)
            if effect == "dolly_zoom":
                clip_path.set("style", "transform-origin: center;")
        elif effect == "image_mirror_blur":
            image = next(root.iter(f"{SVG_NAMESPACE}image"))
            image.set("id", "shapeImage")
            image.set("style", "transform-origin: center;")
            mirror = image.makeelement(image.tag, image.attrib)
            mirror.set("id", "shapeImageMirror")
            mirror.set("filter", "url(#blurFilter)")
            image.addprevious(mirror)
            if intensity is not None:
                zoom = format_js_number(0.99 - intensity / 200)
                replace_values(animate_transforms[0], "hover_effect_zoom", zoom)
