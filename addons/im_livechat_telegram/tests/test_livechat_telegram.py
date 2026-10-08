from odoo.tests import new_test_user

from odoo.addons.telegram.tests.common import NOT_A_MENU, TelegramBotTestCase


class LivechatTelegramCase(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = new_test_user(
            cls.env(su=True),
            login="tg_operator",
            groups="im_livechat.im_livechat_group_user",
        )
        cls.livechat = cls.env["im_livechat.channel"].create(
            {"name": "Soporte Telegram", "user_ids": [cls.operator.id]}
        )
        cls.test_bot.write(
            {
                "livechat_channel_id": cls.livechat.id,
                "livechat_waiting_message": "Te respondemos en cuanto alguien esté disponible.",
            }
        )

    def setUp(self):
        super().setUp()
        self.env["mail.presence"].sudo()._update_presence(self.operator)

    def _customer_writes(
        self, text="Hola, necesito ayuda", chat_id="700100", message_id=1
    ):
        update = self.mock_telegram_message(
            chat_id=chat_id, text=text, message_id=message_id
        )
        with self.mock_api_gateway_post() as post, self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_message(self.test_bot, update)
        chat = self.env["telegram.chat"].search([("chat_id", "=", chat_id)])
        session = self.env["discuss.channel"].search(
            [("telegram_chat_id", "=", chat.id)]
        )
        return chat, session, post

    def _queued(self, chat):
        return self.env["telegram.message"].search(
            [("chat_id", "=", chat.id), ("message_type", "=", "outbound"), NOT_A_MENU],
            order="id",
        )


class TestCustomers(LivechatTelegramCase):
    def test_a_customer_message_opens_a_session_as_their_contact(self):
        chat, session, _post = self._customer_writes()

        self.assertEqual(len(session), 1)
        self.assertEqual(session.channel_type, "livechat")
        self.assertEqual(session.livechat_operator_id, self.operator.partner_id)
        customer = chat.account_id.partner_id
        self.assertEqual(chat.account_id.binding_id.method, "contact")
        self.assertIn(customer, session.livechat_customer_partner_ids)
        posted = session.message_ids.filtered(lambda m: m.author_id == customer)
        self.assertIn("necesito ayuda", posted.body)
        inbound = self.env["telegram.message"].search(
            [("chat_id", "=", chat.id), ("message_type", "=", "inbound")]
        )
        self.assertEqual(inbound.mail_message_id, posted)

    def test_the_next_message_goes_to_the_same_session(self):
        _chat, first, _post = self._customer_writes()
        _chat, second, _post = self._customer_writes("otra cosa", message_id=2)
        self.assertEqual(first, second)

    def test_an_internal_user_is_not_a_customer(self):
        self._customer_writes(chat_id=self.test_chat.chat_id)
        self.assertFalse(
            self.env["discuss.channel"].search(
                [("telegram_chat_id", "=", self.test_chat.id)]
            )
        )

    def test_with_nobody_online_the_session_waits_for_help(self):
        self.env["mail.presence"].sudo().search(
            [("user_id", "=", self.operator.id)]
        ).unlink()

        chat, session, _post = self._customer_writes()

        self.assertEqual(session.livechat_status, "need_help")
        texts = [(m.payload or {}).get("text", "") for m in self._queued(chat)]
        self.assertTrue(any("en cuanto alguien" in text for text in texts))

    def test_an_operator_reply_reaches_the_customer(self):
        chat, session, _post = self._customer_writes()
        session.with_user(self.operator).message_post(
            body="Claro, ¿en qué te ayudo?",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        texts = [m.payload.get("text", "") for m in self._queued(chat)]
        self.assertTrue(any("¿en qué te ayudo?" in text for text in texts))
        self.assertTrue(any(self.operator.name in text for text in texts))

    def test_the_customer_message_is_not_echoed_back(self):
        chat, _session, _post = self._customer_writes()
        self.assertFalse(
            [
                m
                for m in self._queued(chat)
                if "necesito ayuda" in (m.payload or {}).get("text", "")
            ]
        )

    def test_closing_asks_for_a_rating_and_a_press_records_it(self):
        chat, session, _post = self._customer_writes()
        session._close_livechat_session()
        prompt = self._queued(chat)[-1]
        buttons = prompt.payload["reply_markup"]["inline_keyboard"][0]
        self.assertEqual(buttons[-1]["callback_data"], f"lc:rate:{session.id}:5")

        query = self.mock_telegram_callback_query(
            chat_id=chat.chat_id, callback_data=f"lc:rate:{session.id}:5"
        )
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_callback_query(self.test_bot, query)
        self.assertEqual(session.rating_ids.rating, 5)


class TestChatbot(LivechatTelegramCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.script = cls.env["chatbot.script"].create({"title": "Bot de soporte"})
        steps = cls.env["chatbot.script.step"].sudo()
        _hello, cls.question = steps.create(
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
            ]
        )
        cls.answer_invoice, _other = cls.env["chatbot.script.answer"].create(
            [
                {"name": "Factura", "script_step_id": cls.question.id},
                {"name": "Otro", "script_step_id": cls.question.id},
            ]
        )
        steps.create(
            {
                "step_type": "text",
                "message": "Te ayudo con tu factura.",
                "chatbot_script_id": cls.script.id,
            }
        )
        cls.livechat.rule_ids = [(0, 0, {"chatbot_script_id": cls.script.id})]
        cls.test_bot.livechat_chatbot_script_id = cls.script

    def test_the_question_arrives_with_its_answers_and_a_press_goes_on(self):
        chat, session, _post = self._customer_writes()
        question = [
            m
            for m in self._queued(chat)
            if "¿Qué necesitas?" in (m.payload or {}).get("text", "")
        ]
        self.assertEqual(len(question), 1)
        buttons = question[0].payload["reply_markup"]["inline_keyboard"]
        self.assertIn(
            f"lc:ans:{self.answer_invoice.id}",
            [row[0]["callback_data"] for row in buttons],
        )

        query = self.mock_telegram_callback_query(
            chat_id=chat.chat_id, callback_data=f"lc:ans:{self.answer_invoice.id}"
        )
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_callback_query(self.test_bot, query)

        texts = [(m.payload or {}).get("text", "") for m in self._queued(chat)]
        self.assertTrue(any("Te ayudo con tu factura" in text for text in texts))
        self.assertNotEqual(session.chatbot_current_step_id, self.question)


class TestBusinessAccount(LivechatTelegramCase):
    """The operator's own Telegram Business account: its customers' chats are
    sessions the operator answers, from Odoo or from their phone."""

    OWNER_ID = 880001
    CUSTOMER_ID = 880002

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner_account = cls._bound_account(
            cls.OWNER_ID, cls.operator.partner_id, user=cls.operator
        )
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

    def _business(self, text, from_owner=False, message_id=1, kind="business_message"):
        sender = self.OWNER_ID if from_owner else self.CUSTOMER_ID
        update = {
            "update_id": 7000 + message_id + (500 if kind != "business_message" else 0),
            kind: {
                "message_id": message_id,
                "business_connection_id": "bc-owner",
                "from": {"id": sender, "first_name": "X"},
                "chat": {
                    "id": self.CUSTOMER_ID,
                    "type": "private",
                    "first_name": "Cliente",
                },
                "date": 1234567890,
                "text": text,
            },
        }
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._handle_update(self.test_bot, update)
        chat = self.env["telegram.chat"].search(
            [("business_connection_id", "=", self.connection.id)]
        )
        session = self.env["discuss.channel"].search(
            [("telegram_chat_id", "=", chat.id)]
        )
        return chat, session

    def test_a_customer_message_opens_a_session_of_the_owner(self):
        self.env["mail.presence"].sudo().search(
            [("user_id", "=", self.operator.id)]
        ).unlink()
        chat, session = self._business("¿Tienen existencias?")

        self.assertEqual(session.livechat_operator_id, self.operator.partner_id)
        customer = chat.account_id.partner_id
        self.assertIn(customer, session.livechat_customer_partner_ids)
        self.assertIn(
            "existencias",
            session.message_ids.filtered(lambda m: m.author_id == customer).body,
        )
        self.assertFalse(self._queued(chat))

    def test_the_owner_answering_from_their_phone_is_posted_not_resent(self):
        chat, session = self._business("hola")
        _chat, _session = self._business("buenas, sí", from_owner=True, message_id=2)

        posted = session.message_ids.filtered(
            lambda m: (
                m.author_id == self.operator.partner_id and "buenas" in (m.body or "")
            )
        )
        self.assertEqual(len(posted), 1)
        self.assertFalse(self._queued(chat))

    def test_an_answer_from_odoo_goes_out_as_the_owner_unlabelled(self):
        chat, session = self._business("hola")
        session.with_user(self.operator).message_post(
            body="Claro que sí",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        queued = self._queued(chat)
        self.assertEqual(len(queued), 1)
        self.assertNotIn(self.operator.name, queued.payload["text"])
        self.assertEqual(queued.chat_id.business_connection_id, self.connection)

    def test_an_edit_and_a_deletion_follow_the_customer(self):
        _chat, session = self._business("precio de la avena")
        self._business("precio del maíz", message_id=1, kind="edited_business_message")
        customer_message = session.message_ids.filtered(
            lambda m: m.author_id in session.livechat_customer_partner_ids
        )
        self.assertIn("maíz", customer_message.body)

        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._handle_update(
                self.test_bot,
                {
                    "update_id": 7999,
                    "deleted_business_messages": {
                        "business_connection_id": "bc-owner",
                        "chat": {"id": self.CUSTOMER_ID, "type": "private"},
                        "message_ids": [1],
                    },
                },
            )
        self.assertTrue(customer_message._filtered_empty())

    def test_closing_asks_no_rating_in_the_owner_name(self):
        chat, session = self._business("hola")
        session._close_livechat_session()
        self.assertFalse(self._queued(chat))

    def test_the_owner_is_not_notified_of_what_their_phone_showed(self):
        _chat, session = self._business("hola")
        recipient = {"id": self.operator.partner_id.id, "notif": "inbox"}
        self.assertIsNone(session._telegram_notification_kind(recipient))
