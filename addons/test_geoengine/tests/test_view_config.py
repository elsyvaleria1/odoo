import base64

from odoo.exceptions import MissingError, ValidationError
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.view_config import ConfigZone, CountZone

ARCH = (
    '<geoengine><field name="area"/><templates>'
    '<t t-name="info_box"><div>x</div></t></templates></geoengine>'
)


@tagged("post_install", "-at_install")
class TestViewConfig(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Zone = cls.env[ConfigZone._name]
        cls.geo_field = cls.env["ir.model.fields"].search(
            [("model", "=", "config.zone"), ("name", "=", "area")], limit=1
        )

    def _make_view(self, name, **settings):
        view = self.env["ir.ui.view"].create(
            {"name": name, "model": "config.zone", "type": "geoengine", "arch": ARCH}
        )
        if settings:
            self.env["geoengine.view.settings"].create({"view_id": view.id} | settings)
        self.env["geoengine.raster.layer"].create(
            {"name": f"raster-{name}", "view_id": view.id, "raster_type": "osm"}
        )
        self.env["geoengine.vector.layer"].create(
            {
                "name": f"vector-{name}",
                "view_id": view.id,
                "geo_repr": "basic",
                "geo_field_id": self.geo_field.id,
            }
        )
        return view

    def test_get_layers_uses_the_requested_view(self):
        alpha = self._make_view("ALPHA")
        beta = self._make_view("BETA")
        self.env.flush_all()

        for view, expected in ((alpha, "vector-ALPHA"), (beta, "vector-BETA")):
            layers = self.Zone.get_layers(view.id)
            self.assertEqual([a["name"] for a in layers["actives"]], [expected])
            self.assertEqual(
                [b["name"] for b in layers["backgrounds"]],
                [f"raster-{view.name}"],
            )

    def test_get_layers_without_view_id_keeps_first_view(self):
        alpha = self._make_view("ALPHA")
        self._make_view("BETA")
        self.env.flush_all()
        layers = self.Zone.get_layers()
        self.assertEqual([a["name"] for a in layers["actives"]], ["vector-ALPHA"])
        self.assertEqual(self.Zone._get_geo_view().id, alpha.id)

    def test_get_layers_rejects_a_foreign_view(self):
        other = self.env["ir.ui.view"].search([("type", "=", "list")], limit=1)
        with self.assertRaises(MissingError):
            self.Zone.get_layers(other.id)

    def test_malformed_extent_is_rejected(self):
        for bad in ("not-an-extent-at-all", "1, 2, 3", "a, b, c, d"):
            with self.assertRaises(ValidationError):
                self._make_view("bad", default_map_extent=bad)

    def test_inverted_extent_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._make_view("inv", restricted_extent="10, 10, 0, 0")

    def test_valid_extent_is_accepted(self):
        view = self._make_view("ok", default_map_extent="-100.5, 10, -90, 25.5")
        self.assertTrue(view.id)

    def test_unresolvable_projection_is_rejected(self):
        for bad in ("EPSG:99999", "3857", "WGS84"):
            with self.assertRaises(ValidationError):
                self._make_view("badproj", projection=bad)

    def test_supported_projections_are_accepted(self):
        for good in ("EPSG:3857", "EPSG:4326", "EPSG:32614", "EPSG:6372"):
            self.assertTrue(self._make_view("goodproj", projection=good).id)

    def test_zoom_and_threshold_ranges(self):
        with self.assertRaises(ValidationError):
            self._make_view("z", default_map_zoom=999)
        with self.assertRaises(ValidationError):
            self._make_view("t", webgl_threshold=-5)
        self.assertTrue(self._make_view("okz", default_map_zoom=12).id)

    def test_skip_invalid_survives_a_bad_property_value(self):
        square = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]

        def feat(qty):
            return {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [square]},
                "properties": {"qty": qty},
            }

        payload = {
            "type": "FeatureCollection",
            "features": [feat(1), feat(2), feat("not-a-number"), feat(4)],
        }
        model = self.env["ir.model"].search([("model", "=", "config.zone")], limit=1)
        qty_field = self.env["ir.model.fields"].search(
            [("model", "=", "config.zone"), ("name", "=", "qty")], limit=1
        )
        wizard = self.env["wizard.base.import.geodata"].create(
            {
                "model_id": model.id,
                "geo_field_id": self.geo_field.id,
                "skip_invalid": True,
                "file_data": base64.b64encode(json_dumps_bytes(payload)),
                "file_name": "t.geojson",
                "mapping_lines": [
                    (0, 0, {"property_name": "qty", "field_id": qty_field.id})
                ],
            }
        )
        before = self.Zone.search_count([])
        wizard.action_import()
        self.env.flush_all()
        self.assertEqual(self.Zone.search_count([]) - before, 3)
        self.assertEqual(wizard.imported_count, 3)


@tagged("post_install", "-at_install")
class TestLayerValueCount(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Zone = cls.env[CountZone._name]
        cls.model = cls.env["ir.model"].search([("model", "=", "count.zone")], limit=1)
        cls.geo_field = cls.env["ir.model.fields"].search(
            [("model", "=", "count.zone"), ("name", "=", "area")], limit=1
        )
        cls.attr_field = cls.env["ir.model.fields"].search(
            [("model", "=", "count.zone"), ("name", "=", "grade")], limit=1
        )
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "count view",
                "model": "count.zone",
                "type": "geoengine",
                "arch": ARCH.replace('name="area"', 'name="area"'),
            }
        )

    def _layer(self, **vals):
        return self.env["geoengine.vector.layer"].create(
            {
                "name": "counting",
                "view_id": self.view.id,
                "geo_repr": "colored",
                "classification": "quantile",
                "geo_field_id": self.geo_field.id,
                "attribute_field_id": self.attr_field.id,
                "model_id": self.model.id,
                "nb_class": 1,
            }
            | vals
        )

    def test_archived_records_are_not_counted(self):
        square = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        for i in range(4):
            self.Zone.create({"name": f"live{i}", "area": square, "grade": i})
        for i in range(6):
            self.Zone.create(
                {"name": f"gone{i}", "area": square, "grade": 100 + i, "active": False}
            )
        self.env.flush_all()
        layer = self._layer()
        self.assertEqual(layer._count_distinct_values(), 4)

    def test_model_domain_is_applied(self):
        square = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        for i in range(5):
            self.Zone.create({"name": f"z{i}", "area": square, "grade": i})
        self.env.flush_all()
        layer = self._layer(model_domain="[('grade', '>=', 3)]")
        self.assertEqual(layer._count_distinct_values(), 2)

    def test_unset_numeric_values_still_count(self):
        square = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        self.Zone.create({"name": "has", "area": square, "grade": 7})
        self.Zone.create({"name": "none", "area": square})
        self.env.flush_all()
        self.assertEqual(self._layer()._count_distinct_values(), 2)
