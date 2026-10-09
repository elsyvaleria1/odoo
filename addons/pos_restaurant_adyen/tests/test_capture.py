from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon


@tagged("post_install", "-at_install")
class TestAdyenCapture(TestPointOfSaleHttpCommon):
    def test_the_captured_amount_is_rounded_to_minor_units(self):
        adyen = self.env["pos.payment.method"].create(
            {
                "name": "Adyen capture",
                "use_payment_terminal": "adyen",
                "adyen_terminal_identifier": "P400Plus-capture",
                "adyen_merchant_account": "Merchant",
                "payment_method_type": "terminal",
                "journal_id": self.bank_journal.id,
            }
        )
        self.main_pos_config.write({"payment_method_ids": [Command.link(adyen.id)]})
        self.main_pos_config.with_user(self.pos_user).open_ui()
        order = self.env["pos.order"].create(
            {
                "session_id": self.main_pos_config.current_session_id.id,
                "amount_paid": 0.0,
                "amount_total": 19.99,
                "amount_tax": 0.0,
                "amount_return": 0.0,
            }
        )
        payment = self.env["pos.payment"].create(
            {
                "amount": 19.99,
                "payment_method_id": adyen.id,
                "pos_order_id": order.id,
                "transaction_id": "PSP1",
            }
        )
        captured = []
        with patch.object(
            type(adyen),
            "proxy_adyen_request",
            lambda method, data, operation: captured.append(data) or True,
        ):
            payment._adyen_capture()
        self.assertEqual(captured[0]["modificationAmount"]["value"], 1999)
