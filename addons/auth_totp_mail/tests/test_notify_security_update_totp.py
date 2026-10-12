from odoo.tests import tagged, users

from odoo.addons.mail.tests.common import MailCommon


@tagged("-at_install", "post_install", "mail_tools", "res_users")
class TestNotifySecurityUpdateTotp(MailCommon):
    @users("employee")
    def test_security_update_totp_enabled_disabled(self):
        recipients = [self.env.user.email_formatted]
        with self.mock_mail_gateway():
            self.env.user.write({"totp_secret": "test"})

        self.assertSentEmail(
            '"YourTestCompany" <your.company@example.com>',
            recipients,
            subject="Security Update: 2FA Activated",
        )

        with self.mock_mail_gateway():
            self.env.user.write({"totp_secret": False})

        self.assertSentEmail(
            '"YourTestCompany" <your.company@example.com>',
            recipients,
            subject="Security Update: 2FA Deactivated",
        )

    @users("employee")
    def test_security_update_trusted_device_added_removed(self):
        recipients = [self.env.user.email_formatted]
        with self.mock_mail_gateway():
            self.env["auth.totp.trust"].sudo()._issue(
                "Chrome on Windows",
            )

        self.assertNotSentEmail(recipients)

        with self.mock_mail_gateway():
            self.env["auth.totp.trust"].flush_model()
            self.env.user.sudo(False)._revoke_all_totp_trust()

        self.assertSentEmail(
            '"YourTestCompany" <your.company@example.com>',
            recipients,
            subject="Security Update: Device Removed",
        )
