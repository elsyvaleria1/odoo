from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged
from odoo.tests.http import JsonRpcException

from odoo.addons.pos_self_order.tests.self_order_common_test import SelfOrderCommonTest

STATUS_ROUTE = "/pos-self-order/pine-labs-fetch-payment-status/"


@tagged("post_install", "-at_install")
class TestKioskPineLabsPayment(SelfOrderCommonTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.currency_id = cls.env.ref("base.INR")

    def setUp(self):
        super().setUp()
        self.pine_labs = self.env["pos.payment.method"].create(
            {
                "name": "Pine Labs",
                "payment_method_type": "terminal",
                "use_payment_terminal": "pine_labs",
                "pine_labs_merchant": "m",
                "pine_labs_store": "s",
                "pine_labs_client": "c",
                "pine_labs_security_token": "token",
                "pine_labs_allowed_payment_mode": "all",
                "journal_id": self.bank_journal.id,
            }
        )
        self.pos_config.write(
            {
                "self_ordering_mode": "kiosk",
                "self_ordering_pay_after": "each",
                "self_ordering_service_mode": "counter",
                "payment_method_ids": [Command.link(self.pine_labs.id)],
            }
        )
        self.pos_config.with_user(self.pos_user).open_ui()
        self.pos_config.current_session_id.set_opening_control(0, "")
        # what the terminal holds, by PlutusTransactionReferenceID
        self.terminal = {}
        self.uploaded = []
        patcher = patch(
            "odoo.addons.pos_pine_labs.models.pos_payment_method.call_pine_labs",
            self._terminal,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cancel_answer = {"ResponseCode": 0, "ResponseMessage": "APPROVED"}
        self.results = []
        PosOrder = type(self.env["pos.order"])
        send = PosOrder._send_payment_result

        def record(order, payment_result):
            self.results.append(payment_result)
            return send(order, payment_result)

        result_patcher = patch.object(PosOrder, "_send_payment_result", record)
        result_patcher.start()
        self.addCleanup(result_patcher.stop)

    def _terminal(self, payment_method, endpoint, payload):
        if endpoint == "UploadBilledTransaction":
            self.uploaded.append(payload)
            plutus = 1000 + len(self.terminal)
            self.terminal[plutus] = {
                "ResponseCode": 1001,
                "ResponseMessage": "TXN UPLOADED",
                "PlutusTransactionReferenceID": plutus,
                "amount": payload["Amount"],
            }
            return {
                "ResponseCode": 0,
                "ResponseMessage": "APPROVED",
                "PlutusTransactionReferenceID": plutus,
            }
        if endpoint == "GetCloudBasedTxnStatus":
            return dict(self.terminal[int(payload["PlutusTransactionReferenceID"])])
        return self.cancel_answer

    def _approve(self, plutus, log_id, amount=None):
        self.terminal[plutus].update(
            ResponseCode=0,
            ResponseMessage="TXN APPROVED",
            TransactionData=[
                {"Tag": "TransactionLogId", "Value": log_id},
                {
                    "Tag": "Amount",
                    "Value": str(
                        self.terminal[plutus]["amount"] if amount is None else amount
                    ),
                },
            ],
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
        return self.pine_labs._payment_request_from_kiosk(order)[
            "plutusTransactionReferenceID"
        ]

    def _cancel(self, order):
        result = self.call_jsonrpc(
            "/pos-self-order/pine-labs-cancel-transaction/",
            {
                "access_token": self.pos_config.self_ordering_access_token,
                "order_id": order.id,
                "payment_data": {},
                "payment_method_id": self.pine_labs.id,
            },
        )
        self.env.invalidate_all()
        return result

    def _poll(self, order, plutus):
        result = self.call_jsonrpc(
            STATUS_ROUTE,
            {
                "access_token": self.pos_config.self_ordering_access_token,
                "order_id": order.id,
                "payment_data": {
                    "plutusTransactionReferenceID": plutus,
                    "payment_ref_no": "x",
                },
                "payment_method_id": self.pine_labs.id,
            },
        )
        self.env.invalidate_all()
        return result

    def test_the_amount_is_sent_in_whole_paisa(self):
        self._request(self._order(19.99))

        self.assertEqual(self.uploaded[0]["Amount"], 1999)
        self.assertIsInstance(self.uploaded[0]["Amount"], int)

    def test_a_half_paisa_rounds_up(self):
        order = self._order(10)
        order.amount_total = 10.005

        self.assertEqual(self.pine_labs._pine_labs_paisa(order), 1001)

    def test_its_own_transaction_pays_the_order_once(self):
        order = self._order(500)
        plutus = self._request(order)
        self._approve(plutus, "LOG-1")

        self._poll(order, plutus)
        self._poll(order, plutus)

        self.assertEqual(order.state, "paid")
        self.assertEqual(order.payment_ids.mapped("transaction_id"), ["LOG-1"])

    def test_another_orders_transaction_pays_nothing(self):
        paid, target = self._order(500), self._order(700)
        paid_plutus = self._request(paid)
        self._approve(paid_plutus, "LOG-1")
        self._poll(paid, paid_plutus)
        self._request(target)

        self._poll(target, paid_plutus)

        self.assertEqual(target.state, "draft")
        self.assertFalse(target.payment_ids)

    def test_an_order_never_sent_to_the_terminal_cannot_be_polled(self):
        paid, target = self._order(500), self._order(700)
        paid_plutus = self._request(paid)
        self._approve(paid_plutus, "LOG-1")

        with self.assertRaises(JsonRpcException):
            self._poll(target, paid_plutus)

        self.assertEqual(target.state, "draft")

    def test_a_transaction_for_another_amount_pays_nothing(self):
        order = self._order(500)
        plutus = self._request(order)
        self._approve(plutus, "LOG-1", amount=100)

        result = self._poll(order, plutus)

        self.assertIn("error", result)
        self.assertEqual(order.state, "draft")

    def test_a_transaction_id_pays_one_order_only(self):
        paid, target = self._order(500), self._order(500)
        paid_plutus = self._request(paid)
        self._approve(paid_plutus, "LOG-1")
        self._poll(paid, paid_plutus)
        plutus = self._request(target)
        self._approve(plutus, "LOG-1")

        result = self._poll(target, plutus)

        self.assertIn("error", result)
        self.assertEqual(target.state, "draft")

    def test_an_error_status_is_no_failure(self):
        order = self._order(500)
        plutus = self._request(order)
        self.terminal[plutus] = {"ResponseCode": 1, "ResponseMessage": "TXN NOT FOUND"}

        result = self._poll(order, plutus)

        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(self.results, [])
        self.assertFalse(order.kiosk_payment_to_verify_method_id)

    def test_a_cancelled_transaction_lets_the_customer_pay_again(self):
        order = self._order(500)
        self._request(order)

        result = self._cancel(order)

        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(self.results, ["fail"])

    def test_giving_up_on_an_unknown_outcome_holds_the_order(self):
        order = self._order(500)
        self._request(order)
        self.cancel_answer = {"ResponseCode": 1, "ResponseMessage": "TXN IN PROGRESS"}

        result = self._cancel(order)

        self.assertEqual(result["outcome"], "unverified")
        self.assertEqual(self.results, ["unverified"])
        self.assertEqual(order.kiosk_payment_to_verify_method_id, self.pine_labs)
