from odoo.tests import tagged

from .common import TelegramBotTestCase


@tagged("post_install", "-at_install")
class TestOffAirBot(TelegramBotTestCase):
    def test_archiving_the_credential_takes_the_bot_off_the_air(self):
        self.assertTrue(self.test_bot.on_air)

        self.test_credential.active = False

        self.assertFalse(self.test_bot.on_air)
        self.test_credential.active = True
        self.assertTrue(self.test_bot.on_air)

    def test_an_off_air_bot_carries_no_notification_and_no_connect_link(self):
        self.test_bot.bot_username = "off_air_bot"

        self.test_credential.active = False
        self.env.invalidate_all()

        self.assertFalse(
            self.env["telegram.chat"]._for_partner(self.test_partner, self.test_bot)
        )
        self.assertNotIn(self.test_bot, self.test_user.telegram_connect_bot_ids)
        self.assertNotIn(
            self.test_bot, self.env["telegram.bot"]._serving("telegram.handler.base")
        )

    def test_an_invitation_never_defaults_to_an_off_air_bot(self):
        self.test_bot.bot_username = "off_air_bot"

        self.test_credential.active = False

        invite = self.env["wizard.telegram.invite"].new(
            {"partner_id": self.test_partner.id}
        )
        self.assertNotEqual(invite.bot_id, self.test_bot)
