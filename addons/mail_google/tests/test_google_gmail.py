from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestIrMailServer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mail_server = cls.env["ir.mail_server"].create(
            {"name": "Gmail", "smtp_host": "fake.host"}
        )

    def test_gmail_server_defaults_to_verified_starttls(self):
        server = self.env["ir.mail_server"].new({"smtp_authentication": "gmail"})
        server._onchange_smtp_authentication_gmail()
        self.assertEqual(server.smtp_encryption, "starttls_strict")
        for encryption in ("starttls_strict", "starttls"):
            self.env["ir.mail_server"].create(
                {
                    "name": f"gmail-{encryption}",
                    "smtp_host": "smtp.gmail.com",
                    "smtp_authentication": "gmail",
                    "smtp_user": "me@gmail.com",
                    "smtp_encryption": encryption,
                }
            )
        with self.assertRaises(UserError):
            self.env["ir.mail_server"].create(
                {
                    "name": "gmail-ssl",
                    "smtp_host": "smtp.gmail.com",
                    "smtp_authentication": "gmail",
                    "smtp_user": "me@gmail.com",
                    "smtp_encryption": "ssl_strict",
                }
            )
