from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.heatmap_cluster import HeatmapSite


@tagged("post_install", "-at_install")
class TestHeatmapAndCluster(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Site = cls.env[HeatmapSite._name]
        cls.model_id = cls.env["ir.model"]._get_id(HeatmapSite._name)
        cls.geo_view = cls.env["ir.ui.view"].create(
            {
                "name": "Heatmap fixture view",
                "model": HeatmapSite._name,
                "type": "geoengine",
                "arch": '<geoengine><field name="name"/></geoengine>',
            },
        )
        cls.point_field = cls._field("position")
        cls.polygon_field = cls._field("footprint")
        cls.tonnage_field = cls._field("tonnage")
        cls.name_field = cls._field("name")

    @classmethod
    def _field(cls, name):
        return cls.env["ir.model.fields"].search(
            [("model", "=", HeatmapSite._name), ("name", "=", name)], limit=1
        )

    def _layer(self, **overrides):
        vals = {
            "name": "Density",
            "view_id": self.geo_view.id,
            "geo_field_id": self.point_field.id,
            "geo_repr": "heatmap",
        }
        vals.update(overrides)
        return self.env["geoengine.vector.layer"].create(vals)

    def test_a_same_model_layer_names_its_model_for_the_domain_editor(self):
        layer = self._layer(geo_repr="basic")
        self.assertFalse(layer.model_id)
        self.assertEqual(layer.model_name, HeatmapSite._name)

    def test_the_domain_editor_s_date_expressions_are_accepted(self):
        layer = self._layer(
            geo_repr="basic",
            model_domain="[('create_date', '<=', context_today().strftime('%Y-%m-%d'))]",
        )
        self.assertEqual(layer._parsed_model_domain()[0][0], "create_date")

    def test_the_fixture_really_has_geo_fields(self):
        self.assertEqual(self.point_field.ttype, "geo_point")
        self.assertEqual(self.polygon_field.ttype, "geo_polygon")

    def test_both_representations_accept_point_geometry(self):
        for repr_name in ("heatmap", "cluster"):
            with self.subTest(geo_repr=repr_name):
                self.assertEqual(self._layer(geo_repr=repr_name).geo_repr, repr_name)

    def test_polygon_geometry_is_refused(self):
        for repr_name in ("heatmap", "cluster"):
            with self.subTest(geo_repr=repr_name), self.assertRaises(ValidationError):
                self._layer(geo_repr=repr_name, geo_field_id=self.polygon_field.id)

    def test_min_distance_above_cluster_distance_is_refused(self):
        with self.assertRaises(ValidationError):
            self._layer(
                geo_repr="cluster", cluster_distance=20, cluster_min_distance=40
            )

    def test_equal_cluster_distances_are_allowed(self):
        layer = self._layer(
            geo_repr="cluster", cluster_distance=30, cluster_min_distance=30
        )
        self.assertEqual(layer.cluster_min_distance, 30)

    def test_negative_cluster_distance_is_refused(self):
        with self.assertRaises(ValidationError):
            self._layer(geo_repr="cluster", cluster_distance=-1)

    def test_non_numeric_heatmap_weight_is_refused(self):
        with self.assertRaises(ValidationError):
            self._layer(heatmap_weight_field_id=self.name_field.id)

    def test_numeric_heatmap_weight_is_accepted(self):
        layer = self._layer(heatmap_weight_field_id=self.tonnage_field.id)
        self.assertEqual(layer.heatmap_weight_field_id, self.tonnage_field)

    def test_zero_radius_and_negative_blur_are_refused(self):
        with self.assertRaises(ValidationError):
            self._layer(heatmap_radius=0)
        with self.assertRaises(ValidationError):
            self._layer(heatmap_blur=-1)

    def test_get_layers_resolves_the_weight_field_name(self):
        self._layer(
            model_id=self.model_id,
            heatmap_weight_field_id=self.tonnage_field.id,
        )

        layers = self.env[HeatmapSite._name].get_layers(view_id=self.geo_view.id)

        [active] = [a for a in layers["actives"] if a["name"] == "Density"]
        self.assertEqual(active["heatmap_weight_field_name"], "tonnage")
        self.assertEqual(active["geo_field_name"], "position")

    def test_get_layers_sends_false_when_no_weight_field_is_set(self):
        self._layer(model_id=self.model_id)

        layers = self.env[HeatmapSite._name].get_layers(view_id=self.geo_view.id)

        [active] = [a for a in layers["actives"] if a["name"] == "Density"]
        self.assertFalse(active["heatmap_weight_field_name"])
