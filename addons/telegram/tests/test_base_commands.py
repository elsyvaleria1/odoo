from .common import TelegramBotTestCase


class TestStartCommand(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_start_command_sends_welcome(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.env["telegram.handler.base"]._handle_start_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=False,
            )

            self.assertTrue(mock_post.called)
            call_args = mock_post.call_args
            payload = call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertTrue(
                "Bienvenido" in text or "Welcome" in text,
                f"Expected welcome message, got: {text}",
            )
            self.assertIn(self.test_bot.name, text)

    def test_start_command_works_for_unlinked_user(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.env["telegram.handler.base"]._handle_start_command(
                self.test_bot,
                self.unlinked_chat,
                [],
                partner=False,
                internal_user=False,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertTrue(
                "Bienvenido" in text or "Welcome" in text,
                f"Expected welcome message for unlinked user, got: {text}",
            )


class TestHelpCommand(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_help_command_sends_message(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.env["telegram.handler.base"]._handle_help_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=False,
            )

            self.assertTrue(mock_post.called)
            call_args = mock_post.call_args
            payload = call_args.kwargs.get("json", {})
            self.assertIn("General Commands", payload["text"])

    def test_help_shows_quiensoy_for_partner(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.env["telegram.handler.base"]._handle_help_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=False,
            )

            call_args = mock_post.call_args
            payload = call_args.kwargs.get("json", {})
            self.assertIn("quiensoy", payload["text"])


class TestWhoamiCommand(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_whoami_internal_user(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.env["telegram.handler.base"]._handle_whoami_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            call_args = mock_post.call_args
            payload = call_args.kwargs.get("json", {})
            self.assertIn(self.test_user.name, payload["text"])
            self.assertIn(self.test_user.login, payload["text"])

    def test_whoami_partner_only(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.env["telegram.handler.base"]._handle_whoami_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=False,
            )

            self.assertTrue(mock_post.called)
            call_args = mock_post.call_args
            payload = call_args.kwargs.get("json", {})
            self.assertIn(self.test_partner.name, payload["text"])


class TestNonCommandMessage(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_non_command_message_default_handler(self):
        message = self.mock_telegram_message(
            text="Hello", chat_id=self.test_chat.chat_id
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.controller._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                internal_user=False,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertTrue(
                "ayuda" in text.lower() or "command" in text.lower(),
                f"Expected message mentioning commands/ayuda, got: {text}",
            )

    def test_non_command_message_during_active_flow(self):
        self.test_chat._flow_start("telegram.handler.base", "other")
        message = self.mock_telegram_message(
            text="Hola", chat_id=self.test_chat.chat_id
        )
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.controller._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                internal_user=False,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn(
                "in progress",
                text,
                f"Expected the flow-busy notice naming the active flow, got: {text}",
            )
            self.assertTrue(
                payload.get("reply_markup"),
                "The flow-busy notice must carry its way-out keyboard",
            )
            self.assertNotIn("Tap the button", text)

    def test_non_command_message_idle_keeps_generic_notice(self):
        self.test_chat._flow_end()
        message = self.mock_telegram_message(
            text="Hola", chat_id=self.test_chat.chat_id
        )
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.controller._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                internal_user=False,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            self.assertIn("/ayuda", payload.get("text", ""))
            self.assertNotIn("en proceso", payload.get("text", ""))


class TestCallbackQuery(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_callback_query_default_handler(self):
        callback_query = self.mock_telegram_callback_query(
            chat_id=self.test_chat.chat_id,
            callback_data="test_action",
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.controller._dispatch_callback_query(self.test_bot, callback_query)

            calls = {
                call.args[0].rsplit("/", 1)[-1]: call.kwargs.get("json", {})
                for call in mock_post.call_args_list
            }
            text = calls["sendMessage"].get("text", "").lower()
            self.assertTrue(
                "action" in text or "acción" in text or "process" in text,
                f"Expected message about unknown action, got: {text}",
            )
            self.assertIn(
                "answerCallbackQuery",
                calls,
                "an unhandled button press is still answered: the client's "
                "spinner stops",
            )
