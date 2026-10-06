from datetime import timedelta

from psycopg import IntegrityError

from odoo import fields
from odoo.exceptions import ValidationError

from .common import TelegramBotTestCase


class TestChatCreation(TelegramBotTestCase):
    def test_create_chat_with_valid_data(self):
        chat = self.env["telegram.chat"].create(
            {"chat_id": "99999", "bot_id": self.test_bot.id}
        )
        self.assertEqual(chat.chat_id, "99999")
        self.assertEqual(chat.bot_id, self.test_bot)
        self.assertFalse(chat.account_id)

    def test_chat_id_bot_id_uniqueness_constraint(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["telegram.chat"].create(
                {"chat_id": self.test_chat.chat_id, "bot_id": self.test_bot.id}
            )

    def test_a_new_chat_has_no_flow(self):
        chat = self.env["telegram.chat"].create(
            {
                "chat_id": "33333",
                "bot_id": self.test_bot.id,
            }
        )
        self.assertFalse(chat.flow_owner)
        self.assertFalse(chat._flow_is_open())


class TestChatFindOrCreate(TelegramBotTestCase):
    def test_find_or_create_existing_chat(self):
        chat = self.env["telegram.chat"]._acquire_chat(
            self.test_chat.chat_id, self.test_bot.id
        )
        self.assertEqual(chat, self.test_chat)

    def test_find_or_create_new_private_chat_records_its_person(self):
        account = self.env["telegram.account"]._from_telegram(
            {"id": 454545, "username": "@New_Find_User"}
        )
        chat = self.env["telegram.chat"]._acquire_chat(
            "454545", self.test_bot.id, chat_type="private", account=account
        )
        self.assertEqual(chat.account_id, account)
        self.assertEqual(account.username, "new_find_user")

    def test_a_group_records_no_person(self):
        account = self.env["telegram.account"]._from_telegram({"id": 454546})
        chat = self.env["telegram.chat"]._acquire_chat(
            "-100454546", self.test_bot.id, chat_type="supergroup", account=account
        )
        self.assertFalse(chat.account_id)

    def test_an_account_keeps_describing_its_owner(self):
        account = self.env["telegram.account"]._from_telegram(
            {"id": 454547, "username": "before", "first_name": "Ana"}
        )
        again = self.env["telegram.account"]._from_telegram(
            {"id": 454547, "username": "after", "first_name": "Ana", "last_name": "R"}
        )
        self.assertEqual(again, account)
        self.assertEqual(account.username, "after")
        self.assertEqual(account.name, "Ana R")

    def test_a_bot_sender_has_no_account(self):
        self.assertFalse(
            self.env["telegram.account"]._from_telegram({"id": 1, "is_bot": True})
        )


class TestChatFlows(TelegramBotTestCase):
    OWNER = "telegram.handler.base"

    def test_start_opens_the_owners_flow_for_its_ttl(self):
        before = fields.Datetime.now()
        self.test_chat._flow_start(self.OWNER, "email_input", {"retries": 0})

        self.assertTrue(self.test_chat._flow_is_open())
        self.assertEqual(self.test_chat.flow_owner, self.OWNER)
        self.assertEqual(self.test_chat.flow_step, "email_input")
        self.assertEqual(self.test_chat.flow_data, {"retries": 0})
        self.assertGreaterEqual(
            self.test_chat.flow_expires_at,
            before + self.env[self.OWNER]._telegram_flow_ttl - timedelta(seconds=1),
        )

    def test_advance_moves_the_step_and_keeps_the_data(self):
        self.test_chat._flow_start(self.OWNER, "one", {"k": "v"})
        self.test_chat._flow_advance("two")

        self.assertEqual(self.test_chat.flow_step, "two")
        self.assertEqual(self.test_chat.flow_data, {"k": "v"})

    def test_update_merges_into_the_data(self):
        self.test_chat._flow_start(self.OWNER, "one", {"k": "v"})
        self.test_chat._flow_update({"n": 1})

        self.assertEqual(self.test_chat.flow_step, "one")
        self.assertEqual(self.test_chat.flow_data, {"k": "v", "n": 1})

    def test_a_chat_without_a_flow_cannot_be_moved(self):
        with self.assertRaises(ValidationError):
            self.test_chat._flow_advance("two")

    def test_end_clears_the_flow(self):
        self.test_chat._flow_start(self.OWNER, "one", {"k": "v"})
        self.test_chat._flow_end()

        self.assertFalse(self.test_chat._flow_is_open())
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_step)
        self.assertFalse(self.test_chat.flow_data)
        self.assertFalse(self.test_chat.flow_expires_at)

    def test_an_expired_flow_counts_as_ended(self):
        self.test_chat._flow_start(self.OWNER, "one")
        self.test_chat.flow_expires_at = fields.Datetime.now() - timedelta(seconds=1)

        self.assertFalse(self.test_chat._flow_is_open())
        self.assertFalse(self.env[self.OWNER]._owns_flow(self.test_chat))
        self.assertFalse(self.env[self.OWNER]._flow_step(self.test_chat))

    def test_a_flow_of_a_handler_no_longer_installed_counts_as_ended(self):
        self.test_chat._flow_start(self.OWNER, "one")
        self.test_chat.flow_owner = "telegram.handler.uninstalled"

        self.assertFalse(self.test_chat._flow_is_open())

    def test_a_handler_ends_only_its_own_flow(self):
        self.test_chat._flow_start(self.OWNER, "one")
        other = self.env["mixin.telegram.handler"]

        other._flow_end(self.test_chat)
        self.assertEqual(self.test_chat.flow_owner, self.OWNER)

        self.env[self.OWNER]._flow_end(self.test_chat)
        self.assertFalse(self.test_chat.flow_owner)

    def test_starting_logs_the_owner_and_step(self):
        with self.assertLogs(
            "odoo.addons.telegram.models.telegram_chat", level="INFO"
        ) as captured:
            self.test_chat._flow_start(self.OWNER, "one")
        self.assertTrue(
            any(self.OWNER in line and "one" in line for line in captured.output),
            f"the log must name the flow, got {captured.output}",
        )


class TestChatContextManagement(TelegramBotTestCase):
    def test_get_context_existing_key(self):
        self.test_chat.context_data = {"test_key": "test_value", "number": 42}
        value = self.test_chat._get_context("test_key")

        self.assertEqual(value, "test_value")

    def test_get_context_nonexistent_key_returns_default(self):
        self.test_chat.context_data = {}
        value = self.test_chat._get_context("nonexistent", default="default_value")

        self.assertEqual(value, "default_value")

    def test_get_context_nonexistent_key_returns_none(self):
        self.test_chat.context_data = {}
        value = self.test_chat._get_context("nonexistent")

        self.assertIsNone(value)

    def test_set_context_new_key(self):
        self.test_chat.context_data = {}
        self.test_chat._set_context("new_key", "new_value")

        self.assertEqual(self.test_chat._get_context("new_key"), "new_value")

    def test_set_context_updates_existing_key(self):
        self.test_chat.context_data = {"existing": "old_value"}
        self.test_chat._set_context("existing", "new_value")

        self.assertEqual(self.test_chat._get_context("existing"), "new_value")

    def test_set_context_preserves_other_keys(self):
        self.test_chat.context_data = {"key1": "value1", "key2": "value2"}
        self.test_chat._set_context("key3", "value3")

        self.assertEqual(self.test_chat._get_context("key1"), "value1")
        self.assertEqual(self.test_chat._get_context("key2"), "value2")
        self.assertEqual(self.test_chat._get_context("key3"), "value3")

    def test_ending_a_flow_leaves_the_parked_context(self):
        self.test_chat.context_data = {"parked": 1}
        self.test_chat._flow_start("telegram.handler.base", "one")
        self.test_chat._flow_end()

        self.assertEqual(self.test_chat.context_data, {"parked": 1})


class TestChatFailedStateTracking(TelegramBotTestCase):
    def test_increment_failed_state(self):
        initial_count = self.test_chat.failed_command_count
        error_msg = "Test error message"

        self.test_chat._increment_failed_state(error_msg)

        self.assertEqual(self.test_chat.failed_command_count, initial_count + 1)
        self.assertEqual(self.test_chat.last_error, error_msg)

    def test_increment_failed_state_truncates_long_error(self):
        long_error = "x" * 300

        self.test_chat._increment_failed_state(long_error)

        self.assertEqual(len(self.test_chat.last_error), 255)

    def test_reset_failed_state(self):
        self.test_chat.write(
            {
                "failed_command_count": 5,
                "last_error": "Some error",
            }
        )

        self.test_chat._reset_failed_state()

        self.assertEqual(self.test_chat.failed_command_count, 0)
        self.assertFalse(self.test_chat.last_error)


class TestChatResetAsInternalUser(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.chat_as_user = self.test_chat.with_user(self.test_user)

    def test_internal_user_has_no_write_access(self):
        self.assertFalse(self.test_user.has_group("base.group_system"))
        self.assertFalse(self.chat_as_user.has_access("write"))

    def test_end_flow_as_internal_user(self):
        self.test_chat._flow_start("telegram.handler.base", "one", {"k": "v"})

        self.chat_as_user._flow_end()

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)

    def test_start_and_move_a_flow_as_internal_user(self):
        self.chat_as_user._flow_start("telegram.handler.base", "one")
        self.chat_as_user._flow_update({"k": "v"})

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "one")
        self.assertEqual(self.test_chat.flow_data, {"k": "v"})


class TestChatRelationships(TelegramBotTestCase):
    def test_partner_relationship(self):
        self.assertEqual(self.test_chat.partner_id, self.test_partner)
        self.assertFalse(self.unlinked_chat.partner_id)

    def test_bot_relationship(self):
        self.assertEqual(self.test_chat.bot_id, self.test_bot)
        self.assertEqual(self.unlinked_chat.bot_id, self.test_bot)
