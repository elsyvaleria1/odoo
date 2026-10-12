from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestVehicleMenus(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.section = cls.env.ref("resource_asset_vehicle.fleet_vehicles")
        cls.vehicles = cls.env.ref("resource_asset_vehicle.fleet_vehicle_menu")
        cls.clerk = new_test_user(
            cls.env,
            login="vehicle_menu_clerk",
            groups="asset_ledger.group_asset_user",
        )
        cls.driver_desk = new_test_user(
            cls.env,
            login="vehicle_menu_desk",
            groups="asset_ledger.group_asset_user,asset_ledger.group_enable_fleet_assets",
        )

    def _visible(self, user):
        return self.env["ir.ui.menu"].with_user(user)._get_visible_menu_ids()

    def test_the_vehicle_section_is_in_the_assets_app(self):
        self.assertEqual(
            self.section.parent_id,
            self.env.ref("asset_ledger.menu_general_assets_root"),
        )

    def test_the_enable_group_opens_the_vehicle_section(self):
        visible = self._visible(self.driver_desk)
        self.assertIn(self.section.id, visible)
        self.assertIn(self.vehicles.id, visible)

    def test_an_asset_user_without_it_does_not_see_vehicles(self):
        visible = self._visible(self.clerk)
        self.assertIn(self.env.ref("asset_ledger.menu_general_assets_root").id, visible)
        self.assertNotIn(self.section.id, visible)
