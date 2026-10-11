from odoo.tests import TransactionCase


class TestFedexPickupRadiusUnit(TransactionCase):
    def test_recomputes_radius_unit_for_each_carrier(self):
        carrier = self.env["delivery.carrier"]
        records = carrier.new({"name": "One"}) | carrier.new({"name": "Two"})
        for value, xmlid in (
            ("1", "base.product_uom_mile"),
            ("0", "base.product_uom_km"),
        ):
            with self.subTest(value=value):
                self.env["ir.config_parameter"].set_param(
                    "product.volume_in_cubic_feet", value
                )
                records._compute_fedex_locations_radius_unit()
                for record in records:
                    self.assertEqual(
                        record.fedex_locations_radius_unit, self.env.ref(xmlid)
                    )
