from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.geo_type_reflection import ReflectionParcel


@tagged("post_install", "-at_install", "geoengine_audit")
class TestGeoTypeReflection(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Parcel = cls.env[ReflectionParcel._name]

    def test_geo_field_reflects_its_own_geo_type_srid_and_dim(self):
        field = self.env["ir.model.fields"]._get(self.Parcel._name, "boundary")
        self.assertEqual(field.geo_type, "Polygon")
        self.assertEqual(field.srid, 4326)
        self.assertEqual(field.dim, "2")

    def test_non_geo_field_on_the_same_model_reflects_no_geo_metadata(self):
        field = self.env["ir.model.fields"]._get(self.Parcel._name, "name")
        self.assertFalse(field.geo_type)
        self.assertFalse(field.srid)
        self.assertFalse(field.dim)

    def test_a_non_geo_model_reflected_first_does_not_drop_the_columns(self):
        self.env.cr.execute(
            "UPDATE ir_model_fields SET geo_type = NULL, srid = NULL, dim = NULL"
            " WHERE model = %s",
            (self.Parcel._name,),
        )
        with self.registry.init_models_window(install=False):
            self.env["ir.model.fields"]._reflect_fields(
                ["res.currency", self.Parcel._name]
            )
        self.env.invalidate_all()
        field = self.env["ir.model.fields"]._get(self.Parcel._name, "boundary")
        self.assertEqual(field.geo_type, "Polygon")
        self.assertEqual(field.srid, 4326)
        self.assertEqual(field.dim, "2")
