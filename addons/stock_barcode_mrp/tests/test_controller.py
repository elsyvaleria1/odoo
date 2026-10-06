from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestMrpBarcodeSheet(HttpCase):
    def _print_mrp_barcode_sheet(self, login):
        self.env["stock.picking.type"].with_context(active_test=False).search([]).write(
            {"barcode": False}
        )
        self.authenticate(login, login)
        return self.url_open(
            "/stock_barcode/print_inventory_commands"
            "?barcode_type=barcode_mrp_commands_and_operation_types"
        )

    def test_a_manufacturing_user_prints_the_mrp_barcode_sheet(self):
        new_test_user(self.env, login="mrp_printer", groups="mrp.group_mrp_user")
        response = self._print_mrp_barcode_sheet("mrp_printer")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")

    def test_an_inventory_user_outside_manufacturing_cannot_print_it(self):
        new_test_user(self.env, login="mrp_outsider", groups="stock.group_stock_user")
        response = self._print_mrp_barcode_sheet("mrp_outsider")
        self.assertEqual(response.status_code, 404)
