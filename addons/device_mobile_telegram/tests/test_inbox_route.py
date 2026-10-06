from odoo.tests import tagged

from odoo.addons.mail_telegram.tests.test_inbox import InboxRouteCase


@tagged("post_install", "-at_install")
class TestInboxOnCompanyPhones(InboxRouteCase):
    """The inbox inside Telegram follows the bot's rule: under company
    phones only, an account that is not one gets nothing."""

    def test_an_account_that_is_no_company_phone_gets_no_inbox(self):
        self.test_bot.notify_company_phones_only = True

        body = self._rpc(
            "overview",
            bot_id=self.test_bot.id,
            init_data=self._signed(int(self.test_chat.chat_id)),
        )

        self.assertEqual(body["result"], {"error": "auth"})
