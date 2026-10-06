from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestVehicleMenus(TransactionCase):
    """A vehicle is an asset, so its menus live in the Assets app: this module
    ships no app of its own."""

    def test_vehicles_have_no_app_of_their_own(self):
        roots = (
            self.env["ir.ui.menu"]
            .with_context(active_test=False)
            .search([("parent_id", "=", False)])
        )
        owned = self.env["ir.model.data"].search(
            [
                ("module", "=", "resource_asset_vehicle"),
                ("model", "=", "ir.ui.menu"),
                ("res_id", "in", roots.ids),
            ]
        )
        self.assertFalse(owned.mapped("name"))

    def test_the_vehicle_section_hangs_from_an_app(self):
        section = self.env.ref("resource_asset_vehicle.fleet_vehicles")
        self.assertTrue(section.parent_id)
        self.assertEqual(section.name, "Vehicles")
