from unittest.mock import patch

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestAccountOnlinePaymentWebhook(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.link = cls.env["account.online.link"].create(
            {
                "name": "Link",
                "client_id": "client_xyz",
                "is_payment_activated": False,
            }
        )

    @patch("odoo.addons.mail.models.mail_template.MailTemplate.send_mail")
    def test_payment_activated_webhook(self, patched_send_mail):
        response = self.url_open(
            "/webhook/odoofin/payment_activated",
            data=json_dumps(
                {
                    "client_id": "client_xyz",
                }
            ),
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(json_loads(response.text).get("result"))
        self.assertTrue(self.link.is_payment_activated)
        patched_send_mail.assert_called_once()

    @patch("odoo.addons.mail.models.mail_template.MailTemplate.send_mail")
    def test_webhook_unknown_client(self, patched_send_mail):
        response = self.url_open(
            "/webhook/odoofin/payment_activated",
            data=json_dumps(
                {
                    "client_id": "unknown_client_id",
                }
            ),
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(json_loads(response.text).get("result"))
        self.assertFalse(self.link.is_payment_activated)
        patched_send_mail.assert_not_called()
