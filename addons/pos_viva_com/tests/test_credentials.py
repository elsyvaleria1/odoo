from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.pos_viva_com.models.pos_payment_method import PosPaymentMethod

SECRETS = (
    "viva_com_api_key",
    "viva_com_client_secret",
    "viva_com_bearer_token",
    "viva_com_webhook_verification_key",
    "viva_com_webhook_endpoint",
)


@tagged("post_install", "-at_install")
class TestVivaComCredentials(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.method = cls.env["pos.payment.method"].create(
            {
                "name": "Viva",
                "use_payment_terminal": "viva_com",
                "viva_com_merchant_id": "merchant",
                "viva_com_api_key": "api-key",
                "viva_com_client_id": "client",
                "viva_com_client_secret": "client-secret",
                "viva_com_terminal_id": "16002169",
                "viva_com_bearer_token": "bearer",
            }
        )
        cls.cashier = new_test_user(
            cls.env, "viva_cashier", groups="point_of_sale.group_pos_user"
        )
        cls.manager = new_test_user(
            cls.env, "viva_manager", groups="point_of_sale.group_pos_manager"
        )

    def test_a_cashier_reads_no_secret(self):
        method = self.method.with_user(self.cashier)
        self.assertEqual(
            method.read(["viva_com_terminal_id"])[0]["viva_com_terminal_id"], "16002169"
        )
        for name in SECRETS:
            with self.subTest(name), self.assertRaises(AccessError):
                method.read([name])

    def test_a_manager_reads_them(self):
        values = self.method.with_user(self.manager).read(list(SECRETS))[0]
        self.assertEqual(values["viva_com_api_key"], "api-key")
        self.assertEqual(values["viva_com_webhook_verification_key"], "viva_com_test")
        self.assertIn("token=viva_com_test", values["viva_com_webhook_endpoint"])

    def test_a_cashier_request_still_spends_the_bearer_token(self):
        spent = []

        def call(method, session, endpoint, action, data=None):
            spent.append(method.viva_com_bearer_token)
            return {"success": 200}

        with patch.object(PosPaymentMethod, "_call_viva_com_with", call):
            result = self.method.with_user(self.cashier).viva_com_get_payment_status(
                "s1"
            )

        self.assertEqual(result, {"success": 200})
        self.assertEqual(spent, ["bearer"])
