from odoo.tests import TransactionCase, tagged

from odoo.addons.sms.tools.sms_api import SmsApi


@tagged("post_install", "-at_install")
class TestSmsApiErrorMessages(TransactionCase):
    def test_error_messages_never_carry_the_account_token(self):
        account = self.env["iap.account"].sudo().acquire_account("sms")
        account.account_token = "sms-account-secret-token"
        messages = SmsApi(self.env)._get_sms_api_error_messages()
        self.assertTrue(messages)
        for state, message in messages.items():
            self.assertNotIn("sms-account-secret-token", str(message), state)
