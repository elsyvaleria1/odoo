from unittest.mock import Mock, patch

import requests
from psycopg import IntegrityError

from odoo.exceptions import ValidationError

from .common import TelegramBotTestCase
from odoo.addons.telegram.tools.telegram_client import TelegramClient


class TestBotTokenHashing(TelegramBotTestCase):
    def test_token_hash_computed_on_create(self):
        self.assertTrue(self.test_bot.token_hash)
        self.assertEqual(len(self.test_bot.token_hash), 64)

    def test_token_hash_consistency(self):
        hash1 = self.env["telegram.bot"]._hash_token(self.TEST_BOT_TOKEN)
        hash2 = self.env["telegram.bot"]._hash_token(self.TEST_BOT_TOKEN)
        self.assertEqual(hash1, hash2)

    def test_different_tokens_produce_different_hashes(self):
        hash1 = self.env["telegram.bot"]._hash_token("123:ABC")
        hash2 = self.env["telegram.bot"]._hash_token("456:DEF")
        self.assertNotEqual(hash1, hash2)

    def test_find_by_token_returns_correct_bot(self):
        found_bot = self.env["telegram.bot"].find_by_token(self.TEST_BOT_TOKEN)
        self.assertEqual(found_bot, self.test_bot)

    def test_find_by_token_returns_empty_for_invalid(self):
        found_bot = self.env["telegram.bot"].find_by_token("invalid:token")
        self.assertFalse(found_bot)
        self.assertEqual(len(found_bot), 0)

    def test_token_hash_updated_on_credential_change(self):
        old_hash = self.test_bot.token_hash

        telegram_service = self.env.ref("telegram.service_telegram")
        bearer_category = self.env.ref("credential.credential_category_bearer_token")
        new_credential = self.env["credential.credential"].create(
            {
                "name": "Updated Credential",
                "category_id": bearer_category.id,
                "endpoint_id": telegram_service.id,
                "bearer_token": "999888777:NEW-TOKEN-xyz123",
            }
        )

        self.test_bot.write({"credential_id": new_credential.id})
        self.assertNotEqual(self.test_bot.token_hash, old_hash)


class TestTokenRotation(TelegramBotTestCase):
    def test_rotating_the_token_keeps_the_webhook_resolvable(self):
        rotated = "123456789:ROTATEDtokenZZZZZZZZZZZZZZZZZZZZZZ"
        self.test_credential.write({"bearer_token": rotated})
        self.env.flush_all()

        self.assertEqual(
            self.env["telegram.bot"].find_by_token(rotated),
            self.test_bot,
            "token_hash used to be refreshed only when credential_id changed, so "
            "rotating the token behind it left the bot unreachable",
        )
        self.assertFalse(
            self.env["telegram.bot"].find_by_token(self.TEST_BOT_TOKEN),
            "the old token must stop resolving",
        )

    def test_clearing_the_token_clears_the_hash(self):
        self.test_credential.write({"bearer_token": False})
        self.env.flush_all()
        self.assertFalse(self.test_bot.token_hash)

    def test_a_transient_read_failure_keeps_the_hash(self):
        before = self.test_bot.token_hash
        self.assertTrue(before)

        # Cold cache, as any fresh transaction is -- and as the post-migrate
        # recompute is: the decrypt is really attempted and really fails.
        self.env.invalidate_all()
        blow_up = patch.object(
            type(self.test_credential),
            "_compute_credential_accessors",
            side_effect=RuntimeError("decrypt rate limit exceeded"),
        )
        with blow_up:
            self.env.add_to_compute(self.test_bot._fields["token_hash"], self.test_bot)
            self.env.flush_all()

        self.test_bot.invalidate_recordset()
        self.assertEqual(
            self.test_bot.token_hash,
            before,
            "a transient decrypt failure used to store False and mute the bot "
            "for good: the webhook answers 200 to everything, so Telegram "
            "never retries and nothing recomputes the hash again",
        )
        self.assertEqual(
            self.env["telegram.bot"].find_by_token(self.TEST_BOT_TOKEN),
            self.test_bot,
        )


class TestArchivedCredential(TelegramBotTestCase):
    """Archiving the credential is the only non-destructive off switch there
    is: telegram.bot has no active field and credential_id is required with
    ondelete=restrict, so the credential cannot be deleted either."""

    def setUp(self):
        super().setUp()
        self.test_credential.active = False
        self.env.flush_all()

    def test_the_webhook_stops_resolving(self):
        self.assertFalse(self.test_bot._read_token())
        self.assertFalse(self.test_bot.token_hash)
        self.assertFalse(
            self.env["telegram.bot"].find_by_token(self.TEST_BOT_TOKEN),
            "an archived credential used to keep answering the webhook",
        )

    def test_outbound_refuses_instead_of_sending(self):
        with self.assertRaises(ValueError):
            self.test_bot._get_bot_token()

    def test_unarchiving_brings_the_bot_back(self):
        self.test_credential.active = True
        self.env.flush_all()

        self.assertEqual(
            self.env["telegram.bot"].find_by_token(self.TEST_BOT_TOKEN),
            self.test_bot,
        )
        self.assertEqual(self.test_bot._get_bot_token(), self.TEST_BOT_TOKEN)


class TestWebhookSecretEnforcement(TelegramBotTestCase):
    """The webhook receiver's verdict on an update, asked of the gate the
    route admits through, in the mode the bot itself declares."""

    def _admitted(self, headers=None):
        receiver = self.test_bot._get_or_create_webhook_receiver()
        allowed, _status, _reason = receiver._check_inbound_request(
            headers or {}, body=b"{}", remote_addr="149.154.167.220"
        )
        return allowed

    def test_a_legacy_secretless_bot_is_still_accepted_and_flagged_once(self):
        self.test_bot._update_webhook_secret(False)
        self.test_bot.legacy_secretless_webhook = True
        with self.assertLogs(
            "odoo.addons.integration.models.mixin_inbound_gate",
            level="WARNING",
        ) as captured:
            self.assertTrue(self._admitted())
        self.assertTrue(
            any("audit mode" in line for line in captured.output), captured.output
        )
        receiver = self.test_bot.webhook_receiver_id
        self.assertEqual(
            receiver._inbound_verdict(
                {}, body=b"{}", remote_addr="149.154.167.220"
            ).code,
            "audit_accepted",
        )
        self.assertFalse(
            self.env["integration.exchange"].search(
                [("channel_id", "=", f"{receiver._name},{receiver.id}")]
            ),
            "an audit admission is the admission's own row, not a verdict's",
        )

    def test_a_secretless_bot_that_is_not_legacy_is_refused(self):
        self.test_bot._update_webhook_secret(False)
        self.test_bot.legacy_secretless_webhook = False
        self.assertFalse(self._admitted())

    def test_registering_ends_the_legacy_acceptance(self):
        self.test_bot._update_webhook_secret(False)
        self.test_bot.legacy_secretless_webhook = True
        with patch.object(TelegramClient, "_post", return_value={"ok": True}):
            self.test_bot.action_register_webhook()

        self.assertFalse(self.test_bot.legacy_secretless_webhook)
        self.assertFalse(self._admitted())

    def test_a_configured_secret_rejects_a_forged_update(self):
        self.test_bot._update_webhook_secret("s3cret-value")
        self.assertFalse(self._admitted())

    def test_a_configured_secret_accepts_the_matching_header(self):
        self.test_bot._update_webhook_secret("s3cret-value")
        headers = {"X-Telegram-Bot-Api-Secret-Token": "s3cret-value"}
        self.assertTrue(self._admitted(headers))


class TestBotTokenMasking(TelegramBotTestCase):
    def test_token_masked_format(self):
        self.assertTrue(self.test_bot.token_masked)
        self.assertIn("123456789:", self.test_bot.token_masked)
        self.assertIn("***", self.test_bot.token_masked)
        self.assertTrue(self.test_bot.token_masked.endswith("w11"))

    def test_token_masked_without_credential(self):
        self.skipTest(
            "Creating credential without token is no longer allowed by validation"
        )


class TestBotCredentialConstraints(TelegramBotTestCase):
    def test_credential_uniqueness_constraint(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["telegram.bot"].create(
                {
                    "name": "Duplicate Bot",
                    "credential_id": self.test_credential.id,
                }
            )

    def test_different_bots_different_credentials(self):
        telegram_service = self.env.ref("telegram.service_telegram")
        bearer_category = self.env.ref("credential.credential_category_bearer_token")
        new_credential = self.env["credential.credential"].create(
            {
                "name": "Second Bot Credential",
                "category_id": bearer_category.id,
                "endpoint_id": telegram_service.id,
                "bearer_token": "987654321:XYZ-ABC9876def",
            }
        )

        second_bot = self.env["telegram.bot"].create(
            {
                "name": "Second Bot",
                "credential_id": new_credential.id,
            }
        )
        self.assertTrue(second_bot.id)
        self.assertNotEqual(second_bot.token_hash, self.test_bot.token_hash)


class TestWebhookSecretValidation(TelegramBotTestCase):
    def test_webhook_secret_valid_format(self):
        self.test_bot._update_webhook_secret("valid_secret-123")
        self.assertEqual(self.test_bot._webhook_secret().reveal(), "valid_secret-123")

    def test_webhook_secret_alphanumeric_underscore_dash(self):
        valid_secrets = [
            "ABCDEFghij",
            "1234567890",
            "test_secret",
            "test-secret",
            "Test_Secret-123",
        ]
        for secret in valid_secrets:
            self.test_bot._update_webhook_secret(secret)
            self.assertEqual(self.test_bot._webhook_secret().reveal(), secret)

    def test_webhook_secret_invalid_characters_raises_error(self):
        invalid_secrets = [
            "invalid@secret",
            "invalid!secret",
            "invalid secret",
            "invalid#secret",
            "invalid$secret",
        ]
        for secret in invalid_secrets:
            with self.assertRaises(ValidationError):
                self.test_bot._update_webhook_secret(secret)

    def test_webhook_secret_too_long_raises_error(self):
        with self.assertRaises(ValidationError):
            self.test_bot._update_webhook_secret("a" * 257)

    def test_webhook_secret_max_length_accepted(self):
        self.test_bot._update_webhook_secret("a" * 256)
        self.assertEqual(len(self.test_bot._webhook_secret().reveal()), 256)

    def test_webhook_secret_empty_is_allowed(self):
        self.test_bot._update_webhook_secret(False)
        self.assertIsNone(self.test_bot._webhook_secret())


class TestBotSendMessage(TelegramBotTestCase):
    def test_send_message_success(self):
        mock_response = self.mock_telegram_response(
            success=True,
            result={
                "message_id": 123,
                "chat": {"id": "12345"},
                "text": "Test message",
            },
        )

        with self.mock_api_gateway_post(mock_response):
            result = self.test_bot.send_message("12345", "Test message")

        self.assertTrue(result)
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["result"]["message_id"], 123)

    def test_send_message_failure(self):
        mock_response = self.mock_telegram_response(
            success=False,
            error_code=400,
            description="Bad Request: chat not found",
        )

        with self.mock_api_gateway_post(mock_response):
            result = self.test_bot.send_message(self.test_chat.chat_id, "Test message")

        self.assertFalse(result, "a refused send must not report success")
        ledger = self.env["telegram.message"].search(
            [("chat_id", "=", self.test_chat.id)], limit=1
        )
        self.assertEqual(ledger.state, "error")
        self.assertIn("chat not found", ledger.error_message)

    def test_send_message_with_inline_keyboard(self):
        keyboard = [
            [
                {"text": "Button 1", "callback_data": "action1"},
                {"text": "Button 2", "callback_data": "action2"},
            ]
        ]

        mock_response = self.mock_telegram_response(
            success=True,
            result={"message_id": 124},
        )

        with self.mock_api_gateway_post(mock_response):
            result = self.test_bot.send_message(
                "12345",
                "Choose an option:",
                reply_markup={"inline_keyboard": keyboard},
            )

        self.assertTrue(result)
        self.assertEqual(result["ok"], True)

    def test_send_message_network_error(self):
        with self.mock_api_gateway_post() as mock_post:
            mock_post.side_effect = Exception("Network error")
            result = self.test_bot.send_message("12345", "Test")

        self.assertFalse(result)


class TestBotSendDocument(TelegramBotTestCase):
    def test_send_document_success(self):
        document_content = b"PDF content here"
        filename = "test.pdf"

        mock_response = self.mock_telegram_response(
            success=True,
            result={
                "message_id": 125,
                "document": {"file_name": "test.pdf"},
            },
        )

        with self.mock_api_gateway_post(mock_response):
            result = self.test_bot.send_document(
                "12345", document_content, filename, caption="Test document"
            )

        self.assertTrue(result)
        self.assertEqual(result["ok"], True)


class TestBotAnswerCallbackQuery(TelegramBotTestCase):
    def test_answer_callback_query_success(self):
        mock_response = self.mock_telegram_response(success=True, result=True)

        with self.mock_api_gateway_post(mock_response):
            result = self.test_bot.answer_callback_query(
                "callback_query_id_123",
                text="Action completed!",
                show_alert=False,
            )

        self.assertTrue(result)
        self.assertEqual(result["ok"], True)

    def test_answer_callback_query_with_alert(self):
        mock_response = self.mock_telegram_response(success=True, result=True)

        with self.mock_api_gateway_post(mock_response):
            result = self.test_bot.answer_callback_query(
                "callback_query_id_456",
                text="Important notice!",
                show_alert=True,
            )

        self.assertTrue(result)


class TestBotGetFileContent(TelegramBotTestCase):
    def test_get_file_content_success(self):
        file_content = b"File content here"

        get_file_response = self.mock_telegram_response(
            success=True,
            result={
                "file_id": "file123",
                "file_path": "documents/file.pdf",
            },
        )

        mock_download_response = Mock()
        mock_download_response.content = file_content
        mock_download_response.status_code = 200
        mock_download_response.headers = {}
        mock_download_response.raise_for_status = Mock()

        with self.mock_api_gateway_post(get_file_response):
            with patch.object(
                requests.Session,
                "request",
                return_value=mock_download_response,
            ):
                result = self.test_bot.get_file_content("file123")

        self.assertEqual(result, file_content)

    def test_get_file_content_failure(self):
        mock_response = self.mock_telegram_response(
            success=False,
            error_code=400,
            description="Bad Request: invalid file_id",
        )

        with self.mock_api_gateway_post(mock_response):
            result = self.test_bot.get_file_content("invalid_file_id")

        self.assertFalse(result)


class TestBotRelationships(TelegramBotTestCase):
    def test_bot_chats_relationship(self):
        self.assertIn(self.test_chat, self.test_bot.chat_ids)
        self.assertIn(self.unlinked_chat, self.test_bot.chat_ids)
        self.assertEqual(len(self.test_bot.chat_ids), 2)

    def test_bot_commands_relationship(self):
        command = self.env["telegram.command"]._for_name("/testcommand")

        self.test_bot.write({"command_ids": [(4, command.id)]})
        self.assertIn(command, self.test_bot.command_ids)


class TestBotTokenIsUsedNotRevealed(TelegramBotTestCase):
    def test_a_bot_sends_past_the_decrypt_allowance_and_leaves_the_cap_alone(self):
        credential = self._make_bot_credential(
            "Allowance Bot Credential", "111222333:AAA-BBB1234ghIkl-zyx57W2v1u123ew11"
        )
        credential.write(
            {"decrypt_rate_limit_enabled": True, "decrypt_rate_limit_max": 1}
        )
        bot = self.env["telegram.bot"].create(
            {"name": "Allowance Bot", "credential_id": credential.id}
        )
        public = self.env(user=self.env.ref("base.public_user"))

        for _ in range(3):
            self.env.invalidate_all()
            self.assertEqual(
                bot.with_env(public).sudo()._get_bot_token(),
                "111222333:AAA-BBB1234ghIkl-zyx57W2v1u123ew11",
            )
        self.assertEqual(credential.decrypt_rate_limit_max, 1)


class TestBotCredentialService(TelegramBotTestCase):
    def test_a_bot_refuses_a_credential_outside_the_telegram_service(self):
        stray = self.env["credential.credential"].create(
            {
                "name": "Stray Bearer",
                "category_id": self.test_credential.category_id.id,
                "bearer_token": "111222333:AAA-BBB1234ghIkl-zyx57W2v1u123ew11",
            }
        )
        with self.assertRaises(ValidationError):
            self.env["telegram.bot"].create(
                {"name": "Stray Bot", "credential_id": stray.id}
            )
