from unittest.mock import patch

from odoo.tests.common import HttpCase, new_test_user, tagged
from odoo.tools.misc import file_open

from odoo.addons.stock_barcode_mrp.controllers.stock_barcode import MRPStockBarcode

URL = (
    "/stock_barcode/print_inventory_commands"
    "?barcode_type=barcode_mrp_commands_and_operation_types"
)


@tagged("post_install", "-at_install")
class TestPrintMrpCommandsRoute(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        new_test_user(
            cls.env,
            login="mrp_commands_operator",
            groups="base.group_user,stock.group_stock_user,mrp.group_mrp_user",
        )
        new_test_user(
            cls.env,
            login="mrp_commands_stock_user",
            groups="base.group_user,stock.group_stock_user",
        )

    def _print(self, login):
        self.authenticate(login, login)
        with file_open(
            "stock_barcode_mrp/static/img/barcodes_mrp_actions.pdf", "rb"
        ) as sheet:
            pages = [sheet.read()]
        with patch.object(MRPStockBarcode, "_get_barcode_pdfs", return_value=pages):
            return self.url_open(URL)

    def test_a_stock_user_who_cannot_operate_manufacturing_is_refused(self):
        self.assertEqual(self._print("mrp_commands_stock_user").status_code, 404)

    def test_a_manufacturing_user_prints_the_commands(self):
        response = self._print("mrp_commands_operator")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
