from unittest.mock import patch

from odoo import SUPERUSER_ID, Command
from odoo.tests import tagged

from ..tools import errors
from ..tools.telegram_client import TelegramClient
from .common import TelegramBotTestCase

_CALL = "odoo.addons.telegram.tools.telegram_client.TelegramClient.call"


def _contact_update(chat_id, from_id, contact_user_id, phone="5215512345678"):
    return {
        "message_id": 5,
        "from": {"id": from_id, "first_name": "Test"},
        "chat": {"id": chat_id, "type": "private"},
        "date": 1,
        "contact": {
            "phone_number": phone,
            "first_name": "Test",
            "user_id": contact_user_id,
        },
    }


class TestSharedPhone(TelegramBotTestCase):
    def _share(self, update):
        handlers = type(self.env["mixin.telegram.handler"])
        with (
            self.mock_api_gateway_post() as post,
            self.mock_rate_limiter(),
            patch.object(handlers, "_on_phone_verified", autospec=True) as heard,
        ):
            self.env["telegram.router"]._dispatch_message(self.test_bot, update)
        return post, heard

    def test_the_own_contact_records_the_number(self):
        _post, heard = self._share(_contact_update("12345", 12345, 12345))

        self.assertEqual(self.test_account.phone, "+5215512345678")
        self.assertTrue(self.test_account.phone_verified_at)
        self.assertTrue(heard.called)
        self.assertEqual(heard.call_args.args[3], self.test_account)

    def test_a_number_with_its_plus_is_recorded_once_prefixed(self):
        self._share(_contact_update("12345", 12345, 12345, phone="+52 55 1234 5678"))

        self.assertEqual(self.test_account.phone, "+525512345678")

    def test_somebody_elses_contact_records_nothing(self):
        post, heard = self._share(_contact_update("12345", 12345, 99999))

        self.assertFalse(self.test_account.phone)
        self.assertFalse(heard.called)
        sent = " ".join(str(call.kwargs or call.args) for call in post.call_args_list)
        self.assertIn("not your own number", sent)

    def test_a_contact_card_without_a_telegram_user_records_nothing(self):
        update = _contact_update("12345", 12345, None)
        self._share(update)

        self.assertFalse(self.test_account.phone)

    def test_the_phone_request_keyboard_shares_the_contact(self):
        message = self.test_bot._queue_phone_request(
            self.test_chat, "Comparte tu número"
        )

        (row,) = message.payload["reply_markup"]["keyboard"]
        self.assertEqual(len(row), 1)
        self.assertTrue(row[0]["request_contact"])
        self.assertIn("phone number", row[0]["text"])
        self.assertTrue(message.payload["reply_markup"]["one_time_keyboard"])


class TestDeliveryHealth(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        for patcher in (
            patch.object(type(self.env["ir.job"]), "_defer", lambda *a, **k: None),
            patch.object(
                type(self.env["telegram.message"]),
                "_consume_send_budget",
                lambda _self: True,
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _deliver(self, side_effect=None, result=None):
        message = self.test_bot._queue_text(self.test_chat, "Hola")
        messages = type(self.env["telegram.message"])
        with (
            patch(_CALL, side_effect=side_effect, return_value=result),
            patch.object(messages, "_on_delivery_failed", autospec=True) as failed,
        ):
            message._deliver()
        return message, failed

    def test_the_first_failure_starts_the_chat_failing(self):
        _message, failed = self._deliver(
            side_effect=errors.TelegramBadRequest(400, "Bad Request: message is empty")
        )

        self.assertTrue(self.test_chat.delivery_failed_at)
        self.assertIn("message is empty", self.test_chat.delivery_error)
        _message_arg, error, started = failed.call_args.args
        self.assertIn("message is empty", error)
        self.assertTrue(started)

    def test_a_later_failure_is_not_a_start(self):
        error = errors.TelegramBadRequest(400, "Bad Request: message is empty")
        self._deliver(side_effect=error)
        since = self.test_chat.delivery_failed_at

        _message, failed = self._deliver(side_effect=error)

        self.assertEqual(self.test_chat.delivery_failed_at, since)
        self.assertFalse(failed.call_args.args[2])

    def test_a_message_that_goes_through_clears_the_failure(self):
        self._deliver(
            side_effect=errors.TelegramBadRequest(400, "Bad Request: message is empty")
        )

        message, failed = self._deliver(result={"message_id": 9})

        self.assertEqual(message.state, "sent")
        self.assertFalse(self.test_chat.delivery_failed_at)
        self.assertFalse(self.test_chat.delivery_error)
        self.assertFalse(failed.called)

    def test_a_refused_deletion_is_no_delivery_failure(self):
        deletion = self.env["telegram.message"]._queue(
            self.test_bot, self.test_chat, "deleteMessage", {"message_id": 5}
        )
        messages = type(self.env["telegram.message"])
        with (
            patch(
                _CALL,
                side_effect=errors.TelegramBadRequest(
                    400, "Bad Request: message can't be deleted"
                ),
            ),
            patch.object(messages, "_on_delivery_failed", autospec=True) as failed,
        ):
            deletion._deliver()

        self.assertEqual(deletion.state, "error")
        self.assertFalse(self.test_chat.delivery_failed_at)
        self.assertFalse(failed.called)

    def test_a_blocked_bot_is_a_failure_and_a_block(self):
        _message, failed = self._deliver(
            side_effect=errors.TelegramForbidden(
                403, "Forbidden: bot was blocked by the user"
            )
        )

        self.assertTrue(self.test_chat.bot_blocked)
        self.assertTrue(self.test_chat.delivery_failed_at)
        self.assertTrue(failed.call_args.args[2])

    def test_a_chat_names_its_person_and_bot_and_its_number_on_request(self):
        self.test_bot.bot_username = "acme_bot"
        self.test_account.sudo().phone = "+525512345678"

        self.assertEqual(self.test_chat.display_name, "Test · @acme_bot")
        self.assertEqual(
            self.test_chat.with_context(telegram_show_phone=True).display_name,
            "Test (+525512345678) · @acme_bot",
        )


class TestConnectingHook(TelegramBotTestCase):
    def test_binding_through_start_tells_every_handler(self):
        self.test_bot.bot_username = "test_bot"
        token = (
            self.env["telegram.link.token"]
            .with_user(self.test_user)
            ._issue_for_session(self.test_bot)
        )
        update = {
            "message_id": 1,
            "from": {"id": 880011, "first_name": "Nuevo"},
            "chat": {"id": 880011, "type": "private"},
            "date": 1,
            "text": f"/start {token}",
        }
        handlers = type(self.env["mixin.telegram.handler"])
        with (
            self.mock_api_gateway_post(),
            self.mock_rate_limiter(),
            patch.object(handlers, "_on_account_bound", autospec=True) as bound,
        ):
            self.env["telegram.router"]._dispatch_message(self.test_bot, update)

        self.assertTrue(bound.called)
        _handler, bot, chat, binding = bound.call_args.args
        self.assertEqual(bot, self.test_bot)
        self.assertEqual(chat.chat_id, "880011")
        self.assertEqual(binding.user_id, self.test_user)


@tagged("post_install", "-at_install")
class TestConnectBot(TelegramBotTestCase):
    def test_a_bot_of_another_company_is_not_offered(self):
        other = self.env["res.company"].create({"name": "TG Connect Other"})
        self.test_bot.bot_username = "main_bot"
        other_bot = self.env["telegram.bot"].create(
            {
                "name": "Other Bot",
                "company_id": other.id,
                "credential_id": self._make_bot_credential(
                    "Other Connect Credential",
                    "323456789:XYZ-DEF1234ghIkl-zyx57W2v1u123ew33",
                ).id,
            }
        )
        other_bot.bot_username = "other_bot"
        self.test_user.write({"company_ids": [Command.link(self.env.company.id)]})

        offered = self.test_user.with_user(self.test_user).telegram_connect_bot_ids

        self.assertIn(self.test_bot, offered)
        self.assertNotIn(other_bot, offered)


class TestChatSearch(TelegramBotTestCase):
    def test_a_chat_is_found_by_its_number_and_its_bot(self):
        self.test_bot.bot_username = "acme_bot"
        self.test_account.sudo().phone = "+525598765432"
        chats = self.env["telegram.chat"]

        self.assertIn(
            self.test_chat, chats.search([("display_name", "ilike", "98765")])
        )
        self.assertIn(
            self.test_chat, chats.search([("display_name", "ilike", "acme_bot")])
        )
        self.assertNotIn(
            self.test_chat, chats.search([("display_name", "ilike", "no-such-chat")])
        )


class TestBotTokenStorage(TelegramBotTestCase):
    def test_a_token_kept_as_the_secret_value_is_read(self):
        credential = self.env["credential.credential"].create(
            {
                "name": "Simple Bot Credential",
                "category_id": self.env.ref(
                    "credential.credential_category_bearer_token"
                ).id,
                "endpoint_id": self.env.ref("telegram.service_telegram").id,
                "credential_value": "423456789:XYZ-DEF1234ghIkl-zyx57W2v1u123ew99",
            }
        )
        bot = self.env["telegram.bot"].create(
            {"name": "Simple Bot", "credential_id": credential.id}
        )

        self.assertEqual(
            bot._get_bot_token(), "423456789:XYZ-DEF1234ghIkl-zyx57W2v1u123ew99"
        )
        self.assertEqual(bot._telegram_id(), "423456789")

    def test_a_token_kept_as_bearer_token_is_read(self):
        self.assertEqual(self.test_bot._get_bot_token(), self.TEST_BOT_TOKEN)

    def _bot_without_token(self):
        credential = self.env["credential.credential"].create(
            {
                "name": "Later Bot Credential",
                "category_id": self.env.ref(
                    "credential.credential_category_bearer_token"
                ).id,
                "endpoint_id": self.env.ref("telegram.service_telegram").id,
            }
        )
        return self.env["telegram.bot"].create(
            {"name": "Later Bot", "credential_id": credential.id}
        )

    def test_a_secret_value_saved_later_names_the_bot_s_webhook(self):
        bot = self._bot_without_token()
        self.assertFalse(bot.token_hash)
        token = "523456789:XYZ-DEF1234ghIkl-zyx57W2v1u123ew98"

        bot.credential_id.credential_value = token

        self.assertEqual(bot.token_hash, bot._hash_token(token))
        self.assertEqual(self.env["telegram.bot"].find_by_token(token), bot)
        self.assertTrue(bot.token_masked.startswith("523456789:"))

    def test_registering_never_hands_telegram_a_url_that_names_no_bot(self):
        bot = self._bot_without_token()
        token = "623456789:XYZ-DEF1234ghIkl-zyx57W2v1u123ew97"
        bot.credential_id.credential_value = token
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE telegram_bot SET token_hash = NULL WHERE id = %s", (bot.id,)
        )
        bot.invalidate_recordset(["token_hash"])

        urls = []
        with (
            patch.object(
                TelegramClient,
                "set_webhook",
                autospec=True,
                side_effect=lambda client, url, secret: urls.append(url) or True,
            ),
            patch.object(type(bot), "_read_identity", autospec=True),
        ):
            bot.action_register_webhook()

        self.assertEqual(
            urls, [f"{bot.get_base_url()}/telegram/webhook/{bot._hash_token(token)}"]
        )

    def test_registering_a_bot_without_a_token_is_refused(self):
        bot = self._bot_without_token()

        with patch.object(TelegramClient, "set_webhook", autospec=True) as set_webhook:
            with self.assertRaises(ValueError):
                bot.action_register_webhook()

        self.assertFalse(set_webhook.called)


class TestOutboxRunner(TelegramBotTestCase):
    def _run(self, message):
        job = (
            self.env["ir.job"]
            .sudo()
            .search([("identity_key", "=", f"telegram.message:{message.id}")])
        )
        with (
            patch(_CALL, return_value={"message_id": 51}),
            patch.object(
                type(self.env["telegram.message"]),
                "_consume_send_budget",
                lambda _self: True,
            ),
        ):
            job.action_run_now()
        return job

    def test_a_message_queued_as_the_public_user_is_sent(self):
        public = self.env.ref("base.public_user")
        bot = self.test_bot.with_user(public)

        message = bot._queue_text(self.unlinked_chat.with_user(public), "Hola")
        job = self._run(message)

        self.assertEqual(job.user_id.id, SUPERUSER_ID)
        self.assertEqual(message.sudo().state, "sent")

    def test_a_message_queued_by_a_user_runs_as_that_user(self):
        message = self.test_bot.with_user(self.test_user)._queue_text(
            self.test_chat, "Hola"
        )
        job = self._run(message)

        self.assertEqual(job.user_id, self.test_user)
        self.assertEqual(message.sudo().state, "sent")
