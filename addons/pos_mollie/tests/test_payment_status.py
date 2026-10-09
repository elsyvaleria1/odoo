from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools import hash_sign

from odoo.addons.pos_mollie.models.pos_payment_method import (
    WEBHOOK_SCOPE,
    PosPaymentMethod,
)


@tagged("post_install", "-at_install")
class TestMolliePaymentStatus(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        journal = cls.env["account.journal"].create(
            {"name": "Mollie terminal", "type": "bank", "code": "MOLTT"}
        )
        cls.method, cls.other_method = cls.env["pos.payment.method"].create(
            [
                {
                    "name": name,
                    "journal_id": journal.id,
                    "payment_method_type": "terminal",
                }
                for name in ("Mollie", "Other Mollie")
            ]
        )

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

    def _poll(self, payment_id, payment_info):
        with patch.object(
            PosPaymentMethod, "_mollie_get_payment", return_value=payment_info
        ) as fetch:
            try:
                return self.method.mollie_get_payment_status(payment_id)
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
