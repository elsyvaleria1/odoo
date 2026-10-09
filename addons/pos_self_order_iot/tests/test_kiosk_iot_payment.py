import odoo.tests
from odoo import Command
from odoo.tests.http import JsonRpcException

from odoo.addons.iot.tests.common import IotCommonTest
from odoo.addons.pos_self_order.tests.self_order_common_test import SelfOrderCommonTest

SUCCESS_ROUTE = "/pos-self-order/iot-payment-success/"


@odoo.tests.tagged("post_install", "-at_install")
class TestKioskIoTPayment(IotCommonTest, SelfOrderCommonTest):
    def setUp(self):
        super().setUp()
        terminal = (
            self.env["iot.device"]
            .sudo()
            .create(
                {
                    "name": "Payment Terminal",
                    "identifier": "terminal_identifier",
                    "iot_id": self.shop_iot_box.id,
                    "type": "payment",
                    "connection": "network",
                    "connection_state": "connected",
                }
            )
        )
        self.terminal_method = self.env["pos.payment.method"].create(
            {
                "name": "IoT Terminal",
                "journal_id": self.bank_journal.id,
                "iot_device_id": terminal.id,
            }
        )
        self.pos_config.write(
            {
                "self_ordering_mode": "kiosk",
                "self_ordering_pay_after": "each",
                "self_ordering_service_mode": "counter",
                "payment_method_ids": [Command.link(self.terminal_method.id)],
            }
        )
        self.pos_config.with_user(self.pos_user).open_ui()
        self.pos_config.current_session_id.set_opening_control(0, "")

    def _order(self):
        order = self.env["pos.order"].create(
            {
                "session_id": self.pos_config.current_session_id.id,
                "amount_tax": 0,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_return": 0,
                "lines": [
                    Command.create(
                        {
                            "product_id": self.cola.id,
                            "qty": 1,
                            "price_unit": 10,
                            "price_subtotal": 10,
                            "price_subtotal_incl": 10,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        order._recompute_amounts()
        return order

    def _approve(self, order, method, transaction_id):
        try:
            return self.call_jsonrpc(
                SUCCESS_ROUTE,
                {
                    "access_token": self.pos_config.self_ordering_access_token,
                    "order_id": order.id,
                    "payment_method_id": method.id,
                    "payment_info": {
                        "Card": "VISA",
                        "PaymentTransactionID": transaction_id,
                        "Ticket": "",
                    },
                },
            )
        except JsonRpcException:
            return "refused"
        finally:
            self.env.invalidate_all()

    def test_its_terminal_pays_the_order_once(self):
        order = self._order()

        self._approve(order, self.terminal_method, 41)
        self._approve(order, self.terminal_method, 41)

        self.assertEqual(order.state, "paid")
        self.assertEqual(order.payment_ids.mapped("transaction_id"), ["41"])

    def test_a_method_without_a_terminal_pays_nothing(self):
        order = self._order()

        self.assertEqual(self._approve(order, self.bank_payment_method, 41), "refused")

        self.assertEqual(order.state, "draft")

    def test_a_transaction_id_pays_one_order_only(self):
        paid, target = self._order(), self._order()
        self._approve(paid, self.terminal_method, 41)

        result = self._approve(target, self.terminal_method, 41)

        self.assertIn("error", result or {})
        self.assertEqual(target.state, "draft")
        self.assertFalse(target.payment_ids)


@odoo.tests.tagged("post_install", "-at_install")
class TestKioskIoTRelay(TestKioskIoTPayment):
    """The IoT channel is the whole database's: only a kiosk reaches it, and
    only for the boxes of the devices its point of sale uses."""

    def setUp(self):
        super().setUp()
        self.iot_websocket_messages = []
        self.other_box = (
            self.env["iot.box"]
            .sudo()
            .create(
                {
                    "name": "Back office",
                    "identifier": "other_iot_box",
                    "ip": "10.10.10.11",
                    "version": "25.07",
                }
            )
        )

    def _relay(self, identifier):
        return self.call_jsonrpc(
            "/pos-self-order/iot-box-websocket-channel",
            {
                "access_token": self.pos_config.self_ordering_access_token,
                "message": {
                    "iot_identifiers": [identifier],
                    "iot_identifier": identifier,
                    "action": "probe",
                },
                "message_type": "iot_action",
            },
        )

    def _box_data(self, box):
        return self.call_jsonrpc(
            "/pos-self-order/get-iot-box-data/",
            {
                "access_token": self.pos_config.self_ordering_access_token,
                "iot_box_id": box.id,
            },
        )

    def test_a_mobile_qr_code_reaches_no_iot_box(self):
        self.pos_config.self_ordering_mode = "mobile"

        channel = self._relay(self.shop_iot_box.identifier)

        self.assertFalse(channel)
        self.assertEqual(self.iot_websocket_messages, [])

    def test_a_kiosk_reaches_only_its_own_boxes(self):
        with self.assertRaises(JsonRpcException):
            self._relay(self.other_box.identifier)
        self.assertEqual(self.iot_websocket_messages, [])

        channel = self._relay(self.shop_iot_box.identifier)

        self.assertEqual(channel, "mock_iot_channel")
        self.assertEqual(len(self.iot_websocket_messages), 1)

    def test_a_kiosk_reads_only_its_own_boxes(self):
        self.assertIn("error", self._box_data(self.other_box))
        self.assertEqual(
            self._box_data(self.shop_iot_box)[0]["identifier"],
            self.shop_iot_box.identifier,
        )
