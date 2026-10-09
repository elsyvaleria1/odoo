from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.pos_dpopay.models.pos_payment_method import PosPaymentMethod


@tagged("post_install", "-at_install")
class TestDpoPayCredentials(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.method = cls.env["pos.payment.method"].create(
            {
                "name": "DPO Pay",
                "use_payment_terminal": "dpopay",
                "dpopay_client_id": "client",
                "dpopay_client_secret": "client-secret",
                "dpopay_bearer_token": "bearer",
            }
        )
        cls.cashier = new_test_user(
            cls.env, "dpopay_cashier", groups="point_of_sale.group_pos_user"
        )

    def test_a_cashier_reads_no_secret(self):
        method = self.method.with_user(self.cashier)
        for name in ("dpopay_client_secret", "dpopay_bearer_token"):
            with self.subTest(name), self.assertRaises(AccessError):
                method.read([name])

    def test_a_cashier_request_still_spends_the_bearer_token(self):
        spent = []

        def execute(method, payload, endpoint):
            spent.append(method._dpopay_headers()["Authorization"])
            return {"status": "ok"}

        with patch.object(PosPaymentMethod, "_execute_dpopay_api_request", execute):
            result = self.method.with_user(self.cashier).send_dpopay_request(
                {}, "get-status"
            )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(spent, ["Bearer bearer"])
