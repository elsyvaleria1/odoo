from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

GIF_PIXEL = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x00\x00"
    b"\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
SVG = "{http://www.w3.org/2000/svg}"


@tagged("-at_install", "post_install")
class TestImageShapeHoverEffect(TransactionCase):
    def _render(self, **hover):
        svg = self.env["ir.attachment"]._render_image_shape(
            {"id": "html_builder/geometric/geo_square", **hover},
            GIF_PIXEL,
            "image/gif",
        )
        return etree.fromstring(svg)

    def _values(self, root, tag):
        return [element.get("values") for element in root.iter(f"{SVG}{tag}")]

    def test_an_overlay_is_coloured_from_the_shipped_effect(self):
        root = self._render(
            hover_effect="overlay", hover_effect_color="rgba(0, 0, 0, 0.25)"
        )

        self.assertIsNotNone(root.find(".//*[@id='hoverEffects']"))
        self.assertEqual(
            root.find(".//*[@id='shapeOverlay']").get("fill"), "rgb(0,0,0)"
        )
        self.assertEqual(self._values(root, "animate"), ["0;0.25"])

    def test_an_outline_takes_its_colour_and_doubled_stroke_width(self):
        root = self._render(
            hover_effect="outline",
            hover_effect_color="#FF000080",
            hover_effect_stroke_width=10,
        )

        border = root.find(".//*[@id='shapeBorder']")
        self.assertEqual(border.get("stroke"), "rgb(255,0,0)")
        self.assertEqual(border.get("stroke-opacity"), repr(128 / 255 * 100 / 100))
        self.assertEqual(self._values(root, "animate"), ["0;20"])

    def test_a_zoom_wraps_the_image_in_its_clip_path(self):
        root = self._render(
            hover_effect="image_zoom_in",
            hover_effect_color="rgba(0, 0, 0, 0)",
            hover_effect_intensity=20,
        )

        image = root.find(f".//{SVG}image")
        self.assertEqual(image.get("id"), "shapeImage")
        self.assertIsNone(image.get("clip-path"))
        self.assertEqual(image.getparent().get("clip-path"), "url(#clip-path)")
        self.assertEqual(root.get("viewBox"), "0 0 1 1")
        self.assertEqual(
            root.find(".//*[@id='clip-path']").get("clipPathUnits"), "userSpaceOnUse"
        )
        self.assertEqual(
            self._values(root, "animateTransform"), [f"1;{1.01 + 20 / 200!r}"]
        )

    def test_a_zoom_out_starts_zoomed(self):
        root = self._render(hover_effect="image_zoom_out", hover_effect_intensity=40)

        style = next(root.iter(f"{SVG}style"))
        self.assertIn(f"scale: {1.01 + 40 / 200!r};", style.text)
        self.assertEqual(len(style), 0)

    def test_a_dolly_zoom_counter_scales_the_clip_path(self):
        root = self._render(hover_effect="dolly_zoom", hover_effect_intensity=20)

        self.assertEqual(
            self._values(root, "animateTransform"),
            [
                f"1;{1.01 + 20 / 200!r}",
                f"1;{0.99 - 20 / 2000!r}",
                f"1;{0.99 - 20 / 2000!r}",
            ],
        )

    def test_a_mirror_blur_doubles_the_image_behind_a_blur(self):
        root = self._render(hover_effect="image_mirror_blur", hover_effect_intensity=20)

        mirror, image = root.iter(f"{SVG}image")
        self.assertEqual(mirror.get("id"), "shapeImageMirror")
        self.assertEqual(mirror.get("filter"), "url(#blurFilter)")
        self.assertEqual(image.get("id"), "shapeImage")
        self.assertEqual(
            self._values(root, "animateTransform"), [f"1;{0.99 - 20 / 200!r}"]
        )

    def test_hover_parameters_out_of_their_range_are_refused(self):
        for hover in (
            {"hover_effect": "onload"},
            {"hover_effect": "../outline"},
            {"hover_effect": ["overlay"]},
            {"hover_effect": "overlay", "hover_effect_color": 'red"/><script>'},
            {"hover_effect": "overlay", "hover_effect_intensity": "20"},
            {"hover_effect": "outline", "hover_effect_stroke_width": 1.5},
            {"hover_effect_color": "#000000"},
        ):
            with self.subTest(hover=hover), self.assertRaises(UserError):
                self._render(**hover)
