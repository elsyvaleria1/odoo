from unittest.mock import patch
from urllib.parse import parse_qs

from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon
from odoo.addons.pos_adyen.models.pos_payment_method import PosPaymentMethod

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
            method.sudo().adyen_pending_request = json_dumps(
                {
                    "sale_id": "sale",
                    "service_id": "service",
                    "transaction_id": transaction_id,
                    "currency": "USD",
                    "amount": 1.0,
                    "self_order_id": False,
                }
            )
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


@tagged("post_install", "-at_install")
class TestAdyenPaymentRoundTrip(TestPointOfSaleHttpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adyen = cls.env["pos.payment.method"].create(
            {
                "name": "Adyen round trip",
                "use_payment_terminal": "adyen",
                "adyen_api_key": "my_adyen_api_key",
                "adyen_terminal_identifier": "P400Plus-roundtrip",
                "payment_method_type": "terminal",
                "journal_id": cls.bank_journal.id,
            }
        )
        cls.main_pos_config.write({"payment_method_ids": [Command.link(cls.adyen.id)]})
        cls.main_pos_config.with_user(cls.pos_user).open_ui()
        cls.currency_name = cls.main_pos_config.currency_id.name

    def _payment_request(
        self, amount=25.0, acquirer_data=None, service_id="1234567890"
    ):
        session = self.main_pos_config.current_session_id
        data = {
            "SaleToPOIRequest": {
                "MessageHeader": {
                    "ProtocolVersion": "3.0",
                    "MessageClass": "Service",
                    "MessageType": "Request",
                    "MessageCategory": "Payment",
                    "SaleID": f"Shop (ID: {self.main_pos_config.id})",
                    "ServiceID": service_id,
                    "POIID": "P400Plus-roundtrip",
                },
                "PaymentRequest": {
                    "SaleData": {
                        "SaleTransactionID": {
                            "TransactionID": f"order-uuid--{session.id}",
                            "TimeStamp": "2026-10-09T10:00:00+00:00",
                        },
                    },
                    "PaymentTransaction": {
                        "AmountsReq": {
                            "Currency": self.currency_name,
                            "RequestedAmount": amount,
                        },
                    },
                },
            },
        }
        if acquirer_data:
            data["SaleToPOIRequest"]["PaymentRequest"]["SaleData"][
                "SaleToAcquirerData"
            ] = acquirer_data
        sent = []
        with patch.object(
            PosPaymentMethod,
            "_proxy_adyen_request_direct",
            lambda method, request_data, operation: sent.append(request_data) or True,
        ):
            self.adyen.with_user(self.pos_user).proxy_adyen_request(data)
        return sent[0]["SaleToPOIRequest"]

    def _notification(self, request, result="Success", amount=25.0):
        sale_data = request["PaymentRequest"]["SaleData"]
        pos_hmac = parse_qs(sale_data["SaleToAcquirerData"])["metadata.pos_hmac"][0]
        return {
            "SaleToPOIResponse": {
                "MessageHeader": {
                    **PAYMENT_HEADER,
                    "SaleID": request["MessageHeader"]["SaleID"],
                    "ServiceID": request["MessageHeader"]["ServiceID"],
                    "POIID": request["MessageHeader"]["POIID"],
                },
                "PaymentResponse": {
                    "Response": {
                        "Result": result,
                        "AdditionalResponse": "pspReference=PSP1&cardType=visa"
                        f"&metadata.pos_hmac={pos_hmac}",
                    },
                    "SaleData": {"SaleTransactionID": sale_data["SaleTransactionID"]},
                    "PaymentResult": {
                        "AmountsResp": {
                            "AuthorizedAmount": amount,
                            "Currency": self.currency_name,
                        },
                        "PaymentInstrumentData": {"CardData": {"PaymentBrand": "visa"}},
                    },
                    "PaymentReceipt": [],
                },
            }
        }

    def _adyen_reports(self, notification, result, amount):
        response = notification["SaleToPOIResponse"]["PaymentResponse"]

        def proxy(method, request_data, operation):
            self.assertEqual(operation, "transaction_status")
            return {
                "SaleToPOIResponse": {
                    "TransactionStatusResponse": {
                        "Response": {"Result": "Success"},
                        "RepeatedMessageResponse": {
                            "RepeatedResponseMessageBody": {
                                "PaymentResponse": {
                                    "Response": {"Result": result},
                                    "SaleData": response["SaleData"],
                                    "PaymentResult": {
                                        "AmountsResp": {
                                            "AuthorizedAmount": amount,
                                            "Currency": self.currency_name,
                                        }
                                    },
                                }
                            }
                        },
                    }
                }
            }

        return patch.object(PosPaymentMethod, "_proxy_adyen_request_direct", proxy)

    def _post(self, notification):
        return self.url_open(
            "/pos_adyen/notification",
            data=json_dumps(notification),
            headers={"Content-Type": "application/json"},
        )

    def _latest_result(self):
        latest = self.adyen.sudo().adyen_latest_response
        return (
            latest
            and json_loads(latest)["SaleToPOIResponse"]["PaymentResponse"]["Response"][
                "Result"
            ]
        )

    def test_an_approval_adyen_confirms_reaches_the_pos(self):
        notification = self._notification(self._payment_request())
        with self._adyen_reports(notification, "Success", 25.0):
            response = self._post(notification)
        self.assertEqual(response.json(), "[accepted]")
        self.assertEqual(self._latest_result(), "Success")
        self.assertFalse(self.adyen.sudo().adyen_pending_request)

    @mute_logger("odoo.addons.pos_adyen.models.pos_payment_method")
    def test_a_failure_rewritten_as_an_approval_stays_a_failure(self):
        notification = self._notification(self._payment_request())
        with self._adyen_reports(notification, "Failure", 25.0):
            self._post(notification)
        self.assertEqual(self._latest_result(), "Failure")

    @mute_logger(
        "odoo.addons.integration.models.integration_receiver",
        "odoo.addons.pos_adyen.models.pos_payment_method",
    )
    def test_an_approval_for_another_amount_is_refused(self):
        notification = self._notification(self._payment_request(25.0), amount=1.0)
        with self._adyen_reports(notification, "Success", 1.0):
            response = self._post(notification)
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(self._latest_result())

    @mute_logger("odoo.addons.integration.models.integration_receiver")
    def test_a_notification_is_accepted_once(self):
        notification = self._notification(self._payment_request())
        with self._adyen_reports(notification, "Success", 25.0):
            self.assertEqual(self._post(notification).json(), "[accepted]")
            self.adyen.sudo().adyen_latest_response = ""
            replay = self._post(notification)
        self.assertNotEqual(replay.status_code, 200)
        self.assertFalse(self._latest_result())

    @mute_logger("odoo.addons.integration.models.integration_receiver")
    def test_a_notification_for_a_superseded_request_is_refused(self):
        superseded = self._notification(self._payment_request())
        self._payment_request(service_id="0987654321")
        with self._adyen_reports(superseded, "Success", 25.0):
            response = self._post(superseded)
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(self._latest_result())

    def test_the_signature_is_not_logged(self):
        with self.assertLogs("odoo.addons.pos_adyen", "INFO") as logs:
            request = self._payment_request()
            notification = self._notification(request)
            with self._adyen_reports(notification, "Success", 25.0):
                self._post(notification)
        pos_hmac = parse_qs(
            request["PaymentRequest"]["SaleData"]["SaleToAcquirerData"]
        )["metadata.pos_hmac"][0]
        self.assertTrue(logs.output)
        self.assertNotIn(pos_hmac, "\n".join(logs.output))
