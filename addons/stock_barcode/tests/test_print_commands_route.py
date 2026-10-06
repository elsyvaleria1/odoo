from unittest.mock import patch

from odoo.tests.common import HttpCase, new_test_user, tagged
from odoo.tools.misc import file_open

from odoo.addons.stock_barcode.controllers.stock_barcode import StockBarcodeController


@tagged("post_install", "-at_install")
class TestPrintCommandsRoute(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        new_test_user(
            cls.env,
            login="barcode_commands_stock_user",
            groups="base.group_user,stock.group_stock_user",
        )
        new_test_user(
            cls.env, login="barcode_commands_employee", groups="base.group_user"
        )

    def _print(self, login):
        self.authenticate(login, login)
        with file_open("stock_barcode/static/img/barcodes_actions.pdf", "rb") as sheet:
            pages = [sheet.read()]
        with patch.object(
            StockBarcodeController, "_get_barcode_pdfs", return_value=pages
        ):
            return self.url_open("/stock_barcode/print_inventory_commands")

    def test_a_stock_user_prints_the_commands(self):
        response = self._print("barcode_commands_stock_user")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")

    def test_an_employee_without_the_verb_is_refused(self):
        self.assertEqual(self._print("barcode_commands_employee").status_code, 404)
