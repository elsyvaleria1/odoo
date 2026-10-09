from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import hash_sign

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon
from odoo.addons.pos_mollie.models.pos_payment_method import (
    WEBHOOK_SCOPE,
    PosPaymentMethod,
)


@tagged("post_install", "-at_install")
class TestMolliePaymentScope(TestPointOfSaleHttpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.method, cls.other_method = cls.env["pos.payment.method"].create(
            [
                {
                    "name": name,
                    "journal_id": cls.bank_journal.id,
                    "payment_method_type": "terminal",
                }
                for name in ("Mollie", "Other Mollie")
            ]
        )
        cls.main_pos_config.write({"payment_method_ids": [Command.link(cls.method.id)]})
        cls.main_pos_config.with_user(cls.pos_user).open_ui()
        cls.session = cls.main_pos_config.current_session_id
        cls.session.set_opening_control(0, "")

    def setUp(self):
        super().setUp()
        self.mollie_calls = []
        self.payments = {}

        def send(provider, method, endpoint, **kwargs):
            self.mollie_calls.append((method, endpoint))
            return self.payments.get(endpoint.rpartition("/")[2], {"id": "tr_new"})

        patcher = patch.object(
            type(self.env["payment.provider"]), "_send_api_request", send
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _payment(self, method_id, status="paid"):
        payload = hash_sign(
            self.env(su=True),
            WEBHOOK_SCOPE,
            {
                "payment_uuid": "uuid",
                "payment_method_id": method_id,
                "pos_session_id": 1,
            },
            expiration_hours=27,
        )
        return {
            "id": "tr_abc",
            "status": status,
            "details": {
                "cardFunding": "debit",
                "cardNumber": "1234",
                "cardLabel": "Visa",
            },
            "webhookUrl": f"https://odoo.test/pos_mollie/webhook?payload={payload}",
        }

    def _cashier(self, method=None):
        return (method or self.method).with_user(self.pos_user)

    def _poll(self, payment_id, payment_info):
        with patch.object(
            PosPaymentMethod, "_mollie_get_payment", return_value=payment_info
        ) as fetch:
            try:
                return self._cashier().mollie_get_payment_status(payment_id)
            finally:
                self.fetched = fetch.call_args_list

    def test_the_status_of_a_payment_this_method_requested_is_returned(self):
        status = self._poll("tr_abc", self._payment(self.method.id))
        self.assertEqual(
            status,
            {
                "payment_id": "tr_abc",
                "status": "paid",
                "card_type": "debit",
                "card_no": "1234",
                "card_brand": "Visa",
            },
        )

    def test_a_payment_another_method_requested_is_not_read(self):
        with self.assertRaises(AccessError):
            self._poll("tr_abc", self._payment(self.other_method.id))

    def test_a_payment_odoo_did_not_request_is_not_read(self):
        payment = self._payment(self.method.id)
        payment["webhookUrl"] = "https://odoo.test/pos_mollie/webhook?payload=forged"
        with self.assertRaises(AccessError):
            self._poll("tr_abc", payment)

    def test_a_reference_cannot_leave_the_payment_path(self):
        for payment_id in ("tr_abc/../../refunds", "../customers", "", 42):
            with self.subTest(payment_id=payment_id), self.assertRaises(AccessError):
                self._poll(payment_id, self._payment(self.method.id))
            self.assertEqual(self.fetched, [])

    def test_a_payment_this_method_requested_is_cancelled(self):
        self.payments["tr_abc"] = self._payment(self.method.id)
        self._cashier().mollie_cancel_payment("tr_abc")
        self.assertIn(("DELETE", "/payments/tr_abc"), self.mollie_calls)

    def test_a_payment_of_another_method_or_path_is_not_cancelled(self):
        self.payments["tr_abc"] = self._payment(self.other_method.id)
        for payment_id in ("tr_abc", "tr_abc/../../customers/cst_1"):
            with self.subTest(payment_id=payment_id), self.assertRaises(AccessError):
                self._cashier().mollie_cancel_payment(payment_id)
        self.assertNotIn("DELETE", [method for method, _endpoint in self.mollie_calls])

    def test_a_payment_is_created_only_for_an_open_session_using_the_method(self):
        self._cashier().mollie_create_payment(10.0, "uuid-1", self.session.id)
        self.assertEqual(self.mollie_calls, [("POST", "/payments")])
        for method, session_id in (
            (self.other_method, self.session.id),
            (self.method, self.session.id + 1000),
            (self.method, str(self.session.id)),
        ):
            with (
                self.subTest(method=method.name, session_id=session_id),
                self.assertRaises(AccessError),
            ):
                self._cashier(method).mollie_create_payment(10.0, "uuid", session_id)
        self.assertEqual(self.mollie_calls, [("POST", "/payments")])

    def test_only_a_payment_this_method_requested_is_refunded(self):
        self.payments["tr_abc"] = self._payment(self.other_method.id)
        with self.assertRaises(AccessError):
            self._cashier().mollie_create_refund("tr_abc", 5.0, "uuid", self.session.id)
        self.payments["tr_abc"] = self._payment(self.method.id)
        self._cashier().mollie_create_refund("tr_abc", 5.0, "uuid", self.session.id)
        self.assertIn(("POST", "/payments/tr_abc/refunds"), self.mollie_calls)
