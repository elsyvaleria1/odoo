from odoo import fields
from odoo.tests import new_test_user, tagged

from odoo.addons.telegram.tests.common import TelegramBotHttpCase


@tagged("post_install", "-at_install")
class TestPreferencesTour(TelegramBotHttpCase):
    def test_the_user_chooses_their_work_phone(self):
        self.test_bot.write({"bot_username": "notify_bot", "notify_mail": True})
        user = new_test_user(
            self.env,
            login="tg_prefs",
            groups="base.group_user",
            notification_type="inbox",
            tz="America/Mexico_City",
        )
        chats = self.env["telegram.chat"]
        for tg_user_id, phone, days_ago in (
            ("700101", "+525511112222", 0),
            ("700102", "+525598765432", 3),
        ):
            account = self._bound_account(tg_user_id, user.partner_id, user=user)
            account._update_phone(phone)
            chats |= chats.create(
                {
                    "chat_id": tg_user_id,
                    "chat_type": "private",
                    "bot_id": self.test_bot.id,
                    "account_id": account.id,
                    "last_message_time": fields.Datetime.subtract(
                        fields.Datetime.now(), days=days_ago
                    ),
                }
            )
        personal, work = chats

        self.assertEqual(user._get_telegram_notify_chat(), personal)
        self.start_tour("/odoo", "mail_telegram_preferences", login="tg_prefs")

        self.assertEqual(user._telegram_settings().telegram_notify_chat_id, work)
        self.assertEqual(user._get_telegram_notify_chat(), work)
