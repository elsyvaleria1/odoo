from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestPosConfigPrinterMenu(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config

    def test_printer_menu_tracks_archiving_and_deletion(self):
        self.env["pos.config"].search([]).write({"is_order_printer": False})
        menu = self.env.ref("point_of_sale.menu_pos_preparation_printer")
        for action in ("archive", "unlink"):
            with self.subTest(action=action):
                config = self.config.copy({"name": action, "is_order_printer": True})
                self.assertTrue(menu.active)

                if action == "archive":
                    config.with_context(active_test=False).action_archive()
                else:
                    config.unlink()

                self.assertFalse(menu.active)

    def test_printer_menu_remains_visible_for_other_configs(self):
        first = self.config.copy({"name": "Printer A", "is_order_printer": True})
        second = self.config.copy({"name": "Printer B", "is_order_printer": True})
        menu = self.env.ref("point_of_sale.menu_pos_preparation_printer")
        self.assertIn(menu.id, self.env["ir.ui.menu"].load_menus(False))
        first.action_archive()
        self.assertTrue(menu.active)
        second.unlink()
        self.assertFalse(menu.active)
        self.assertNotIn(menu.id, self.env["ir.ui.menu"].load_menus(False))
        first.with_context(active_test=False).action_unarchive()
        self.assertTrue(menu.active)
        self.assertIn(menu.id, self.env["ir.ui.menu"].load_menus(False))
