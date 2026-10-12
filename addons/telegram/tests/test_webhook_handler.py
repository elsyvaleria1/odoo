from unittest.mock import patch

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import tagged
from odoo.tools import consteq

from .common import TelegramBotHttpCase, TelegramBotTestCase


@tagged("post_install", "-at_install")
class WebhookRouteCase(TelegramBotHttpCase):
    def _post(self, token=None, data=None, headers=None, body=None):
        self.env.flush_all()
        if body is None:
            body = json_dumps_bytes(
                data
                if data is not None
                else {"message": self.mock_telegram_message(text="/start")}
            )
        with patch.object(
            type(self.env["telegram.router"]), "_handle_update"
        ) as handled:
            response = self.url_open(
                f"/telegram/webhook/{token or self.TEST_BOT_TOKEN}",
                data=body,
                method="POST",
                headers={"Content-Type": "application/json", **(headers or {})},
            )
        return response, handled

    def _assert_answered_not_handled(self, response, handled):
        self.assertEqual((response.status_code, response.text), (200, "OK"))
        handled.assert_not_called()


class TestWebhookTokenValidation(WebhookRouteCase):
    def test_a_valid_token_routes_to_its_bot(self):
        self.test_bot._update_webhook_secret(False)
        self.test_bot.sudo().legacy_secretless_webhook = True

        response, handled = self._post()

        self.assertEqual(response.status_code, 200)
        handled.assert_called_once()
        self.assertEqual(handled.call_args.args[0], self.test_bot)

    def test_an_unknown_token_is_answered_and_recorded_without_the_token(self):
        token = "999999999:unknown-token-for-the-access-log"

        response, handled = self._post(token=token)

        self._assert_answered_not_handled(response, handled)
        row = self.env["integration.exchange"].search(
            [
                ("state", "=", "refused"),
                ("refusal_reason", "=", "endpoint_not_found"),
                ("channel_name", "like", "telegram.bot:%"),
            ],
            limit=1,
        )
        self.assertTrue(row)
        self.assertNotIn(token, row.channel_name)
        self.assertNotIn(token, row.error_message)
        self.assertTrue(row.channel_name.startswith("telegram.bot: token sha256:"))


class TestWebhookSecretValidation(WebhookRouteCase):
    SECRET = {"X-Telegram-Bot-Api-Secret-Token": "test_secret_123"}

    def setUp(self):
        super().setUp()
        self.test_bot._update_webhook_secret("test_secret_123")

    def test_the_secret_admits_the_update(self):
        response, handled = self._post(headers=self.SECRET)
        self.assertEqual(response.status_code, 200)
        handled.assert_called_once()

    def test_a_wrong_secret_is_answered_and_not_handled(self):
        response, handled = self._post(
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"}
        )
        self._assert_answered_not_handled(response, handled)

    def test_a_missing_secret_is_answered_and_not_handled(self):
        response, handled = self._post()
        self._assert_answered_not_handled(response, handled)

    def test_a_bot_with_no_secret_refuses_unless_it_is_legacy(self):
        self.test_bot._update_webhook_secret(False)

        response, handled = self._post()
        self._assert_answered_not_handled(response, handled)

        self.test_bot.sudo().legacy_secretless_webhook = True
        response, handled = self._post()
        self.assertEqual(response.status_code, 200)
        handled.assert_called_once()

    def test_a_non_ascii_secret_is_answered_and_not_handled(self):
        response, handled = self._post(
            headers={"X-Telegram-Bot-Api-Secret-Token": "test_secret_12é"}
        )
        self._assert_answered_not_handled(response, handled)

    def test_the_secret_is_compared_in_constant_time(self):
        with patch(
            "odoo.addons.telegram.models.telegram_bot_receiver.consteq",
            wraps=consteq,
        ) as compare:
            response, handled = self._post(headers=self.SECRET)

        compare.assert_called_once()
        presented, expected = compare.call_args.args
        self.assertEqual(presented, "test_secret_123")
        self.assertTrue(expected.matches("test_secret_123"))
        self.assertEqual(response.status_code, 200)
        handled.assert_called_once()


class TestWebhookBodyParsing(WebhookRouteCase):
    def setUp(self):
        super().setUp()
        self.test_bot._update_webhook_secret("test_secret_123")
        self.headers = {"X-Telegram-Bot-Api-Secret-Token": "test_secret_123"}

    def test_an_empty_body_is_answered_and_not_handled(self):
        response, handled = self._post(body=b"", headers=self.headers)
        self._assert_answered_not_handled(response, handled)

    def test_invalid_json_is_answered_and_not_handled(self):
        response, handled = self._post(body=b"not valid json", headers=self.headers)
        self._assert_answered_not_handled(response, handled)

    def test_json_that_is_not_an_object_is_answered_and_not_handled(self):
        response, handled = self._post(body=b"[1, 2, 3]", headers=self.headers)
        self._assert_answered_not_handled(response, handled)

    def test_an_update_past_the_size_cap_is_answered_but_never_handled(self):
        receiver = self.test_bot._get_or_create_webhook_receiver()
        body = b"{" + b" " * receiver.max_payload_size + b"}"

        response, handled = self._post(body=body, headers=self.headers)

        self._assert_answered_not_handled(response, handled)


class TestWebhookMessageDispatch(WebhookRouteCase):
    def setUp(self):
        super().setUp()
        self.test_bot._update_webhook_secret("test_secret_123")
        self.headers = {"X-Telegram-Bot-Api-Secret-Token": "test_secret_123"}

    def _exchanges(self):
        receiver = self.test_bot._get_or_create_webhook_receiver()
        return self.env["integration.exchange"].search(
            [("channel_id", "=", f"integration.receiver,{receiver.id}")], order="id"
        )

    def test_a_message_reaches_the_handler_and_its_row_says_message(self):
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id, text="/start"
        )
        response, handled = self._post(data={"message": message}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(handled.call_args.args[1], {"message": message})
        row = self._exchanges()
        self.assertEqual(len(row), 1)
        self.assertEqual((row.event_type, row.state), ("message", "success"))

    def test_a_callback_query_reaches_the_handler(self):
        callback_query = self.mock_telegram_callback_query(
            chat_id=self.test_chat.chat_id, callback_data="test_action"
        )
        response, handled = self._post(
            data={"callback_query": callback_query}, headers=self.headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(handled.call_args.args[1], {"callback_query": callback_query})
        self.assertEqual(self._exchanges().event_type, "callback_query")

    def test_a_message_is_processed_end_to_end(self):
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id, text="/start"
        )
        self.env.flush_all()
        with self.mock_api_gateway_post() as post:
            response = self.url_open(
                f"/telegram/webhook/{self.TEST_BOT_TOKEN}",
                data=json_dumps_bytes({"message": message}),
                headers={"Content-Type": "application/json", **self.headers},
            )

        self.assertEqual((response.status_code, response.text), (200, "OK"))
        self.assertTrue(post.called, "the bot answered /start")


class TestWebhookErrorHandling(WebhookRouteCase):
    def test_an_infrastructure_failure_propagates_for_redelivery(self):
        self.test_bot._update_webhook_secret("test_secret_123")
        message = self.mock_telegram_message(text="/start")
        self.env.flush_all()
        with patch.object(
            type(self.env["telegram.router"]),
            "_dispatch_message",
            side_effect=OSError("transient: connection reset"),
        ):
            response = self.url_open(
                f"/telegram/webhook/{self.TEST_BOT_TOKEN}",
                data=json_dumps_bytes({"update_id": 424242, "message": message}),
                headers={
                    "Content-Type": "application/json",
                    "X-Telegram-Bot-Api-Secret-Token": "test_secret_123",
                },
            )

        self.assertEqual(response.status_code, 500)
        with patch.object(
            type(self.env["telegram.router"]), "_handle_update"
        ) as handled:
            again = self.url_open(
                f"/telegram/webhook/{self.TEST_BOT_TOKEN}",
                data=json_dumps_bytes({"update_id": 424242, "message": message}),
                headers={
                    "Content-Type": "application/json",
                    "X-Telegram-Bot-Api-Secret-Token": "test_secret_123",
                },
            )
        self.assertEqual(again.status_code, 200)
        handled.assert_called_once()

    def test_a_redelivered_update_is_answered_and_not_handled_again(self):
        self.test_bot._update_webhook_secret("test_secret_123")
        message = self.mock_telegram_message(text="/start")
        update = {"update_id": 515151, "message": message}
        headers = {"X-Telegram-Bot-Api-Secret-Token": "test_secret_123"}

        first, handled = self._post(data=update, headers=headers)
        handled.assert_called_once()
        second, handled = self._post(data=update, headers=headers)

        self._assert_answered_not_handled(second, handled)
        self.assertEqual(first.status_code, 200)
        rows = self.env["integration.exchange"].search(
            [("event_id_external", "=", "515151")]
        )
        self.assertEqual(rows.mapped("state"), ["success"], "one row claims it")


class TestWebhookByTokenHash(WebhookRouteCase):
    def test_a_hash_with_the_secret_routes_to_its_bot(self):
        self.test_bot._update_webhook_secret("hash_secret_1")
        response, handled = self._post(
            token=self.test_bot.token_hash,
            headers={"X-Telegram-Bot-Api-Secret-Token": "hash_secret_1"},
        )
        self.assertEqual(response.status_code, 200)
        handled.assert_called_once()
        self.assertEqual(handled.call_args.args[0], self.test_bot)

    def test_a_hash_without_the_secret_is_refused(self):
        self.test_bot._update_webhook_secret("hash_secret_1")
        response, handled = self._post(token=self.test_bot.token_hash)
        self._assert_answered_not_handled(response, handled)

    def test_a_hash_is_refused_for_a_bot_that_does_not_enforce_a_secret(self):
        self.test_bot._update_webhook_secret(False)
        self.test_bot.sudo().legacy_secretless_webhook = True
        response, handled = self._post(token=self.test_bot.token_hash)
        self._assert_answered_not_handled(response, handled)


class TestWebhookBotMessageFiltering(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_dispatch_message_filters_bot_messages(self):
        message = self.mock_telegram_message(text="/start", is_bot=True)

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.controller._dispatch_message(self.test_bot, message)

            self.assertFalse(
                mock_post.called,
                "No message should be sent when incoming message is from a bot",
            )


class TestWebhookRateLimiting(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_dispatch_message_checks_rate_limit(self):
        self.test_chat.write(
            {
                "rate_limit_enabled": True,
                "rate_limit_requests": 5,
            }
        )

        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text="/start",
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_rate_limiter(is_allowed=False):
            with self.mock_api_gateway_post(mock_response) as mock_post:
                self.controller._dispatch_message(self.test_bot, message)

                self.assertTrue(mock_post.called)


class TestGetChatAndUser(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_acquire_chat_and_identity_from_message(self):
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            from_user={"id": 12345, "username": "testuser", "is_bot": False},
        )

        chat, partner, internal_user = self.controller._acquire_chat_and_identity(
            self.test_bot, message
        )

        self.assertEqual(chat.chat_id, self.test_chat.chat_id)
        self.assertEqual(partner, self.test_partner)
        self.assertEqual(internal_user, self.test_user)

    def test_acquire_chat_and_identity_from_callback_query(self):
        callback_query = self.mock_telegram_callback_query(
            chat_id=self.test_chat.chat_id,
            from_user={"id": 12345, "username": "testuser", "is_bot": False},
        )

        chat, partner, _internal_user = self.controller._acquire_chat_and_identity(
            self.test_bot, callback_query
        )

        self.assertEqual(chat.chat_id, self.test_chat.chat_id)
        self.assertEqual(partner, self.test_partner)


class TestCommandParsing(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_command_token_drops_the_bot_suffix(self):
        command, args = self.controller._split_command("/ayuda@MyBot")
        self.assertEqual(command, "/ayuda")
        self.assertEqual(args, [])

    def test_command_token_ignores_non_breaking_spaces(self):
        command, _args = self.controller._split_command("/start\xa0now")
        self.assertEqual(command, "/start")

    def test_command_token_strips_trailing_punctuation(self):
        command, _args = self.controller._split_command("/ayuda.")
        self.assertEqual(command, "/ayuda")

    def test_arguments_keep_their_punctuation(self):
        _command, args = self.controller._split_command("/nueva Revisar la bomba!")
        self.assertEqual(
            args,
            ["Revisar", "la", "bomba!"],
            "the sanitiser used to strip trailing '.' and '!' off the whole line, "
            "quietly editing the text handed to the AI wizards",
        )

    def test_arguments_keep_a_trailing_period(self):
        _command, args = self.controller._split_command("/estadocuenta ACME S.A.")
        self.assertEqual(args, ["ACME", "S.A."])

    def test_empty_message_yields_no_command(self):
        self.assertEqual(self.controller._normalize_command_token(""), "")
        self.assertEqual(self.controller._normalize_command_token(None), "")
