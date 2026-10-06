from .common import TelegramBotTestCase


class TestBotLanguage(TelegramBotTestCase):
    """A bot answers in its linked contact's language unless it is set to
    always answer in its own."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_MX")
        cls.test_bot.lang = "es_MX"
        cls.test_partner.lang = "en_US"

    def test_the_contacts_language_comes_first_by_default(self):
        self.assertEqual(self.test_bot.get_lang(self.test_chat), "en_US")

    def test_a_bot_set_to_its_own_language_ignores_the_contacts(self):
        self.test_bot.answer_in_bot_lang = True
        self.assertEqual(self.test_bot.get_lang(self.test_chat), "es_MX")

    def test_an_unlinked_chat_gets_the_bots_language(self):
        self.assertEqual(self.test_bot.get_lang(self.unlinked_chat), "es_MX")
