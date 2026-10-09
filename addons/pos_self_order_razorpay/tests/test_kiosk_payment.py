from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged
from odoo.tests.http import JsonRpcException

from odoo.addons.pos_razorpay.models.razorpay_pos_request import RazorpayPosRequest
from odoo.addons.pos_self_order.tests.self_order_common_test import SelfOrderCommonTest

STATUS_ROUTE = "/pos-self-order/razorpay-fetch-payment-status/"


@tagged("post_install", "-at_install")
class TestKioskRazorpayPayment(SelfOrderCommonTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.currency_id = cls.env.ref("base.INR")

    def setUp(self):
        super().setUp()
        self.razorpay = self.env["pos.payment.method"].create(
            {
                "name": "Razorpay",
                "payment_method_type": "terminal",
                "use_payment_terminal": "razorpay",
                "razorpay_tid": "tid",
                "razorpay_username": "user",
                "razorpay_api_key": "key",
                "razorpay_allowed_payment_modes": "card",
                "journal_id": self.bank_journal.id,
            }
        )
        self.pos_config.write(
            {
                "self_ordering_mode": "kiosk",
                "self_ordering_pay_after": "each",
                "self_ordering_service_mode": "counter",
                "payment_method_ids": [Command.link(self.razorpay.id)],
            }
        )
        self.pos_config.with_user(self.pos_user).open_ui()
        self.pos_config.current_session_id.set_opening_control(0, "")
        # what the terminal holds, by p2pRequestId
        self.terminal = {}
        patcher = patch.object(RazorpayPosRequest, "_call_razorpay", self._terminal)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cancel_answer = {"success": True}
        self.results = []
        PosOrder = type(self.env["pos.order"])
        send = PosOrder._send_payment_result

        def record(order, payment_result):
            self.results.append(payment_result)
            return send(order, payment_result)

        patcher = patch.object(PosOrder, "_send_payment_result", record)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _terminal(self, endpoint, payload):
        if endpoint == "pay":
            p2p = f"P2P-{len(self.terminal) + 1}"
            self.terminal[p2p] = {
                "success": True,
                "status": "PENDING",
                "messageCode": "P2P_DEVICE_SENT",
                "p2pRequestId": p2p,
                "externalRefNumber": payload["externalRefNumber"],
                "amount": payload["amount"],
            }
            return {"success": True, "p2pRequestId": p2p}
        if endpoint == "status":
            return self.terminal[payload["origP2pRequestId"]]
        if endpoint == "cancel":
            return self.cancel_answer
        return {"success": True}

    def _approve(self, p2p, txn_id, **changes):
        self.terminal[p2p].update(
            status="AUTHORIZED",
            messageCode="P2P_DEVICE_TXN_DONE",
            txnId=txn_id,
            **changes,
        )

    def _order(self, price):
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
                            "price_unit": price,
                            "price_subtotal": price,
                            "price_subtotal_incl": price,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        order._recompute_amounts()
        return order

    def _request(self, order):
        return self.razorpay._payment_request_from_kiosk(order)["p2pRequestId"]

    def _cancel(self, order):
        result = self.call_jsonrpc(
            "/pos-self-order/razorpay-cancel-transaction/",
            {
                "access_token": self.pos_config.self_ordering_access_token,
                "order_id": order.id,
                "payment_data": {},
                "payment_method_id": self.razorpay.id,
            },
        )
        self.env.invalidate_all()
        return result

    def _poll(self, order, p2p):
        result = self.call_jsonrpc(
            STATUS_ROUTE,
            {
                "access_token": self.pos_config.self_ordering_access_token,
                "order_id": order.id,
                "payment_data": {"p2pRequestId": p2p},
                "payment_method_id": self.razorpay.id,
            },
        )
        self.env.invalidate_all()
        return result

    def test_its_own_transaction_pays_the_order_once(self):
        order = self._order(500)
        p2p = self._request(order)
        self._approve(p2p, "TXN-1")

        self._poll(order, p2p)
        self._poll(order, p2p)

        self.assertEqual(order.state, "paid")
        self.assertEqual(order.payment_ids.mapped("transaction_id"), ["TXN-1"])
        self.assertEqual(order.payment_ids.amount, 500)

    def test_another_orders_transaction_pays_nothing(self):
        paid, target = self._order(500), self._order(700)
        paid_p2p = self._request(paid)
        self._approve(paid_p2p, "TXN-1")
        self._poll(paid, paid_p2p)
        self._request(target)

        self._poll(target, paid_p2p)

        self.assertEqual(target.state, "draft")
        self.assertFalse(target.payment_ids)

    def test_an_order_never_sent_to_the_terminal_cannot_be_polled(self):
        paid, target = self._order(500), self._order(700)
        paid_p2p = self._request(paid)
        self._approve(paid_p2p, "TXN-1")

        with self.assertRaises(JsonRpcException):
            self._poll(target, paid_p2p)

        self.assertEqual(target.state, "draft")

    def test_a_transaction_for_another_amount_pays_nothing(self):
        order = self._order(500)
        p2p = self._request(order)
        self._approve(p2p, "TXN-1", amount=1.0)

        result = self._poll(order, p2p)

        self.assertIn("error", result)
        self.assertEqual(order.state, "draft")
        self.assertFalse(order.payment_ids)

    def test_a_transaction_id_pays_one_order_only(self):
        paid, target = self._order(500), self._order(500)
        paid_p2p = self._request(paid)
        self._approve(paid_p2p, "TXN-1")
        self._poll(paid, paid_p2p)
        p2p = self._request(target)
        self._approve(p2p, "TXN-1")

        result = self._poll(target, p2p)

        self.assertIn("error", result)
        self.assertEqual(target.state, "draft")
        self.assertFalse(target.payment_ids)

    def test_a_lost_status_answer_is_no_failure(self):
        order = self._order(500)
        p2p = self._request(order)
        self.terminal[p2p] = {
            "success": False,
            "errorCode": "EZETAP_0000000",
            "errorMessage": "upstream timeout",
        }

        result = self._poll(order, p2p)

        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(self.results, [])
        self.assertFalse(order.kiosk_payment_to_verify_method_id)

    def test_a_declined_transaction_lets_the_customer_pay_again(self):
        order = self._order(500)
        p2p = self._request(order)
        self.terminal[p2p].update(
            status="FAILED", messageCode="P2P_DEVICE_TXN_DONE", message="Declined"
        )

        result = self._poll(order, p2p)

        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(self.results, ["fail"])

    def test_a_cancelled_transaction_lets_the_customer_pay_again(self):
        order = self._order(500)
        self._request(order)

        result = self._cancel(order)

        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(self.results, ["fail"])
        self.assertFalse(order.kiosk_payment_to_verify_method_id)

    def test_giving_up_on_an_unknown_outcome_holds_the_order(self):
        order = self._order(500)
        self._request(order)
        self.cancel_answer = {
            "success": False,
            "errorCode": "EZETAP_0000999",
            "errorMessage": "device busy",
        }

        result = self._cancel(order)

        self.assertEqual(result["outcome"], "unverified")
        self.assertEqual(self.results, ["unverified"])
        self.assertEqual(order.kiosk_payment_to_verify_method_id, self.razorpay)
        self.assertEqual(order.state, "draft")

    def test_an_approval_the_device_reports_after_the_hold_pays_and_lifts_it(self):
        order = self._order(500)
        p2p = self._request(order)
        self.cancel_answer = {"success": False, "errorMessage": "device busy"}
        self._cancel(order)
        self._approve(p2p, "TXN-1")

        self._poll(order, p2p)

        self.assertEqual(order.state, "paid")
        self.assertFalse(order.kiosk_payment_to_verify_method_id)
