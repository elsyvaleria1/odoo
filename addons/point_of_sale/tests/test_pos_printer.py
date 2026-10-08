from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import CommonPosTest


@tagged("post_install", "-at_install")
class TestPosPrinter(CommonPosTest):
    def test_switching_a_printer_to_epson_requires_its_address(self):
        printer = self.env["pos.printer"].create(
            {"name": "Kitchen", "printer_type": "iot", "epson_printer_ip": False}
        )

        with self.assertRaises(ValidationError):
            printer.printer_type = "epson_epos"
