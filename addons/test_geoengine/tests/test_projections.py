from pyproj import CRS, Transformer

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .test_view_config import ARCH
from odoo.addons.geoengine.models.projections import (
    is_drawable_projection,
    projection_definition,
)
from odoo.addons.test_geoengine.models.view_config import ConfigZone

MEXICO_LCC = 6372
MEXICO_UTM_14 = 6369


@tagged("post_install", "-at_install")
class TestProjections(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Zone = cls.env[ConfigZone._name]

    def _make_view(self, name, **settings):
        view = self.env["ir.ui.view"].create(
            {"name": name, "model": ConfigZone._name, "type": "geoengine", "arch": ARCH}
        )
        if settings:
            self.env["geoengine.view.settings"].create({"view_id": view.id} | settings)
        return view

    def test_a_crs_openlayers_cannot_resolve_is_described_from_postgis(self):
        definition = projection_definition(self.env, MEXICO_LCC)
        self.assertEqual(definition["code"], "EPSG:6372")
        self.assertIn("+proj=lcc", definition["proj4"])
        self.assertIn("+lon_0=-102", definition["proj4"])
        area = CRS.from_epsg(MEXICO_LCC).area_of_use
        expected = Transformer.from_crs(
            4326, MEXICO_LCC, always_xy=True
        ).transform_bounds(area.west, area.south, area.east, area.north, densify_pts=21)
        for got, want in zip(definition["extent"], expected, strict=True):
            self.assertAlmostEqual(got, want, delta=0.01)

    def test_openlayers_built_ins_need_no_definition(self):
        for srid in (4326, 3857, 32614):
            self.assertIsNone(projection_definition(self.env, srid))
            self.assertTrue(is_drawable_projection(self.env, srid))

    def test_a_code_postgis_does_not_know_is_not_drawable(self):
        self.assertIsNone(projection_definition(self.env, 999999))
        self.assertFalse(is_drawable_projection(self.env, 999999))

    def test_a_raster_layer_may_be_in_any_crs_postgis_describes(self):
        view = self._make_view("raster-crs")
        layer = self.env["geoengine.raster.layer"].create(
            {
                "name": "INEGI",
                "view_id": view.id,
                "raster_type": "d_wms",
                "url": "https://example.com/wms",
                "params_wms": '{"LAYERS": "inegi:estados"}',
                "projection": "EPSG:6372",
            }
        )
        self.assertEqual(layer.projection, "EPSG:6372")
        with self.assertRaises(ValidationError):
            layer.projection = "EPSG:999999"

    def test_the_map_receives_every_definition_it_needs_once(self):
        view = self._make_view("lcc-map", projection="EPSG:6372")
        for projection in ("EPSG:6369", "EPSG:6372", "EPSG:3857"):
            self.env["geoengine.raster.layer"].create(
                {
                    "name": f"wms {projection}",
                    "view_id": view.id,
                    "raster_type": "d_wms",
                    "url": "https://example.com/wms",
                    "params_wms": '{"LAYERS": "inegi:estados"}',
                    "projection": projection,
                }
            )
        payload = self.Zone.get_layers(view.id)
        self.assertEqual(payload["projection"], "EPSG:6372")
        self.assertEqual(
            sorted(d["code"] for d in payload["projections"]),
            ["EPSG:6369", "EPSG:6372"],
        )

    def test_a_map_in_built_in_projections_receives_no_definitions(self):
        view = self._make_view("mercator-map", projection="EPSG:3857")
        self.assertEqual(self.Zone.get_layers(view.id)["projections"], [])
