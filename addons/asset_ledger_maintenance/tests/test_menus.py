from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestVehicleMaintenanceMenu(TransactionCase):
    """Vehicle maintenance sits in the Assets app beside Equipment Maintenance,
    behind the vehicle family's enable-group."""

    def test_vehicle_maintenance_is_in_the_assets_app(self):
        menu = self.env.ref("asset_ledger_maintenance.menu_fleet_maintenance")
        self.assertEqual(
            menu.parent_id, self.env.ref("asset_ledger.menu_general_assets_root")
        )
        clerk = new_test_user(
            self.env,
            login="vehicle_maintenance_clerk",
            groups="asset_ledger.group_asset_user",
        )
        desk = new_test_user(
            self.env,
            login="vehicle_maintenance_desk",
            groups="asset_ledger.group_asset_user,asset_ledger.group_enable_fleet_assets",
        )
        menus = self.env["ir.ui.menu"]
        self.assertNotIn(menu.id, menus.with_user(clerk)._get_visible_menu_ids())
        self.assertIn(menu.id, menus.with_user(desk)._get_visible_menu_ids())
