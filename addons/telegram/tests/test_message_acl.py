from odoo.fields import Command

from .common import TelegramBotTestCase


class TestTelegramMessageAcl(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref("base.group_user")
        cls.owner_user = cls.env["res.users"].create(
            {
                "name": "Chat Owner",
                "login": "tg_owner@example.com",
                "partner_id": cls.test_partner.id,
                "group_ids": [Command.set([group_user.id])],
            }
        )
        outsider_partner = cls._create_partner({"name": "TG Outsider"})
        cls.outsider_user = cls.env["res.users"].create(
            {
                "name": "Outsider User",
                "login": "tg_outsider@example.com",
                "partner_id": outsider_partner.id,
                "group_ids": [Command.set([group_user.id])],
            }
        )
        cls.message = cls.env["telegram.message"].create(
            {
                "chat_id": cls.test_chat.id,
                "bot_id": cls.test_bot.id,
                "text": "confidential ledger balance",
            }
        )

    def test_owner_can_read_own_chat_message(self):
        found = (
            self.env["telegram.message"]
            .with_user(self.owner_user)
            .search([("id", "=", self.message.id)])
        )
        self.assertEqual(found, self.message, "chat owner must read their own message")

    def test_outsider_cannot_read_other_partner_message(self):
        found = (
            self.env["telegram.message"]
            .with_user(self.outsider_user)
            .search([("id", "=", self.message.id)])
        )
        self.assertFalse(
            found, "an unrelated internal user must not see the message (TG-18)"
        )
