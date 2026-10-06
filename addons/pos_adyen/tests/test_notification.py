from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

PAYMENT_HEADER = {
    "ProtocolVersion": "3.0",
    "MessageClass": "Service",
    "MessageType": "Response",
    "MessageCategory": "Payment",
}


@tagged("post_install", "-at_install")
class TestAdyenNotification(HttpCase):
    @mute_logger("odoo.addons.pos_adyen.models.pos_payment_method")
    def test_a_notification_that_is_no_payment_response_is_acknowledged(self):
        for body in (
            "not json",
            json_dumps([1]),
            json_dumps({"SaleToPOIResponse": [1]}),
            json_dumps({"SaleToPOIResponse": "response"}),
            json_dumps({"SaleToPOIResponse": {"MessageHeader": [1]}}),
            json_dumps({"SaleToPOIResponse": {"MessageHeader": "header"}}),
            json_dumps(
                {
                    "SaleToPOIResponse": {
                        "MessageHeader": {**PAYMENT_HEADER, "POIID": ["terminal"]}
                    }
                }
            ),
        ):
            with self.subTest(body=body):
                response = self.url_open(
                    "/pos_adyen/notification",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.json())

    @mute_logger("odoo.addons.pos_adyen.controllers.main")
    def test_a_signed_notification_that_names_no_pos_session_is_acknowledged(self):
        journal = self.env["account.journal"].create(
            {"name": "Adyen terminal", "type": "bank", "code": "ADYNT"}
        )
        method = self.env["pos.payment.method"].create(
            {
                "name": "Adyen",
                "use_payment_terminal": "adyen",
                "adyen_api_key": "my_adyen_api_key",
                "adyen_terminal_identifier": "my_adyen_terminal",
                "payment_method_type": "terminal",
                "journal_id": journal.id,
            }
        )
        header = {
            **PAYMENT_HEADER,
            "POIID": "my_adyen_terminal",
            "SaleID": "sale",
            "ServiceID": "service",
        }
        for transaction_id in ("", "no-session"):
            pos_hmac = method._get_hmac(
                "sale", "service", "my_adyen_terminal", transaction_id
            )
            body = {
                "SaleToPOIResponse": {
                    "MessageHeader": header,
                    "PaymentResponse": {
                        "Response": {
                            "AdditionalResponse": f"metadata.pos_hmac={pos_hmac}"
                        },
                        "SaleData": {
                            "SaleTransactionID": {"TransactionID": transaction_id}
                        },
                    },
                }
            }
            with self.subTest(transaction_id=transaction_id):
                response = self.url_open(
                    "/pos_adyen/notification",
                    data=json_dumps(body),
                    headers={"Content-Type": "application/json"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.json())
