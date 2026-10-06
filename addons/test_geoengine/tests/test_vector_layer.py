import psycopg

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.vector_layer import LayerOther, LayerSite

ARCH = (
    '<geoengine><field name="name"/><field name="position"/><templates>'
    '<t t-name="info_box"><div>x</div></t></templates></geoengine>'
)


@tagged("post_install", "-at_install")
class TestGeoVectorLayer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Site, cls.Other = (cls.env[LayerSite._name], cls.env[LayerOther._name])
        cls.geo_view = cls.env["ir.ui.view"].create(
            {
                "name": "layer fixture view",
                "model": LayerSite._name,
                "type": "geoengine",
                "arch": ARCH,
            },
        )
        field = cls.env["ir.model.fields"]
        cls.geo_field = field._get(LayerSite._name, "position")
        cls.char_field = field._get(LayerSite._name, "band")
        cls.numeric_field = field._get(LayerSite._name, "tonnage")
        cls.foreign_numeric = field._get(LayerOther._name, "qty")
        cls.foreign_char = field._get(LayerOther._name, "code")

    def _layer(self, **vals):
        return self.env["geoengine.vector.layer"].create(
            {
                "name": "layer",
                "view_id": self.geo_view.id,
                "geo_field_id": self.geo_field.id,
                "geo_repr": "basic",
            }
            | vals
        )

    def test_create_basic_layer(self):
        layer = self._layer(name="Test Basic Layer", begin_color="#FF0000")
        self.assertEqual(layer.name, "Test Basic Layer")
        self.assertEqual(layer.geo_repr, "basic")
        self.assertFalse(layer.model_id, "a same-model layer names no model")
        self.assertEqual(layer.model_name, LayerSite._name)

    def test_layer_opacity_constraint(self):
        self.assertEqual(self._layer(layer_opacity=0.5).layer_opacity, 0.5)
        with self.assertRaises(psycopg.errors.CheckViolation):
            self._layer(layer_opacity=1.5)

    def test_hex_color_validation(self):
        self.assertEqual(self._layer(begin_color="#FF0000").begin_color, "#FF0000")
        self.assertEqual(self._layer(begin_color="#fff").begin_color, "#fff")
        with self.assertRaises(ValidationError):
            self._layer(begin_color="not-a-color")

    def test_colored_representation_requires_numeric_field(self):
        with self.assertRaises(ValidationError):
            self._layer(
                geo_repr="colored",
                classification="interval",
                attribute_field_id=self.char_field.id,
            )

    def test_model_domain_validation(self):
        layer = self._layer(model_domain="[('active', '=', True)]")
        self.assertEqual(layer.model_domain, "[('active', '=', True)]")
        with self.assertRaises(ValidationError):
            self._layer(model_domain="not a valid domain")

    def test_render_engine_options(self):
        for engine in ("inherit", "auto", "webgl", "canvas"):
            self.assertEqual(self._layer(render_engine=engine).render_engine, engine)

    def test_count_distinct_returns_zero_without_attribute(self):
        self.assertEqual(self._layer()._count_distinct_values(), 0)

    def test_attribute_field_must_belong_to_the_layer_model(self):
        with self.assertRaises(ValidationError):
            self._layer(geo_repr="colored", attribute_field_id=self.foreign_numeric.id)

    def test_colored_field_requires_color_field_id(self):
        with self.assertRaises(ValidationError):
            self._layer(geo_repr="colored_field")

    def test_colored_field_with_valid_color_field(self):
        layer = self._layer(geo_repr="colored_field", color_field_id=self.char_field.id)
        self.assertEqual(layer.color_field_id, self.char_field)

    def test_colored_field_color_field_must_match_model(self):
        with self.assertRaises(ValidationError):
            self._layer(geo_repr="colored_field", color_field_id=self.foreign_char.id)

    def test_layer_ordering_by_sequence(self):
        z = self._layer(name="Layer Z", sequence=10)
        a = self._layer(name="Layer A", sequence=5)
        layers = self.env["geoengine.vector.layer"].search([("id", "in", [z.id, a.id])])
        self.assertEqual(layers.mapped("name"), ["Layer A", "Layer Z"])

    def test_class_values_come_from_the_layer_model(self):
        for name, band in (("a", "low"), ("b", "high"), ("c", "low")):
            self.Site.create({"name": name, "band": band, "position": "POINT(1 1)"})
        self.Site.flush_model()
        layer = self._layer(
            geo_repr="colored",
            classification="unique",
            attribute_field_id=self.char_field.id,
        )
        self.assertEqual(sorted(layer.get_class_values()), ["high", "low", "low"])
        self.assertEqual(layer._count_distinct_values(), 2)
