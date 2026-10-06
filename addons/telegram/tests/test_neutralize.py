from odoo.modules import neutralize
from odoo.tests import tagged

from .common import TelegramBotTestCase


@tagged("post_install", "-at_install", "neutralize")
class TestTelegramBotNeutralize(TelegramBotTestCase):
    def _neutralize(self):
        self.env.flush_all()
        for query in neutralize.get_neutralization_queries(["telegram"]):
            self.env.cr.execute(query)
        self.env.invalidate_all()

    def test_a_neutralized_copy_neither_sends_nor_receives(self):
        self._neutralize()
        self.assertFalse(self.test_credential.active)
        with self.assertRaises(ValueError):
            self.test_bot._get_bot_token()
        self.assertFalse(
            self.env["telegram.bot"].find_by_token(self.TEST_BOT_TOKEN),
            "a neutralized copy kept answering the production bot's webhook",
        )

    def test_a_telegram_credential_no_bot_uses_is_left_alone(self):
        spare = self._make_bot_credential("Spare Telegram Credential", "1:spare")
        self._neutralize()
        self.assertTrue(spare.active)
