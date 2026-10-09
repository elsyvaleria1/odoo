import contextlib
from unittest.mock import patch

import odoo.tests
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import Command
from odoo.tests.http import JsonRpcException

from odoo.addons.pos_self_order.tests.self_order_common_test import SelfOrderCommonTest


@odoo.tests.tagged("post_install", "-at_install")
class TestSelfOrderKioskStripe(SelfOrderCommonTest):
    def setUp(self):
        super().setUp()
        self.pos_config.write(
            {
                "self_ordering_mode": "kiosk",
                "self_ordering_pay_after": "each",
                "self_ordering_service_mode": "table",
            }
        )
        self.stripe = self.env["pos.payment.method"].create(
            {
                "name": "Stripe",
                "use_payment_terminal": "stripe",
            }
        )

        self.env["pos.payment.method"].create(
            {
                "name": "Stripe 2",
                "use_payment_terminal": "stripe",
            }
        )

        self.pos_config.write(
            {
                "payment_method_ids": [Command.set([self.stripe.id])],
                "self_ordering_access_token": "access_token",
            }
        )

        self.headers = {
            "Content-Type": "application/json",
        }

    def _build_payload(self, params=None):
        """
        Helper to properly build jsonrpc payload
        """
        return {
            "jsonrpc": "2.0",
            "method": "call",
            "id": 0,
            "params": params or {},
        }

    def test_self_order_kiosk_stripe(self):
        res = self.pos_config.load_self_data()
        pm = res.get("pos.payment.method", [])
        self.assertEqual(len(pm), 1, "Only one payment method should be loaded")
        self.assertEqual(
            pm[0]["name"], "Stripe", "The loaded payment method should be Stripe"
        )

    def test_get_stripe_creditentials(self):
        """This test make sure the get_stripe_creditentials method does not crash because of `_get_pos_config_and_table` method"""
        self.pos_config.open_ui()
        stripe_connection_token = "odoo.addons.pos_stripe.models.pos_payment_method.PosPaymentMethod.stripe_connection_token"
        connection_token = {
            "object": "terminal.connection_token",
            "secret": "pst_test_YWNjdF8xUXR003cnRmp4b",
        }
        with patch(stripe_connection_token, return_value=connection_token):
            payload = self._build_payload(
                {"access_token": "access_token", "payment_method_id": self.stripe.id}
            )
            response = self.url_open(
                "/pos-self-order/stripe-connection-token",
                data=json_dumps(payload),
                headers=self.headers,
                timeout=60000,
            )
            json_response = json_loads(response.text)
            self.assertTrue(
                json_response.get("result").get("object"), "terminal.connection_token"
            )

    def test_stripe_capture_payment(self):
        """This test make sure the stripe_capture_payment method does not crash because of `_get_pos_config_and_table` method"""
        self.pos_config.self_ordering_access_token = "access_token"
        self.pos_config.open_ui()
        stripe_capture_payment = "odoo.addons.pos_stripe.models.pos_payment_method.PosPaymentMethod.stripe_capture_payment"
        order = self.env["pos.order"].create(
            {
                "company_id": self.env.company.id,
                "session_id": self.pos_config.current_session_id.id,
                "lines": [
                    Command.create(
                        {
                            "product_id": self.fanta.id,
                            "price_unit": 10,
                            "discount": 0,
                            "qty": 1,
                            "price_subtotal": 10,
                            "price_subtotal_incl": 10,
                        }
                    )
                ],
                "amount_paid": 10.0,
                "amount_total": 10.0,
                "amount_tax": 0.0,
                "amount_return": 0.0,
                "to_invoice": True,
                "last_order_preparation_change": "{}",
            }
        )
        order._set_kiosk_terminal_request(False, "1")
        with patch(
            stripe_capture_payment,
            return_value={
                "id": "1",
                "status": "succeeded",
                "amount": 1000,
                "currency": self.env.company.currency_id.name.lower(),
            },
        ):
            payload = self._build_payload(
                {
                    "access_token": "access_token",
                    "order_access_token": order.access_token,
                    "payment_intent_id": "1",
                    "payment_method_id": self.stripe.id,
                }
            )
            self.url_open(
                "/pos-self-order/stripe-capture-payment",
                data=json_dumps(payload),
                headers=self.headers,
                timeout=60000,
            )
            self.assertTrue(order.state == "paid", "The order should be paid")

    def test_kiosk_without_payment_terminal(self):
        """Verify that kiosk should not ask for payment when valid payment method is not configured."""
        invalid_pm = (
            self.bank_payment_method
        )  # 'Bank' is not a valid payment method for kiosk mode
        self.pos_config.write(
            {
                "self_ordering_mode": "kiosk",
                "self_ordering_service_mode": "counter",
                "use_presets": False,
                "payment_method_ids": [(6, 0, invalid_pm.ids)],
            }
        )
        self.pos_config.with_user(self.pos_user).open_ui()
        self.pos_config.current_session_id.set_opening_control(0, "")
        self_route = self.pos_config._get_self_order_route()
        self.start_tour(self_route, "test_kiosk_without_payment_terminal")

        order = self.pos_config.current_session_id.order_ids[0]
        self.assertEqual(order.state, "draft", "The order should be draft")
        self.assertFalse(
            order.payment_ids, "No payments should be registered for the order"
        )


@odoo.tests.tagged("post_install", "-at_install")
class TestSelfOrderKioskStripeCapture(SelfOrderCommonTest):
    CAPTURE = "odoo.addons.pos_stripe.models.pos_payment_method.PosPaymentMethod.stripe_capture_payment"
    INTENT = "odoo.addons.pos_stripe.models.pos_payment_method.PosPaymentMethod.stripe_payment_intent"

    def setUp(self):
        super().setUp()
        self.stripe = self.env["pos.payment.method"].create(
            {
                "name": "Stripe",
                "journal_id": self.bank_journal.id,
                "use_payment_terminal": "stripe",
            }
        )
        self.pos_config.write(
            {
                "self_ordering_mode": "kiosk",
                "self_ordering_pay_after": "each",
                "self_ordering_service_mode": "counter",
                "payment_method_ids": [Command.set([self.stripe.id])],
            }
        )
        self.pos_config.with_user(self.pos_user).open_ui()
        self.pos_config.current_session_id.set_opening_control(0, "")
        self.currency = self.env.company.currency_id.name.lower()

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
                            "product_id": self.fanta.id,
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

    def _capture(self, order, intent_id, answer):
        with (
            patch(self.CAPTURE, return_value=answer) as capture,
            contextlib.suppress(JsonRpcException),
        ):
            self.call_jsonrpc(
                "/pos-self-order/stripe-capture-payment/",
                {
                    "access_token": self.pos_config.self_ordering_access_token,
                    "order_access_token": order.access_token,
                    "payment_intent_id": intent_id,
                    "payment_method_id": self.stripe.id,
                },
            )
        self.env.invalidate_all()
        return capture

    def _succeeded(self, intent_id, amount=1000, currency=None):
        return {
            "id": intent_id,
            "status": "succeeded",
            "amount": amount,
            "currency": currency or self.currency,
        }

    def test_the_kiosk_request_records_its_intent(self):
        order = self._order()
        with patch(self.INTENT, return_value={"id": "pi_1", "client_secret": "s"}):
            self.stripe._payment_request_from_kiosk(order)

        self.assertEqual(order.kiosk_terminal_request, "pi_1")

    def test_another_orders_intent_is_not_captured_for_this_order(self):
        paid, target = self._order(), self._order()
        paid._set_kiosk_terminal_request(False, "pi_paid")
        target._set_kiosk_terminal_request(False, "pi_target")

        capture = self._capture(target, "pi_paid", self._succeeded("pi_paid"))

        capture.assert_not_called()
        self.assertEqual(target.state, "draft")
        self.assertFalse(target.payment_ids)

    def test_its_own_intent_pays_it_once(self):
        order = self._order()
        order._set_kiosk_terminal_request(False, "pi_1")

        self._capture(order, "pi_1", self._succeeded("pi_1"))
        self._capture(order, "pi_1", self._succeeded("pi_1"))

        self.assertEqual(order.state, "paid")
        self.assertEqual(order.payment_ids.mapped("transaction_id"), ["pi_1"])

    def test_a_capture_in_another_currency_pays_nothing(self):
        order = self._order()
        order._set_kiosk_terminal_request(False, "pi_1")

        self._capture(order, "pi_1", self._succeeded("pi_1", currency="xyz"))

        self.assertEqual(order.state, "draft")
        self.assertFalse(order.payment_ids)
