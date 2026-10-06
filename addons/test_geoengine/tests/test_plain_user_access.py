from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.plain_user_access import PlainSite


@tagged("post_install", "-at_install", "geoengine_audit")
class TestPlainUserAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Site = cls.env[PlainSite._name]
        cls.plain = cls.env["res.users"].create(
            {
                "name": "plain",
                "login": "geoengine_plain",
                "group_ids": [fields.Command.set([cls.env.ref("base.group_user").id])],
            }
        )
        cls.env["ir.access"].create(
            {
                "name": "plain site read",
                "model_id": cls.env["ir.model"]._get_id(PlainSite._name),
                "group_id": cls.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "r",
            }
        )
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "plain fixture view",
                "model": PlainSite._name,
                "type": "geoengine",
                "arch": '<geoengine><field name="name"/></geoengine>',
            },
        )
        field = cls.env["ir.model.fields"]
        cls.position_field = field.search(
            [("model", "=", PlainSite._name), ("name", "=", "position")]
        )
        cls.band_field = field.search(
            [("model", "=", PlainSite._name), ("name", "=", "band")]
        )
        cls.tonnage_field = field.search(
            [("model", "=", PlainSite._name), ("name", "=", "tonnage")]
        )
        for name, band, tonnage in (("a", "low", 1), ("b", "high", 9)):
            cls.Site.create(
                {
                    "name": name,
                    "band": band,
                    "tonnage": tonnage,
                    "position": "SRID=3857;POINT(1 1)",
                }
            )
        cls.Site.flush_model()

    def _layer(self, attribute_field, classification):
        return self.env["geoengine.vector.layer"].create(
            {
                "name": "classified",
                "view_id": self.view.id,
                "geo_field_id": self.position_field.id,
                "attribute_field_id": attribute_field.id,
                "geo_repr": "colored",
                "classification": classification,
                "nb_class": 2,
            }
        )

    def test_plain_user_gets_class_values(self):
        layer = self._layer(self.band_field, "unique").with_user(self.plain)
        self.assertEqual(sorted(layer.get_class_values()), ["high", "low"])

    def test_plain_user_gets_class_bounds(self):
        layer = self._layer(self.tonnage_field, "quantile").with_user(self.plain)
        self.assertEqual(layer.get_class_bounds(), {"min": 1, "max": 9})

    def test_plain_user_opens_trail_wizard_with_a_default_model(self):
        wizard = (
            self.env["wizard.base.view.trail"]
            .with_user(self.plain)
            .with_context(default_trail_model=PlainSite._name)
        )
        defaults = wizard.default_get(["model_id"])
        self.assertEqual(
            defaults.get("model_id"),
            self.env["ir.model"]._get_id(PlainSite._name),
        )
