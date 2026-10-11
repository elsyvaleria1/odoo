import contextlib
import math
import re
from base64 import b64encode
from urllib.parse import quote

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.documents import get_format_of_extension
from odoo.libs.filesystem import get_essential_mimetype, guess_mimetype
from odoo.tools.image import base64_to_image, binary_to_image, get_webp_size
from odoo.tools.misc import file_open

from ..tools import format_js_number, replace_animation_duration

_debug = DebugLog(__name__)

SUPPORTED_IMAGE_EXTENSIONS = ("gif", "jpg", "png", "svg", "webp")
SUPPORTED_IMAGE_MIMETYPES = {
    mimetype: f".{extension}"
    for extension in SUPPORTED_IMAGE_EXTENSIONS
    for mimetype in get_format_of_extension(extension).mimetypes
}

SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
SAFE_XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)
CSS_COLOR = re.compile(
    r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})"
    r"|rgba?\(\s*(\d*\.?\d+)\s*(?:,\s*|\s+)(\d*\.?\d+)\s*(?:,\s*|\s+)(\d*\.?\d+)"
    r"\s*(?:[,/]\s*(\d*\.?\d+)(%?)\s*)?\)"
)
IMAGE_SHAPE_ID = re.compile(r"(\w+)/(\w+)/(\w+)")
IMAGE_SHAPE_PALETTE = ("#3AADAA", "#7C6576", "#F6F6F6", "#FFFFFF", "#383E45")
IMAGE_SHAPE_FLIPS = {"": None, "x": "scaleX(-1)", "y": "scaleY(-1)", "xy": "scale(-1)"}
IMAGE_SHAPE_ROTATIONS = (0, 90, 180, 270)
IMAGE_SHAPE_UPLOADED_SOURCES = frozenset(
    {"image/gif", "image/jpeg", "image/png", "image/webp"}
)
BUILT_IMAGE_SHAPE = object()


def is_json_number(value, kind=(int, float)) -> bool:
    return isinstance(value, kind) and not isinstance(value, bool)


def js_round(value: float) -> int:
    return math.floor(value + 0.5)


def parse_css_rgba(color: str) -> tuple[int, int, int, float]:
    match = CSS_COLOR.fullmatch(color)
    if not match:
        raise ValueError(color)
    if match[1] is not None:
        alpha = 1.0 if match[4] is None else float(match[4])
        if match[5]:
            alpha /= 100
        red, green, blue = (
            js_round(float(channel)) for channel in match.group(1, 2, 3)
        )
        return red, green, blue, js_round(alpha * 100)
    digits = color[1:]
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    opacity = int(digits[6:], 16) / 255 * 100 if len(digits) == 8 else 100
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16), opacity


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    local_url = fields.Char(
        string="Attachment URL",
        compute="_compute_local_url",
    )
    image_src = fields.Char(compute="_compute_image_src")
    image_width = fields.Integer(compute="_compute_image_size")
    image_height = fields.Integer(compute="_compute_image_size")
    original_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Original (unoptimized, unresized) attachment",
        index="btree_not_null",
    )

    @api.depends("url", "checksum")
    def _compute_local_url(self) -> None:
        for attachment in self:
            if attachment.url:
                attachment.local_url = attachment.url
            else:
                attachment.local_url = (
                    f"/web/image/{attachment.id}?unique={attachment.checksum}"
                )

    @api.depends("mimetype", "url", "name")
    def _compute_image_src(self) -> None:
        for attachment in self:
            if (
                not attachment.mimetype
                or get_essential_mimetype(attachment.mimetype)
                not in SUPPORTED_IMAGE_MIMETYPES
            ):
                attachment.image_src = False
                continue

            if attachment.type == "url":
                if attachment.url.startswith("/"):
                    attachment.image_src = attachment.url
                else:
                    name = quote(attachment.name)
                    attachment.image_src = f"/web/image/{attachment.id}-redirect/{name}"
            else:
                unique = attachment.checksum[:8]
                if attachment.url:
                    separator = "&" if "?" in attachment.url else "?"
                    attachment.image_src = f"{attachment.url}{separator}unique={unique}"
                else:
                    name = quote(attachment.name)
                    attachment.image_src = f"/web/image/{attachment.id}-{unique}/{name}"

    @api.depends("datas")
    def _compute_image_size(self) -> None:
        for attachment in self:
            try:
                image = base64_to_image(attachment.datas)
                attachment.image_width = image.width
                attachment.image_height = image.height
            except UserError:
                attachment.image_width = 0
                attachment.image_height = 0

    def _get_media_info(self):
        self.check_singleton()
        return self._read_format(
            [
                "id",
                "name",
                "description",
                "mimetype",
                "checksum",
                "url",
                "type",
                "res_id",
                "res_model",
                "public",
                "access_token",
                "image_src",
                "image_width",
                "image_height",
                "original_id",
            ]
        )[0]

    def _can_bypass_rights_on_media_dialog(self, **attachment_data) -> bool:
        return False

    def _can_store_markup(self) -> bool:
        return (
            self.env.context.get("html_editor_built_image_shape") is BUILT_IMAGE_SHAPE
            or super()._can_store_markup()
        )

    def _get_image_shape_source(self, data: str | None) -> tuple[bytes, str]:
        if data:
            image = self._decode_datas(data)
            mimetype = guess_mimetype(image)
            if mimetype not in IMAGE_SHAPE_UPLOADED_SOURCES:
                raise self._prepare_image_shape_error(
                    "source_not_raster", mimetype=mimetype
                )
            return image, mimetype
        self.check_singleton()
        stream = self._to_http_stream()
        mimetype = get_essential_mimetype(stream.mimetype or "")
        if stream.type == "url" or mimetype not in SUPPORTED_IMAGE_MIMETYPES:
            raise self._prepare_image_shape_error(
                "original_not_image", mimetype=mimetype
            )
        return stream.read(), mimetype

    @api.model
    def _render_image_shape(self, shape: dict, image: bytes, mimetype: str) -> bytes:
        if not isinstance(shape, dict):
            raise self._prepare_image_shape_error("not_a_dict")
        params = dict(shape)
        svg = self._get_image_shape_template(params.pop("id", None))
        svg = self._color_image_shape(svg, params.pop("colors", []))
        speed = params.pop("animation_speed", 0)
        if not is_json_number(speed) or not math.isfinite(speed):
            raise self._prepare_image_shape_error("animation_speed")
        if speed:
            svg = replace_animation_duration(svg, speed)
        width = params.pop("width", None)
        if width is not None and not (is_json_number(width, int) and width > 0):
            raise self._prepare_image_shape_error("width")
        root = etree.fromstring(svg.encode(), SAFE_XML_PARSER)
        try:
            aspect_ratio = float(root.get("width")) / float(root.get("height"))
        except TypeError, ValueError, ZeroDivisionError:
            raise self._prepare_image_shape_error("template_size") from None
        self._transform_image_shape(
            root, params.pop("flip", ""), params.pop("rotate", 0)
        )
        self._apply_image_shape_effects(root, params)
        if (preview := root.find(".//*[@id='preview']")) is not None:
            preview.getparent().remove(preview)
        uri = f"data:{mimetype};base64,{b64encode(image).decode()}"
        for image_element in root.iter(f"{SVG_NAMESPACE}image"):
            image_element.set(XLINK_HREF, uri)
        if root.get("data-forced-size"):
            width = width or self._get_image_shape_source_size(image, mimetype)[0]
            height = format_js_number(width / aspect_ratio)
        else:
            width, height = self._get_image_shape_source_size(image, mimetype)
        root.set("width", str(width))
        root.set("height", str(height))
        return etree.tostring(root)

    @api.model
    def _get_image_shape_template(self, shape_id: str | None) -> str:
        match = isinstance(shape_id, str) and IMAGE_SHAPE_ID.fullmatch(shape_id)
        if not match:
            raise self._prepare_image_shape_error("shape_id", shape_id=str(shape_id))
        module, directory, name = match.groups()
        if module == "web_editor":
            module = "html_builder"
        path = f"{module}/static/image_shapes/{directory}/{name}.svg"
        try:
            with file_open(path, "r", filter_ext=(".svg",)) as file:
                return file.read()
        except FileNotFoundError, ValueError:
            raise self._prepare_image_shape_error("shape_missing", path=path) from None

    @api.model
    def _color_image_shape(self, svg: str, colors: list) -> str:
        if not isinstance(colors, list) or len(colors) > len(IMAGE_SHAPE_PALETTE):
            raise self._prepare_image_shape_error("colors")
        for template_color, color in zip(IMAGE_SHAPE_PALETTE, colors, strict=False):
            if color == "":
                continue
            if not isinstance(color, str) or not CSS_COLOR.fullmatch(color):
                raise self._prepare_image_shape_error("color")
            svg = svg.replace(template_color, color)
        return svg

    @api.model
    def _transform_image_shape(self, root, flip: str, rotate: int) -> None:
        if not isinstance(flip, str) or flip not in IMAGE_SHAPE_FLIPS:
            raise self._prepare_image_shape_error("flip")
        if not is_json_number(rotate, int) or rotate not in IMAGE_SHAPE_ROTATIONS:
            raise self._prepare_image_shape_error("rotate")
        transforms = [IMAGE_SHAPE_FLIPS[flip]] if flip else []
        if rotate:
            transforms.append(f"rotate({rotate}deg)")
        if not transforms:
            return
        if (filter_path := root.find(".//*[@id='filterPath']")) is None:
            raise self._prepare_image_shape_error("transform_without_path")
        filter_path.set(
            "style",
            f"transform: {' '.join(transforms)}; transform-origin: 0.5px 0.5px;",
        )

    @api.model
    def _apply_image_shape_effects(self, root, params: dict) -> None:
        if params:
            raise self._prepare_image_shape_error(
                "unknown_parameters", keys=sorted(params)
            )

    @api.model
    def _get_image_shape_source_size(
        self, image: bytes, mimetype: str
    ) -> tuple[int, int]:
        if mimetype == "image/svg+xml":
            try:
                root = etree.fromstring(image, SAFE_XML_PARSER)
            except etree.XMLSyntaxError:
                raise self._prepare_image_shape_error("source_unreadable") from None
            with contextlib.suppress(AttributeError, ValueError):
                return (
                    round(float(root.get("width").removesuffix("px"))),
                    round(float(root.get("height").removesuffix("px"))),
                )
            with contextlib.suppress(AttributeError, ValueError):
                _x, _y, width, height = map(
                    float, root.get("viewBox").replace(",", " ").split()
                )
                return round(width), round(height)
            return 300, 150
        if mimetype == "image/webp":
            with contextlib.suppress(UserError):
                return get_webp_size(image)
        return binary_to_image(image).size

    @api.model
    def _prepare_image_shape_error(self, reason: str, **details) -> UserError:
        _debug.logic("image_shape_refused", reason=reason, **details)
        return UserError(self.env._("This image shape cannot be applied."))
