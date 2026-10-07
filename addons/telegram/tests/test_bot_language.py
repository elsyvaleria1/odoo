from .common import TelegramBotTestCase


class TestBotLanguage(TelegramBotTestCase):
    """A bot answers in the language the person's Telegram app uses, else in
    their linked contact's, unless it is set to always answer in its own."""

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

    def test_the_telegram_app_s_language_comes_before_the_contact_s(self):
        # Odoo in English, Telegram in Spanish: the bot speaks Spanish
        self.test_account.language_code = "es"
        self.assertEqual(self.test_bot.get_lang(self.test_chat), "es_MX")

    def test_an_app_language_odoo_does_not_run_falls_back_to_the_contact_s(self):
        self.test_account.language_code = "fr"
        self.assertEqual(self.test_bot.get_lang(self.test_chat), "en_US")

    def test_a_bot_set_to_its_own_language_ignores_the_app_s_too(self):
        self.test_account.language_code = "en"
        self.test_bot.answer_in_bot_lang = True
        self.assertEqual(self.test_bot.get_lang(self.test_chat), "es_MX")

    def test_switching_the_app_s_language_resends_the_menu_in_it(self):
        self.test_chat._sync_command_menu()
        self.assertEqual(self.test_chat.command_menu[-1]["command"], "ayuda")

        self.env["telegram.account"]._from_telegram(
            {"id": 12345, "first_name": "Test", "language_code": "es"}
        )

        menus = self.env["telegram.message"].search(
            [("chat_id", "=", self.test_chat.id), ("api_method", "=", "setMyCommands")]
        )
        self.assertEqual(len(menus), 2)
        self.assertNotEqual(menus[0].payload["commands"], menus[1].payload["commands"])
