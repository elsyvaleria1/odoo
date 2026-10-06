import psycopg

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.raster_layer import RasterSite


@tagged("post_install", "-at_install")
class TestGeoRasterLayer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.env[RasterSite._name],)
        cls.geo_view = cls.env["ir.ui.view"].create(
            {
                "name": "raster fixture view",
                "model": RasterSite._name,
                "type": "geoengine",
                "arch": '<geoengine><field name="position"/><templates>'
                '<t t-name="info_box"><div>x</div></t></templates></geoengine>',
            },
        )

    def test_create_osm_layer(self):
        layer = self.env["geoengine.raster.layer"].create(
            {
                "name": "OSM Base Layer",
                "view_id": self.geo_view.id,
                "raster_type": "osm",
            },
        )

        self.assertTrue(layer)
        self.assertEqual(layer.name, "OSM Base Layer")
        self.assertEqual(layer.raster_type, "osm")

    def test_create_xyz_layer_with_url(self):
        layer = self.env["geoengine.raster.layer"].create(
            {
                "name": "Mapbox Tiles",
                "view_id": self.geo_view.id,
                "raster_type": "xyz",
                "url": "https://api.mapbox.com/styles/v1/{z}/{x}/{y}",
            },
        )

        self.assertEqual(layer.raster_type, "xyz")
        self.assertIn("mapbox", layer.url)

    def test_create_wmts_layer(self):
        layer = self.env["geoengine.raster.layer"].create(
            {
                "name": "WMTS Layer",
                "view_id": self.geo_view.id,
                "raster_type": "wmts",
                "wmts_layer": "layer",
                "url": "https://wmts.example.com/service",
                "matrix_set": "EPSG:3857",
                "format_suffix": "png",
                "request_encoding": "REST",
            },
        )

        self.assertEqual(layer.raster_type, "wmts")

    def test_a_wmts_layer_names_the_layer_it_requests(self):
        with self.assertRaises(ValidationError):
            self.env["geoengine.raster.layer"].create(
                {
                    "name": "Geology",
                    "view_id": self.geo_view.id,
                    "raster_type": "wmts",
                    "url": "https://wmts.example.com/service",
                    "matrix_set": "GoogleMapsCompatible",
                }
            )

    def test_create_wms_layer(self):
        layer = self.env["geoengine.raster.layer"].create(
            {
                "name": "WMS Layer",
                "view_id": self.geo_view.id,
                "raster_type": "d_wms",
                "url": "https://wms.example.com/service",
                "params_wms": '{"LAYERS": "boundaries"}',
            },
        )

        self.assertEqual(layer.raster_type, "d_wms")

    def test_url_validation_invalid_url(self):
        with self.assertRaises(ValidationError):
            self.env["geoengine.raster.layer"].create(
                {
                    "name": "Invalid URL Layer",
                    "view_id": self.geo_view.id,
                    "raster_type": "xyz",
                    "url": "not-a-valid-url",
                },
            )

    def test_url_validation_osm_no_url_required(self):
        layer = self.env["geoengine.raster.layer"].create(
            {
                "name": "OSM No URL",
                "view_id": self.geo_view.id,
                "raster_type": "osm",
                "url": "",
            },
        )
        self.assertTrue(layer)

    def test_params_json_validation_valid(self):
        layer = self.env["geoengine.raster.layer"].create(
            {
                "name": "WMTS with params",
                "view_id": self.geo_view.id,
                "raster_type": "wmts",
                "wmts_layer": "layer",
                "url": "https://wmts.example.com/service",
                "params": '{"time": "2024-01-01", "layer": "default"}',
            },
        )
        self.assertEqual(layer.params, '{"time": "2024-01-01", "layer": "default"}')

    def test_params_json_validation_invalid(self):
        with self.assertRaises(ValidationError):
            self.env["geoengine.raster.layer"].create(
                {
                    "name": "Invalid JSON params",
                    "view_id": self.geo_view.id,
                    "raster_type": "wmts",
                    "wmts_layer": "layer",
                    "url": "https://wmts.example.com/service",
                    "params": "not valid json",
                },
            )

    def test_params_wms_json_validation_invalid(self):
        with self.assertRaises(ValidationError):
            self.env["geoengine.raster.layer"].create(
                {
                    "name": "Invalid WMS params",
                    "view_id": self.geo_view.id,
                    "raster_type": "d_wms",
                    "url": "https://wms.example.com/service",
                    "params_wms": "{invalid json}",
                },
            )

    def test_opacity_constraint_valid(self):
        layer = self.env["geoengine.raster.layer"].create(
            {
                "name": "Semi-transparent layer",
                "view_id": self.geo_view.id,
                "raster_type": "osm",
                "opacity": 0.5,
            },
        )
        self.assertEqual(layer.opacity, 0.5)

    def test_opacity_constraint_invalid(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.env["geoengine.raster.layer"].create(
                {
                    "name": "Invalid opacity",
                    "view_id": self.geo_view.id,
                    "raster_type": "osm",
                    "opacity": 1.5,
                },
            )

    def test_sequence_positive_constraint(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.env["geoengine.raster.layer"].create(
                {
                    "name": "Negative sequence",
                    "view_id": self.geo_view.id,
                    "raster_type": "osm",
                    "sequence": -1,
                },
            )

    def test_overlay_layer_flag(self):
        base_layer = self.env["geoengine.raster.layer"].create(
            {
                "name": "Base OSM",
                "view_id": self.geo_view.id,
                "raster_type": "osm",
                "overlay": False,
            },
        )
        self.assertFalse(base_layer.overlay)

        overlay_layer = self.env["geoengine.raster.layer"].create(
            {
                "name": "Overlay WMS",
                "view_id": self.geo_view.id,
                "raster_type": "d_wms",
                "params_wms": '{"LAYERS": "topp:states"}',
                "url": "https://wms.example.com",
                "overlay": True,
            },
        )
        self.assertTrue(overlay_layer.overlay)

    def test_layer_ordering_by_sequence(self):
        layer1 = self.env["geoengine.raster.layer"].create(
            {
                "name": "Layer with sequence 10",
                "view_id": self.geo_view.id,
                "raster_type": "osm",
                "sequence": 10,
            },
        )
        layer2 = self.env["geoengine.raster.layer"].create(
            {
                "name": "Layer with sequence 5",
                "view_id": self.geo_view.id,
                "raster_type": "osm",
                "sequence": 5,
            },
        )

        layers = self.env["geoengine.raster.layer"].search(
            [("id", "in", [layer1.id, layer2.id])],
        )

        self.assertEqual(layers[0].sequence, 5)
        self.assertEqual(layers[1].sequence, 10)

    def test_all_raster_types(self):
        raster_types = [
            ("osm", {}),
            ("xyz", {"url": "https://tiles.example.com/{z}/{x}/{y}.png"}),
            ("google", {}),
            ("wmts", {"url": "https://wmts.example.com", "wmts_layer": "layer"}),
            (
                "d_wms",
                {
                    "url": "https://wms.example.com",
                    "params_wms": '{"LAYERS": "topp:states"}',
                },
            ),
        ]

        for raster_type, extra_vals in raster_types:
            with self.subTest(raster_type=raster_type):
                vals = {
                    "name": f"Test {raster_type} layer",
                    "view_id": self.geo_view.id,
                    "raster_type": raster_type,
                    **extra_vals,
                }
                layer = self.env["geoengine.raster.layer"].create(vals)
                self.assertEqual(layer.raster_type, raster_type)
                layer.unlink()

    def test_xyz_url_must_carry_placeholders(self):
        with self.assertRaises(ValidationError):
            self.env["geoengine.raster.layer"].create(
                {
                    "name": "XYZ no placeholders",
                    "view_id": self.geo_view.id,
                    "raster_type": "xyz",
                    "url": "https://tiles.example.com/map.png",
                },
            )

    def test_xyz_requires_a_url(self):
        with self.assertRaises(ValidationError):
            self.env["geoengine.raster.layer"].create(
                {
                    "name": "XYZ no url",
                    "view_id": self.geo_view.id,
                    "raster_type": "xyz",
                },
            )

    def test_wms_requires_layers_param(self):
        with self.assertRaises(ValidationError):
            self.env["geoengine.raster.layer"].create(
                {
                    "name": "WMS no layers",
                    "view_id": self.geo_view.id,
                    "raster_type": "d_wms",
                    "url": "https://wms.example.com/service",
                    "params_wms": '{"FORMAT": "image/png"}',
                },
            )

    def test_osm_needs_no_url(self):
        layer = self.env["geoengine.raster.layer"].create(
            {"name": "OSM", "view_id": self.geo_view.id, "raster_type": "osm"},
        )
        self.assertTrue(layer)


@tagged("post_install", "-at_install")
class TestNewRasterTypes(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.env[RasterSite._name],)
        cls.geo_view = cls.env["ir.ui.view"].create(
            {
                "name": "Raster fixture view",
                "model": RasterSite._name,
                "type": "geoengine",
                "arch": '<geoengine><field name="position"/><templates>'
                '<t t-name="info_box"><div>x</div></t></templates></geoengine>',
            },
        )

    def _layer(self, **overrides):
        vals = {
            "name": "Background",
            "view_id": self.geo_view.id,
            "raster_type": "mvt",
            "url": "https://tiles.example.com/{z}/{x}/{y}.pbf",
        }
        vals.update(overrides)
        return self.env["geoengine.raster.layer"].create(vals)

    def test_vector_tiles_need_the_xyz_placeholders(self):
        with self.assertRaises(ValidationError):
            self._layer(url="https://tiles.example.com/tiles.pbf")

    def test_vector_tiles_accept_a_templated_url(self):
        layer = self._layer()
        self.assertEqual(layer.raster_type, "mvt")

    def test_single_image_wms_saves_with_its_layers(self):
        layer = self._layer(
            raster_type="i_wms",
            url="https://wms.example.com/geoserver/wms",
            params_wms='{"LAYERS": "topp:states"}',
            server_type="geoserver",
        )
        self.assertEqual(layer.raster_type, "i_wms")

    def test_single_image_wms_still_requires_layers(self):
        with self.assertRaises(ValidationError):
            self._layer(
                raster_type="i_wms",
                url="https://wms.example.com/geoserver/wms",
                params_wms='{"FORMAT": "image/png"}',
                server_type="geoserver",
            )

    def test_both_new_types_require_a_url(self):
        for raster_type in ("i_wms", "mvt"):
            with (
                self.subTest(raster_type=raster_type),
                self.assertRaises(ValidationError),
            ):
                self._layer(raster_type=raster_type, url=False)
