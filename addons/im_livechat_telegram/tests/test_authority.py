from unittest.mock import patch

from odoo.tests import tagged

from .test_livechat_telegram import LivechatTelegramCase

SERVE = "im_livechat_telegram.privilege_serve_customers"


class LivechatWebhookCase(LivechatTelegramCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public = cls.env.ref("base.public_user")

    @classmethod
    def _customer_contact(cls, tg_id, name):
        contact = cls._create_partner({"name": name})
        account = cls.env["telegram.account"]._from_telegram(
            {"id": int(tg_id), "first_name": name}
        )
        account._bind(contact, method="contact")
        return contact

    def _webhook(self, update):
        self.patch(self.env.transaction, "default_env", self.env(user=self.public))
        channels = type(self.env["discuss.channel"])
        post = channels.message_post
        update_content = channels._message_update_content
        open_session = type(self.env["im_livechat.channel"])._open_session
        posters = []
        self.openers = []
        self.updaters = []

        def spy(this, **kwargs):
            posters.append((this.env.uid, this.env.su))
            return post(this, **kwargs)

        def opener_spy(this, **kwargs):
            self.openers.append((this.env.uid, this.env.su))
            return open_session(this, **kwargs)

        def updater_spy(this, message, **kwargs):
            self.updaters.append((this.env.uid, this.env.su))
            return update_content(this, message, **kwargs)

        with (
            patch.object(channels, "message_post", spy),
            patch.object(channels, "_message_update_content", updater_spy),
            patch.object(
                type(self.env["im_livechat.channel"]), "_open_session", opener_spy
            ),
            self.mock_api_gateway_post(),
            self.mock_rate_limiter(),
        ):
            self.env["telegram.router"]._handle_update(
                self.test_bot.with_user(self.public).sudo(), update
            )
        return posters

    def _writes(self, chat_id, text, update_id):
        return self._webhook(
            {
                "update_id": update_id,
                "message": self.mock_telegram_message(
                    chat_id=chat_id, text=text, message_id=update_id
                ),
            }
        )

    def _presses(self, chat_id, data, update_id):
        return self._webhook(
            {
                "update_id": update_id,
                "callback_query": self.mock_telegram_callback_query(
                    chat_id=chat_id, callback_data=data
                ),
            }
        )

    def _session_of(self, chat_id):
        chat = self.env["telegram.chat"].search([("chat_id", "=", chat_id)])
        return chat, self.env["discuss.channel"].search(
            [("telegram_chat_id", "=", chat.id)]
        )


@tagged("post_install", "-at_install")
class TestCustomerAuthority(LivechatWebhookCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls._customer_contact("588001", "Cliente Uno")

    def test_a_customer_s_message_is_posted_as_the_webhook_s_user(self):
        posters = self._writes("588001", "Hola, necesito ayuda", 9601)

        self.assertEqual(posters, [(self.public.id, False)])
        self.assertEqual(self.openers, [(self.public.id, False)])
        _chat, session = self._session_of("588001")
        posted = session.message_ids.filtered(lambda m: m.author_id == self.customer)
        self.assertIn("necesito ayuda", posted.body)

    def test_a_rating_press_rates_the_customer_s_own_session(self):
        self._writes("588001", "hola", 9621)
        _chat, session = self._session_of("588001")
        session._close_livechat_session()
        self._presses("588001", f"lc:rate:{session.id}:5", 9622)
        self.assertEqual(session.rating_ids.rating, 5)

    def test_a_session_opens_on_an_operator_with_nobody_online_as_the_webhook_s_user(
        self,
    ):
        self.env["mail.presence"].sudo().search(
            [("user_id", "=", self.operator.id)]
        ).unlink()
        self._writes("588001", "hola", 9611)

        self.assertEqual(self.openers, [(self.public.id, False)])
        _chat, session = self._session_of("588001")
        self.assertEqual(session.livechat_operator_id, self.operator.partner_id)
        self.assertEqual(session.livechat_status, "need_help")

    def test_the_privilege_reaches_telegram_sessions_only(self):
        self._writes("588001", "hola", 9631)
        _chat, session = self._session_of("588001")
        web = self.livechat._open_session(
            visitor_partner=self._create_partner({"name": "Visitante web"})
        )
        group = self.env["discuss.channel"].create({"name": "Equipo"})
        channels = self.env["discuss.channel"].with_user(self.public)
        self.assertFalse(channels.search([("id", "=", session.id)]))
        served = channels.with_privilege(SERVE).search(
            [("id", "in", (session | web | group).ids)]
        )
        self.assertEqual(served, session)


@tagged("post_install", "-at_install")
class TestChatbotAuthority(LivechatWebhookCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._customer_contact("588101", "Cliente Bot")
        cls.script = cls.env["chatbot.script"].create({"title": "Bot de soporte"})
        _hello, question, _after = cls.env["chatbot.script.step"].create(
            [
                {
                    "step_type": "text",
                    "message": "¡Hola!",
                    "chatbot_script_id": cls.script.id,
                },
                {
                    "step_type": "question_selection",
                    "message": "¿Qué necesitas?",
                    "chatbot_script_id": cls.script.id,
                },
                {
                    "step_type": "text",
                    "message": "Te ayudo con tu factura.",
                    "chatbot_script_id": cls.script.id,
                },
            ]
        )
        cls.question = question
        cls.answer = cls.env["chatbot.script.answer"].create(
            {"name": "Factura", "script_step_id": question.id}
        )
        cls.livechat.rule_ids = [(0, 0, {"chatbot_script_id": cls.script.id})]
        cls.test_bot.livechat_chatbot_script_id = cls.script

    def test_a_chatbot_answer_is_pressed_as_the_webhook_s_user(self):
        self._writes("588101", "hola", 9701)
        _chat, session = self._session_of("588101")
        self.assertEqual(session.chatbot_current_step_id, self.question)

        posters = self._presses("588101", f"lc:ans:{self.answer.id}", 9702)

        self.assertIn((self.public.id, False), posters)
        self.assertNotEqual(session.chatbot_current_step_id, self.question)
        asked = self.env["chatbot.message"].search(
            [
                ("discuss_channel_id", "=", session.id),
                ("script_step_id", "=", self.question.id),
            ]
        )
        self.assertEqual(asked.user_script_answer_id, self.answer)


@tagged("post_install", "-at_install")
class TestForwardAuthority(LivechatWebhookCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls._customer_contact("588151", "Cliente Persona")
        cls.script = cls.env["chatbot.script"].create({"title": "Recepción"})
        _hello, question, _forward = cls.env["chatbot.script.step"].create(
            [
                {
                    "step_type": "text",
                    "message": "¡Hola!",
                    "chatbot_script_id": cls.script.id,
                },
                {
                    "step_type": "question_selection",
                    "message": "¿Qué necesitas?",
                    "chatbot_script_id": cls.script.id,
                },
                {
                    "step_type": "forward_operator",
                    "message": "Te paso con alguien.",
                    "chatbot_script_id": cls.script.id,
                },
            ]
        )
        cls.person = cls.env["chatbot.script.answer"].create(
            {"name": "Hablar con una persona", "script_step_id": question.id}
        )
        cls.livechat.rule_ids = [(0, 0, {"chatbot_script_id": cls.script.id})]
        cls.test_bot.livechat_chatbot_script_id = cls.script

    def test_talking_to_a_person_forwards_and_names_the_session(self):
        self._writes("588151", "hola", 9751)
        _chat, session = self._session_of("588151")
        self.assertEqual(session.livechat_operator_id, self.script.operator_partner_id)

        posters = self._presses("588151", f"lc:ans:{self.person.id}", 9752)

        self.assertIn((self.public.id, False), posters)
        self.assertEqual(session.livechat_operator_id, self.operator.partner_id)
        operator_name = self.operator.livechat_username or self.operator.name
        self.assertEqual(session.name, f"Cliente Persona {operator_name}")
        self.assertIn(
            self.operator.partner_id,
            session.channel_member_ids.filtered(
                lambda m: m.livechat_member_type == "agent"
            ).partner_id,
        )


@tagged("post_install", "-at_install")
class TestBusinessAuthority(LivechatWebhookCase):

    OWNER_ID = 588201
    CUSTOMER_ID = 588202

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._bound_account(cls.OWNER_ID, cls.operator.partner_id, user=cls.operator)
        cls.connection = cls.env["telegram.business.connection"]._from_update(
            cls.test_bot,
            {
                "id": "bc-owner",
                "user": {"id": cls.OWNER_ID, "first_name": "Operador"},
                "user_chat_id": cls.OWNER_ID,
                "rights": {"can_reply": True},
                "is_enabled": True,
            },
        )
        cls.customer = cls._customer_contact(cls.CUSTOMER_ID, "Cliente Negocio")

    def _business(self, text, update_id, kind="business_message", message_id=1):
        return self._webhook(
            {
                "update_id": update_id,
                kind: {
                    "message_id": message_id,
                    "business_connection_id": "bc-owner",
                    "from": {"id": self.CUSTOMER_ID, "first_name": "Cliente"},
                    "chat": {"id": self.CUSTOMER_ID, "type": "private"},
                    "date": 1234567890,
                    "text": text,
                },
            }
        )

    def test_a_customer_s_message_and_edit_are_the_webhook_user_s(self):
        posters = self._business("precio de la avena", 9801)
        self.assertEqual(posters, [(self.public.id, False)])
        self.assertEqual(self.openers, [(self.public.id, False)])
        chat = self.env["telegram.chat"].search(
            [("business_connection_id", "=", self.connection.id)]
        )
        session = self.env["discuss.channel"].search(
            [("telegram_chat_id", "=", chat.id)]
        )
        posted = session.message_ids.filtered(lambda m: m.author_id == self.customer)
        self.assertEqual(posted.create_uid, self.public)

        self._business("precio del maíz", 9802, kind="edited_business_message")
        self.assertIn("maíz", posted.body)

    def test_a_customer_s_deletion_empties_their_message_as_the_webhook_s_user(self):
        self._business("precio de la avena", 9811, message_id=7)
        chat = self.env["telegram.chat"].search(
            [("business_connection_id", "=", self.connection.id)]
        )
        session = self.env["discuss.channel"].search(
            [("telegram_chat_id", "=", chat.id)]
        )
        posted = session.message_ids.filtered(lambda m: m.author_id == self.customer)
        self.assertIn("avena", posted.body)

        self._webhook(
            {
                "update_id": 9812,
                "deleted_business_messages": {
                    "business_connection_id": "bc-owner",
                    "chat": {"id": self.CUSTOMER_ID, "type": "private"},
                    "message_ids": [7],
                },
            }
        )

        self.assertEqual(self.updaters, [(self.public.id, False)])
        self.assertTrue(posted._filtered_empty())
