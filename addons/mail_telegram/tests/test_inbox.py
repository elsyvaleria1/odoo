import time

from odoo import Command
from odoo.exceptions import AccessError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import tagged

from odoo.addons.telegram.tests.common import TelegramBotHttpCase, TelegramBotTestCase
from odoo.addons.telegram.tests.test_web_app_init_data import signed_init_data


class InboxCase(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user.notification_type = "inbox"
        cls.test_user.group_ids |= cls.env.ref("base.group_partner_manager")
        cls.colleague = cls.env["res.users"].create(
            {"name": "Ana Colega", "login": "ana_colega"}
        )
        cls.record = cls.env["res.partner"].create({"name": "Rancho El Sauz"})

    def _inbox(self):
        return self.env["telegram.inbox"].with_user(self.test_user)

    def _notify(self, body="Revisa el lote 3"):
        return (
            self.record.with_user(self.colleague)
            .sudo()
            .message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                partner_ids=self.test_partner.ids,
            )
        )


class TestInbox(InboxCase):
    def test_the_overview_lists_unread_notifications_and_chats(self):
        self._notify()
        chat = (
            self.env["discuss.channel"]
            .with_user(self.colleague)
            ._get_or_create_chat(self.test_partner.ids)
        )
        chat.with_user(self.colleague).message_post(
            body="¿Vienes mañana?",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        overview = self._inbox()._overview()
        self.assertEqual(
            [n["body"] for n in overview["notifications"]], ["Revisa el lote 3"]
        )
        self.assertEqual(overview["notifications"][0]["thread"], "Rancho El Sauz")
        chats = {c["id"]: c for c in overview["chats"]}
        self.assertEqual(chats[chat.id]["unread"], 1)
        self.assertEqual(chats[chat.id]["preview"]["body"], "¿Vienes mañana?")
        self.assertEqual(overview["labels"]["chats"], "Chats")

    def test_opening_and_reading_clears_them(self):
        message = self._notify()
        self._inbox()._read(message_ids=[message.id])
        self.assertFalse(self._inbox()._overview()["notifications"])

    def test_a_reply_is_the_user_s_and_a_note_stays_internal(self):
        thread = self._inbox()._thread("res.partner", self.record.id)
        self.assertTrue(thread["can_note"])
        posted = self._inbox()._post(
            "res.partner", self.record.id, "Ya voy\nen camino", note=True
        )
        message = self.env["mail.message"].browse(posted["id"])
        self.assertEqual(message.author_id, self.test_partner)
        self.assertTrue(message.subtype_id.internal)
        self.assertIn("Ya voy<br>en camino", message.body)

    def test_a_channel_never_takes_a_note(self):
        channel = (
            self.env["discuss.channel"]
            .with_user(self.test_user)
            .create({"name": "Cuadrilla", "channel_type": "channel"})
        )
        posted = self._inbox()._post("discuss.channel", channel.id, "hola", note=True)
        self.assertFalse(posted["note"])

    def test_what_the_user_cannot_read_stays_closed(self):
        private = (
            self.env["discuss.channel"]
            .with_user(self.colleague)
            .create({"name": "Privado", "channel_type": "group"})
        )
        with self.assertRaises(AccessError):
            self._inbox()._thread("discuss.channel", private.id)

    def test_posting_needs_what_odoo_asks_of_the_user(self):
        # only what every internal user has: reading contacts, not writing them
        reader = self.env["res.users"].create(
            {
                "name": "Lector",
                "login": "lector_inbox",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        with self.assertRaises(AccessError):
            self.env["telegram.inbox"].with_user(reader)._post(
                "res.partner", self.record.id, "hola"
            )

    def test_a_model_without_chatter_is_refused(self):
        with self.assertRaises(ValueError):
            self._inbox()._thread("res.lang", 1)

    def _bandeja(self, base_url):
        self.env["ir.config_parameter"].sudo().set_param("web.base.url", base_url)
        self.test_bot.notify_mail = True
        update = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id, text="/bandeja"
        )
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_message(self.test_bot, update)
        return self.env["telegram.message"].search(
            [("chat_id", "=", self.test_chat.id), ("message_type", "=", "outbound")]
        )

    def test_bandeja_opens_the_inbox_and_keeps_it_as_the_menu_button(self):
        queued = self._bandeja("https://odoo.example.com")
        url = f"/telegram/inbox/{self.test_bot.id}"
        button = queued.filtered(lambda m: m.api_method == "sendMessage")
        self.assertIn(
            url,
            button.payload["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"],
        )
        menu = queued.filtered(lambda m: m.api_method == "setChatMenuButton")
        self.assertIn(url, menu.payload["menu_button"]["web_app"]["url"])
        self.assertTrue(
            menu.payload["menu_button"]["web_app"]["url"].startswith("https://")
        )

    def test_bandeja_off_https_says_why_and_sets_no_menu_button(self):
        queued = self._bandeja("http://odoo.example.com")
        self.assertEqual(queued.mapped("api_method"), ["sendMessage"])
        self.assertIn("https", queued.payload["text"])
        self.assertNotIn("reply_markup", queued.payload)


@tagged("post_install", "-at_install")
class TestInboxRoutes(TelegramBotHttpCase):
    def _rpc(self, path, **params):
        self.env.flush_all()
        response = self.url_open(
            f"/telegram/inbox/{path}",
            data=json_dumps({"jsonrpc": "2.0", "id": 3, "params": params}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _signed(self, user_id):
        return signed_init_data(
            self.TEST_BOT_TOKEN,
            {"auth_date": str(int(time.time())), "user": json_dumps({"id": user_id})},
        )

    def test_a_bound_user_gets_their_inbox(self):
        body = self._rpc(
            "overview",
            bot_id=self.test_bot.id,
            init_data=self._signed(int(self.test_chat.chat_id)),
        )
        self.assertNotIn("error", body, body)
        self.assertIn("notifications", body["result"])

    def test_a_stranger_gets_nothing(self):
        body = self._rpc(
            "overview", bot_id=self.test_bot.id, init_data=self._signed(424242)
        )
        self.assertEqual(body["result"], {"error": "auth"})

    def test_the_page_names_its_bot(self):
        response = self.url_open(f"/telegram/inbox/{self.test_bot.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'data-bot-id="{self.test_bot.id}"', response.text)

    def test_another_company_s_bot_opens_that_company_s_records_only(self):
        bot = self._bot_of_another_company("Other Inbox Bot")
        self.test_user.write({"company_ids": [Command.link(bot.company_id.id)]})
        partners = self.env["res.partner"]
        ours = partners.create({"name": "Rancho Otro", "company_id": bot.company_id.id})
        main = partners.create(
            {"name": "Rancho Main", "company_id": self.env.company.id}
        )
        session = bot._mint_mini_app_session(self.test_chat.chat_id)

        def thread(partner):
            return self._rpc(
                "thread",
                bot_id=bot.id,
                s=session,
                model="res.partner",
                res_id=partner.id,
            )["result"]

        self.assertEqual(thread(ours).get("title"), "Rancho Otro")
        self.assertEqual(thread(main), {"error": "access"})
