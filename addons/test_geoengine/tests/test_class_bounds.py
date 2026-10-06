from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.class_bounds import BoundsParcel


@tagged("post_install", "-at_install", "geoengine_audit")
class TestClassBounds(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Parcel = cls.env[BoundsParcel._name]
        cls.model_id = cls.env["ir.model"]._get_id(cls.Parcel._name)
        cls.geo_field_id = (
            cls.env["ir.model.fields"]._get(cls.Parcel._name, "boundary").id
        )
        cls.yield_field_id = (
            cls.env["ir.model.fields"]._get(cls.Parcel._name, "yield_t").id
        )
        cls.unstored_field_id = (
            cls.env["ir.model.fields"]._get(cls.Parcel._name, "yield_unstored").id
        )
        cls.parcels = cls.Parcel.create(
            [
                {
                    "name": f"P{i}",
                    "yield_t": float(i),
                    "boundary": (
                        f"SRID=4326;POLYGON(({i} 0,{i + 1} 0,{i + 1} 1,{i} 1,{i} 0))"
                    ),
                }
                for i in range(1, 11)
            ]
        )
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "bounds fixture view",
                "model": cls.Parcel._name,
                "type": "geoengine",
                "arch": """
                    <geoengine>
                        <field name="name"/>
                        <templates><t t-name="info_box"><div/></t></templates>
                    </geoengine>
                """,
            }
        )

    def _layer(self, **overrides):
        vals = {
            "name": "bounds layer",
            "view_id": self.view.id,
            "geo_field_id": self.geo_field_id,
            "attribute_field_id": self.yield_field_id,
            "geo_repr": "colored",
            "classification": "interval",
            "nb_class": 4,
        }
        vals.update(overrides)
        return self.env["geoengine.vector.layer"].create(vals)

    def test_target_model_resolves_for_a_same_model_layer(self):
        layer = self._layer()
        self.assertFalse(
            layer.model_id,
            "fixture is not exercising the same-model case if model_id is set",
        )
        self.assertEqual(layer._target_model_name(), self.Parcel._name)

    def test_count_values_sees_a_same_model_layer(self):
        layer = self._layer()
        self.assertEqual(layer._count_distinct_values(), 10)

    def test_bounds_span_the_whole_layer(self):
        layer = self._layer()
        self.assertEqual(layer.get_class_bounds(), {"min": 1.0, "max": 10.0})

    def test_bounds_are_not_the_drawn_subset(self):
        layer = self._layer()
        page = self.Parcel.search([], limit=3)
        self.assertEqual(
            sorted(page.mapped("yield_t")),
            [1.0, 2.0, 3.0],
            "fixture assumption: the first page is a strict subset",
        )
        self.assertEqual(layer.get_class_bounds(), {"min": 1.0, "max": 10.0})

    def test_extra_domain_narrows_the_population(self):
        layer = self._layer()
        bounds = layer.get_class_bounds([("yield_t", "<=", 4.0)])
        self.assertEqual(bounds, {"min": 1.0, "max": 4.0})

    def test_the_layers_own_domain_is_applied(self):
        layer = self._layer(model_domain="[('yield_t', '>=', 8.0)]")
        self.assertEqual(layer.get_class_bounds(), {"min": 8.0, "max": 10.0})

    def test_the_evaluated_layer_domain_replaces_the_stored_one(self):
        layer = self._layer(model_domain="[('yield_t', '>=', 4.0)]")
        bounds = layer.get_class_bounds([("yield_t", "<=", 6.0)])
        self.assertEqual(bounds, {"min": 1.0, "max": 6.0})

    def test_archived_records_are_out_of_scope(self):
        self.Parcel.search([("yield_t", "=", 10.0)]).active = False
        layer = self._layer()
        self.assertEqual(layer.get_class_bounds(), {"min": 1.0, "max": 9.0})

    def test_an_unstored_attribute_field_is_declined(self):
        layer = self._layer(attribute_field_id=self.unstored_field_id)
        self.assertEqual(layer.get_class_bounds(), {})

    def test_no_attribute_field_is_declined(self):
        layer = self._layer(
            attribute_field_id=False, geo_repr="basic", classification=False
        )
        self.assertEqual(layer.get_class_bounds(), {})

    def test_a_domain_matching_nothing_is_declined(self):
        layer = self._layer()
        self.assertEqual(layer.get_class_bounds([("yield_t", ">", 1000.0)]), {})

    def test_values_span_the_whole_layer(self):
        layer = self._layer(classification="quantile")
        values = layer.get_class_values()
        self.assertEqual(len(values), 10)
        self.assertEqual(sorted(values), [float(i) for i in range(1, 11)])

    def test_values_read_the_evaluated_layer_domain(self):
        layer = self._layer(
            classification="quantile", model_domain="[('yield_t', '>=', 3.0)]"
        )
        values = layer.get_class_values([("yield_t", "<=", 7.0)])
        self.assertEqual(sorted(values), [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        self.assertEqual(min(layer.get_class_values()), 3.0)

    def test_values_exclude_archived_records(self):
        self.Parcel.search([("yield_t", "=", 1.0)]).active = False
        layer = self._layer(classification="quantile")
        self.assertNotIn(1.0, layer.get_class_values())

    def test_too_many_values_is_declined_rather_than_shipped(self):
        layer = self._layer(classification="quantile")
        self.assertEqual(layer.get_class_values(limit=3), [])
        self.assertEqual(len(layer.get_class_values(limit=10)), 10)

    def test_values_decline_for_an_unstored_field(self):
        layer = self._layer(
            classification="quantile", attribute_field_id=self.unstored_field_id
        )
        self.assertEqual(layer.get_class_values(), [])

    def test_a_minimum_of_zero_is_a_real_bound(self):
        self.Parcel.create(
            {
                "name": "P0",
                "yield_t": 0.0,
                "boundary": "SRID=4326;POLYGON((0 0,1 0,1 1,0 1,0 0))",
            }
        )
        layer = self._layer()
        self.assertEqual(layer.get_class_bounds(), {"min": 0.0, "max": 10.0})

    def test_quantiles_are_cut_by_the_database_over_the_population(self):
        layer = self._layer(classification="quantile")
        self.assertEqual(
            layer.get_class_quantiles(None, 4), [1.0, 3.25, 5.5, 7.75, 10.0]
        )
        self.assertEqual(
            layer.get_class_quantiles([("yield_t", "<=", 5)], 2), [1.0, 3.0, 5.0]
        )
        self.assertEqual(layer.get_class_quantiles([("id", "=", 0)], 2), [])

    def test_distinct_values_name_each_value_once(self):
        self.Parcel.create(
            [{"name": "dup", "yield_t": 3.0}, {"name": "dup", "yield_t": 3.0}]
        )
        layer = self._layer(classification="unique")
        values = layer.get_class_values(None, distinct=True)
        self.assertEqual(sorted(values), [float(i) for i in range(1, 11)])
        self.assertEqual(len(layer.get_class_values(None)), 12)
