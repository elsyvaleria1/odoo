from unittest.mock import patch
from urllib.parse import parse_qsl, urlencode

import requests

import odoo.tests
from odoo import Command
from odoo.exceptions import UserError
from odoo.libs.json import dumps as json_dumps
from odoo.tools import mute_logger

from odoo.addons.pos_adyen.models.pos_payment_method import PosPaymentMethod
from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController
from odoo.addons.pos_self_order.tests.self_order_common_test import SelfOrderCommonTest


@odoo.tests.tagged("post_install", "-at_install")
class TestKioskAdyenNotification(SelfOrderCommonTest):
    def setUp(self):
        super().setUp()
        self.adyen = self.env["pos.payment.method"].create(
            {
                "name": "Adyen kiosk",
                "use_payment_terminal": "adyen",
                "adyen_api_key": "my_adyen_api_key",
                "adyen_terminal_identifier": "P400Plus-kiosk",
                "payment_method_type": "terminal",
                "journal_id": self.bank_journal.id,
            }
        )
        self.pos_config.write(
            {
                "self_ordering_mode": "kiosk",
                "self_ordering_pay_after": "each",
                "payment_method_ids": [Command.set(self.adyen.ids)],
            }
        )
        self.pos_config.open_ui()
        self.order = self._order(10.0)
        self.other_order = self._order(300.0)

    def _order(self, price):
        return self.env["pos.order"].create(
            {
                "session_id": self.pos_config.current_session_id.id,
                "lines": [
                    Command.create(
                        {
                            "product_id": self.fanta.id,
                            "qty": 1,
                            "price_unit": price,
                            "price_subtotal": price,
                            "price_subtotal_incl": price,
                        }
                    )
                ],
                "amount_paid": 0.0,
                "amount_total": price,
                "amount_tax": 0.0,
                "amount_return": 0.0,
            }
        )

    def _kiosk_request(self, order):
        sent = []
        with patch.object(
            PosPaymentMethod,
            "_proxy_adyen_request_direct",
            lambda method, data, operation: sent.append(data) or True,
        ):
            self.assertTrue(self.adyen.sudo()._payment_request_from_kiosk(order))
        return sent[0]["SaleToPOIRequest"]

    def _notification(self, request, self_order_id=None):
        sale_data = request["PaymentRequest"]["SaleData"]
        metadata = dict(parse_qsl(sale_data["SaleToAcquirerData"]))
        if self_order_id:
            metadata["metadata.self_order_id"] = str(self_order_id)
        amount = request["PaymentRequest"]["PaymentTransaction"]["AmountsReq"][
            "RequestedAmount"
        ]
        return {
            "SaleToPOIResponse": {
                "MessageHeader": {
                    "ProtocolVersion": "3.0",
                    "MessageClass": "Service",
                    "MessageType": "Response",
                    "MessageCategory": "Payment",
                    "SaleID": request["MessageHeader"]["SaleID"],
                    "ServiceID": request["MessageHeader"]["ServiceID"],
                    "POIID": request["MessageHeader"]["POIID"],
                },
                "PaymentResponse": {
                    "Response": {
                        "Result": "Success",
                        "AdditionalResponse": urlencode(
                            {"pspReference": "PSP1", **metadata}
                        ),
                    },
                    "SaleData": {"SaleTransactionID": sale_data["SaleTransactionID"]},
                    "PaymentResult": {
                        "AmountsResp": {"AuthorizedAmount": amount},
                        "PaymentInstrumentData": {"CardData": {"PaymentBrand": "visa"}},
                    },
                    "PaymentReceipt": [],
                },
            }
        }

    def _adyen_reports(self, notification, result):
        response = notification["SaleToPOIResponse"]["PaymentResponse"]
        status = {
            "SaleToPOIResponse": {
                "TransactionStatusResponse": {
                    "Response": {"Result": "Success"},
                    "RepeatedMessageResponse": {
                        "RepeatedResponseMessageBody": {
                            "PaymentResponse": {
                                "Response": {"Result": result},
                                "SaleData": response["SaleData"],
                                "PaymentResult": response["PaymentResult"],
                            }
                        }
                    },
                }
            }
        }
        return patch.object(
            PosPaymentMethod,
            "_proxy_adyen_request_direct",
            lambda method, data, operation: status,
        )

    def _post(self, notification):
        return self.url_open(
            "/pos_adyen/notification",
            data=json_dumps(notification),
            headers={"Content-Type": "application/json"},
        )

    def _settle(self, notification, reply_patch):
        self._post(notification)
        self.assertEqual(self.order.state, "draft")
        with (
            reply_patch,
            patch.object(
                type(self.env["pos.order"]), "_send_payment_result", autospec=True
            ) as sent,
        ):
            self.env["pos.payment.method"].sudo()._cron_confirm_adyen_payments()
        return [call.args[1] for call in sent.call_args_list]

    def test_a_notification_pays_the_order_its_request_was_made_for(self):
        notification = self._notification(
            self._kiosk_request(self.order), self_order_id=self.other_order.id
        )
        sent = self._settle(notification, self._adyen_reports(notification, "Success"))
        self.assertEqual(sent, ["Success"])
        self.assertEqual(self.order.state, "paid")
        self.assertEqual(self.other_order.state, "draft")
        self.assertFalse(self.other_order.payment_ids)

    def test_a_failure_adyen_reports_pays_nothing(self):
        notification = self._notification(self._kiosk_request(self.order))
        sent = self._settle(notification, self._adyen_reports(notification, "Failure"))
        self.assertEqual(sent, ["Failure"])
        self.assertEqual(self.order.state, "draft")
        self.assertFalse(self.order.payment_ids)

    @mute_logger(
        "odoo.addons.pos_adyen.models.pos_payment_method",
        "odoo.addons.pos_self_order_adyen.models.pos_payment_method",
    )
    def _hold_unconfirmed(self):
        notification = self._notification(self._kiosk_request(self.order))
        unreachable = patch.object(
            PosPaymentMethod,
            "_proxy_adyen_request_direct",
            side_effect=requests.ConnectionError("timed out"),
        )
        return self._settle(notification, unreachable)

    def _kiosk_pays(self):
        requested = []
        with (
            patch.object(
                PosSelfOrderController,
                "process_order",
                lambda controller, *args: {"pos.order": [{"id": self.order.id}]},
            ),
            patch.object(
                type(self.env["pos.payment.method"]),
                "_payment_request_from_kiosk",
                lambda method, order: requested.append(order.id) or True,
            ),
        ):
            response = self.url_open(
                f"/kiosk/payment/{self.pos_config.id}/kiosk",
                json_dumps(
                    {
                        "jsonrpc": "2.0",
                        "params": {
                            "order": {},
                            "payment_method_id": self.adyen.id,
                            "access_token": self.pos_config.access_token,
                        },
                    }
                ),
                method="POST",
                headers={"Content-Type": "application/json"},
            ).json()
        return requested, response

    def test_an_approval_adyen_cannot_confirm_holds_the_order_for_staff(self):
        self.assertEqual(self._hold_unconfirmed(), ["unverified"])
        self.assertEqual(self.order.state, "draft")
        self.assertFalse(self.order.payment_ids)
        self.assertEqual(self.order.kiosk_payment_to_verify, "PSP1")
        self.assertEqual(self.order.kiosk_payment_to_verify_method_id, self.adyen)
        self.assertEqual(self.order.kiosk_payment_to_verify_amount, 10.0)

    @mute_logger("odoo.http")
    def test_the_kiosk_takes_no_new_payment_while_the_order_is_verified(self):
        self._hold_unconfirmed()
        requested, response = self._kiosk_pays()
        self.assertEqual(requested, [])
        self.assertIn("being verified", response["error"]["data"]["message"])

    def test_staff_record_the_payment_the_terminal_approved(self):
        self._hold_unconfirmed()
        with (
            patch.object(
                type(self.env["pos.order"]), "_send_payment_result", autospec=True
            ) as sent,
            patch.object(
                PosPaymentMethod,
                "_proxy_adyen_request_direct",
                lambda method, data, operation: True,
            ),
        ):
            self.order.with_user(self.pos_user).action_kiosk_payment_approved()
        self.assertEqual([call.args[1] for call in sent.call_args_list], ["Success"])
        self.assertEqual(self.order.state, "paid")
        self.assertEqual(self.order.payment_ids.transaction_id, "PSP1")
        self.assertEqual(self.order.payment_ids.payment_method_id, self.adyen)
        self.assertFalse(self.order.kiosk_payment_to_verify_method_id)

    def test_staff_let_the_customer_pay_again_when_the_terminal_did_not_approve(self):
        self._hold_unconfirmed()
        with patch.object(
            type(self.env["pos.order"]), "_send_payment_result", autospec=True
        ) as sent:
            self.order.with_user(self.pos_user).action_kiosk_payment_not_approved()
        self.assertEqual([call.args[1] for call in sent.call_args_list], ["fail"])
        self.assertEqual(self.order.state, "draft")
        self.assertFalse(self.order.payment_ids)
        requested, response = self._kiosk_pays()
        self.assertEqual(requested, [self.order.id])
        self.assertNotIn("error", response)

    def test_the_cashier_cannot_name_the_kiosk_order(self):
        data = {
            "SaleToPOIRequest": {
                "MessageHeader": {
                    "ProtocolVersion": "3.0",
                    "MessageClass": "Service",
                    "MessageType": "Request",
                    "MessageCategory": "Payment",
                    "SaleID": "Shop (ID: 1)",
                    "ServiceID": "1234567890",
                    "POIID": "P400Plus-kiosk",
                },
                "PaymentRequest": {
                    "SaleData": {
                        "SaleTransactionID": {
                            "TransactionID": "order-uuid--1",
                            "TimeStamp": "2026-10-09T10:00:00+00:00",
                        },
                        "SaleToAcquirerData": "metadata.self_order_id="
                        f"{self.other_order.id}",
                    },
                    "PaymentTransaction": {
                        "AmountsReq": {"Currency": "USD", "RequestedAmount": 1.0},
                    },
                },
            },
        }
        with (
            patch.object(
                PosPaymentMethod,
                "_proxy_adyen_request_direct",
                lambda method, data, operation: True,
            ),
            self.assertRaises(UserError),
        ):
            self.adyen.with_user(self.pos_user).proxy_adyen_request(data)
