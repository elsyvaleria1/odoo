from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoadCapacity(TransactionCase):
    def test_load_capacity_names_the_configured_units(self):
        hauler = self.env["product.product"].create(
            {"name": "Hauler", "weight_capacity": 5000.0, "volume_capacity": 20.0}
        )
        shown = hauler.with_context(show_load_capacity=True).display_name
        self.assertIn(self.env.ref("uom.product_uom_kgm").display_name, shown)
        self.assertIn(self.env.ref("uom.product_uom_cubic_meter").display_name, shown)
        self.assertNotIn("False", shown)
