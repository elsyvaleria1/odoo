import base64
import io

from lxml import etree
from PIL import Image

import odoo.tests
from odoo.tests.common import HttpCase, new_test_user
from odoo.tools.json import scriptsafe as json_safe
from odoo.tools.misc import file_open

SVG = "{http://www.w3.org/2000/svg}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
GIF_PIXEL = "R0lGODlhAQABAIAAAP///wAAACwAAAAAAQABAAACAkQBADs="


def png(width, height):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "red").save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def template(shape_id):
    module, directory, name = shape_id.split("/")
    with file_open(
        f"{module}/static/image_shapes/{directory}/{name}.svg", "rb"
    ) as file:
        return etree.fromstring(file.read())


class ImageShapeCase(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = new_test_user(
            cls.env,
            login="image_shape_author",
            groups="base.group_user,base.group_partner_manager",
        )
        cls.partner = cls.env["res.partner"].create({"name": "Image owner"})

    def setUp(self):
        super().setUp()
        self.authenticate(self.author.login, self.author.login)

    def _original(self, datas=GIF_PIXEL, name="pixel.gif", **values):
        return (
            self.env["ir.attachment"]
            .with_user(self.author)
            .create(
                {
                    "name": name,
                    "datas": datas,
                    "res_model": "res.partner",
                    "res_id": self.partner.id,
                    **values,
                }
            )
        )

    def _modify(self, original, **params):
        return self.url_open(
            f"/html_editor/modify_image/{original.id}",
            headers={"Content-Type": "application/json"},
            data=json_safe.dumps(
                {
                    "params": {
                        "res_model": "res.partner",
                        "res_id": self.partner.id,
                        "name": "shaped.svg",
                        **params,
                    }
                }
            ),
        ).json()

    def _shaped(self, original):
        return self.env["ir.attachment"].search(
            [("original_id", "=", original.id)], order="id desc", limit=1
        )

    def _rendered(self, original, **params):
        response = self._modify(original, **params)
        self.assertNotIn("error", response)
        shaped = self._shaped(original)
        self.assertEqual(shaped.mimetype, "image/svg+xml")
        return etree.fromstring(shaped.raw)


@odoo.tests.tagged("-at_install", "post_install")
class TestImageShapeSave(ImageShapeCase):
    def test_a_shaped_image_is_built_from_the_shipped_template(self):
        self.assertFalse(
            self.env["ir.ui.view"].with_user(self.author).has_access("write")
        )
        shape_id = "html_builder/geometric/geo_diamond"
        original = self._original()

        root = self._rendered(original, data=GIF_PIXEL, shape={"id": shape_id})

        shipped = template(shape_id)
        self.assertEqual(
            root.find(".//*[@id='filterPath']").get("d"),
            shipped.find(".//*[@id='filterPath']").get("d"),
        )
        self.assertIsNone(root.find(".//*[@id='preview']"))
        (image,) = root.iter(f"{SVG}image")
        self.assertEqual(image.get(XLINK_HREF), f"data:image/gif;base64,{GIF_PIXEL}")
        self.assertEqual((root.get("width"), root.get("height")), ("1", "1"))

    def test_a_raster_is_measured_from_its_pixels(self):
        original = self._original()

        root = self._rendered(
            original,
            data=png(40, 30),
            shape={"id": "html_builder/geometric/geo_diamond"},
        )

        self.assertEqual((root.get("width"), root.get("height")), ("40", "30"))
        self.assertTrue(
            next(root.iter(f"{SVG}image"))
            .get(XLINK_HREF)
            .startswith("data:image/png;base64,")
        )

    def test_a_forced_size_shape_keeps_its_ratio_at_the_requested_width(self):
        shape_id = "html_builder/devices/iphone_front_portrait"
        shipped = template(shape_id)
        ratio = float(shipped.get("width")) / float(shipped.get("height"))

        root = self._rendered(
            self._original(), data=png(40, 30), shape={"id": shape_id, "width": 340}
        )

        self.assertEqual(root.get("width"), "340")
        self.assertAlmostEqual(float(root.get("height")), 340 / ratio)

    def test_colours_replace_the_palette_of_the_template(self):
        shape_id = "html_builder/pattern/pattern_wave_4"
        self.assertIn(b"#3AADAA", etree.tostring(template(shape_id)))

        root = self._rendered(
            self._original(),
            data=GIF_PIXEL,
            shape={
                "id": shape_id,
                "colors": ["#123456", "rgba(1, 2, 3, 0.5)", "", "", ""],
            },
        )

        text = etree.tostring(root).decode()
        self.assertNotIn("#3AADAA", text)
        self.assertIn("#123456", text)
        self.assertNotIn("#7C6576", text)
        self.assertIn("rgba(1, 2, 3, 0.5)", text)
        self.assertIn("#F6F6F6", text)

    def test_flip_and_rotation_transform_the_clip_path(self):
        root = self._rendered(
            self._original(),
            data=GIF_PIXEL,
            shape={
                "id": "html_builder/geometric/geo_triangle",
                "flip": "xy",
                "rotate": 90,
            },
        )

        self.assertEqual(
            root.find(".//*[@id='filterPath']").get("style"),
            "transform: scale(-1) rotate(90deg); transform-origin: 0.5px 0.5px;",
        )

    def test_an_animation_speed_scales_the_durations(self):
        shape_id = "html_builder/special/special_filter"
        self.assertIn(b'dur="', etree.tostring(template(shape_id)))

        root = self._rendered(
            self._original(),
            data=GIF_PIXEL,
            shape={"id": shape_id, "animation_speed": 1},
        )

        self.assertIn("--animation_ratio: 2.000;", etree.tostring(root).decode())

    def test_an_svg_original_is_embedded_from_its_stored_content(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"/>'
        original = self.env["ir.attachment"].create(
            {
                "name": "drawing.svg",
                "raw": svg,
                "mimetype": "image/svg+xml",
                "res_model": "ir.ui.view",
                "res_id": 0,
                "public": True,
            }
        )
        self.assertEqual(original.mimetype, "image/svg+xml")

        response = self._modify(
            original, shape={"id": "html_builder/geometric/geo_diamond"}
        )

        self.assertNotIn("error", response)
        root = etree.fromstring(self._shaped(original).raw)
        self.assertEqual(
            next(root.iter(f"{SVG}image")).get(XLINK_HREF),
            f"data:image/svg+xml;base64,{base64.b64encode(svg).decode()}",
        )
        self.assertEqual((root.get("width"), root.get("height")), ("20", "10"))


@odoo.tests.tagged("-at_install", "post_install")
class TestImageShapeRefusals(ImageShapeCase):
    SVG_BYTES = (
        '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
        "<script>alert(document.domain)</script></svg>"
    )

    def _assert_refused(self, original, **params):
        response = self._modify(original, **params)
        self.assertIn("error", response, response)
        self.assertFalse(self._shaped(original))

    def test_raw_svg_bytes_are_refused(self):
        data = base64.b64encode(self.SVG_BYTES.encode()).decode()
        for mimetype in ("image/svg+xml", "image/png", None):
            with self.subTest(mimetype=mimetype):
                self._assert_refused(self._original(), data=data, mimetype=mimetype)

    def test_raw_svg_bytes_are_refused_from_a_view_writer(self):
        self.authenticate("admin", "admin")
        original = self.env["ir.attachment"].create(
            {
                "name": "pixel.gif",
                "datas": GIF_PIXEL,
                "res_model": "ir.ui.view",
                "res_id": 0,
            }
        )
        data = base64.b64encode(self.SVG_BYTES.encode()).decode()

        response = self.url_open(
            f"/html_editor/modify_image/{original.id}",
            headers={"Content-Type": "application/json"},
            data=json_safe.dumps(
                {"params": {"data": data, "mimetype": "image/svg+xml", "name": "x.svg"}}
            ),
        ).json()

        self.assertIn("error", response)
        self.assertFalse(self._shaped(original))

    def test_a_markup_mimetype_is_refused_for_raster_bytes(self):
        self._assert_refused(self._original(), data=GIF_PIXEL, mimetype="image/svg+xml")

    def test_svg_bytes_are_not_a_shape_source(self):
        data = base64.b64encode(self.SVG_BYTES.encode()).decode()
        self._assert_refused(
            self._original(),
            data=data,
            shape={"id": "html_builder/geometric/geo_diamond"},
        )

    def test_an_unknown_shape_is_refused(self):
        for shape_id in (
            "html_builder/geometric/nope",
            "html_builder/../../base/static/description/icon",
            "html_builder/geometric",
            "base/geometric/geo_diamond",
            None,
        ):
            with self.subTest(shape_id=shape_id):
                self._assert_refused(
                    self._original(), data=GIF_PIXEL, shape={"id": shape_id}
                )

    def test_a_colour_that_is_not_one_is_refused(self):
        for colour in (
            'red"/><script>alert(1)</script>',
            "url(#x)",
            "expression(1)",
            7,
        ):
            with self.subTest(colour=colour):
                self._assert_refused(
                    self._original(),
                    data=GIF_PIXEL,
                    shape={
                        "id": "html_builder/pattern/pattern_wave_4",
                        "colors": [colour],
                    },
                )

    def test_out_of_range_parameters_are_refused(self):
        for params in (
            {"flip": "z"},
            {"rotate": 45},
            {"animation_speed": "Infinity"},
            {"animation_speed": "fast"},
            {"width": 0},
            {"width": "100px"},
            {"colors": ["#123456"] * 6},
            {"onload": "alert(1)"},
        ):
            with self.subTest(params=params):
                self._assert_refused(
                    self._original(),
                    data=GIF_PIXEL,
                    shape={"id": "html_builder/geometric/geo_triangle", **params},
                )

    def test_a_neutered_original_is_not_a_shape_source(self):
        original = self._original(
            datas=base64.b64encode(self.SVG_BYTES.encode()).decode(),
            name="drawing.svg",
            mimetype="image/svg+xml",
        )
        self.assertEqual(original.mimetype, "text/plain")

        self._assert_refused(
            original, shape={"id": "html_builder/geometric/geo_diamond"}
        )
