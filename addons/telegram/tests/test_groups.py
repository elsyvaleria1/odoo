from unittest.mock import patch

from .common import TelegramBotTestCase

GROUP_ID = -4001


class GroupCase(TelegramBotTestCase):
    def _group_message(self, text="hola", sender=12345, **extra):
        return {
            "message_id": extra.pop("message_id", 1),
            "from": {"id": sender, "first_name": "Ana"},
            "chat": {"id": extra.pop("chat_id", GROUP_ID), "type": "group"},
            "date": 1234567890,
            "text": text,
            **extra,
        }

    def _dispatch(self, message, admin_status="administrator"):
        with (
            self.mock_api_gateway_post(),
            self.mock_rate_limiter(),
            patch.object(
                type(self.test_bot),
                "_is_chat_administrator",
                lambda bot, chat, uid: admin_status in ("creator", "administrator"),
            ),
            patch.object(type(self.test_bot), "send_message") as send,
        ):
            self.env["telegram.router"]._dispatch_message(self.test_bot, message)
        return send


class TestMigration(GroupCase):
    def test_the_old_group_learns_its_supergroup_and_keeps_its_history(self):
        self._dispatch(self._group_message("antes"))
        group = self.env["telegram.chat"].search([("chat_id", "=", str(GROUP_ID))])
        self._dispatch(self._group_message(text="", migrate_to_chat_id=-1004001))

        supergroup = group.migrated_to_id
        self.assertEqual(supergroup.chat_id, "-1004001")
        self.assertEqual(supergroup.chat_type, "supergroup")
        self.assertEqual(group.chat_id, str(GROUP_ID))
        self.assertTrue(
            self.env["telegram.message"].search([("chat_id", "=", group.id)])
        )

    def test_either_side_of_the_migration_records_it_once(self):
        self._dispatch(
            self._group_message(
                text="", chat_id=-1004001, migrate_from_chat_id=GROUP_ID
            )
        )
        self._dispatch(self._group_message(text="", migrate_to_chat_id=-1004001))
        group = self.env["telegram.chat"].search([("chat_id", "=", str(GROUP_ID))])
        self.assertEqual(
            self.env["telegram.chat"].search_count([("chat_id", "=", "-1004001")]), 1
        )
        self.assertEqual(group.migrated_to_id.chat_id, "-1004001")


class TestGroupLink(GroupCase):
    def _token(self, purpose="group", user=None):
        tokens = self.env["telegram.link.token"].with_user(user or self.test_user)
        if purpose == "group":
            return tokens._issue_group_link(self.test_bot, self.test_partner)
        return tokens._issue_for_session(self.test_bot)

    def _link(self, token, **kwargs):
        return self._link_text(f"/start {token}", **kwargs)

    def _link_text(self, text, **kwargs):
        seen = []

        def hook(handler, bot, chat, link, account):
            seen.append((chat, link, account))
            return True

        with patch.object(
            type(self.env["telegram.handler.base"]), "_on_group_link", hook
        ):
            send = self._dispatch(self._group_message(text), **kwargs)
        return seen, send

    def test_the_link_s_own_user_as_administrator_connects_the_group(self):
        seen, _send = self._link(self._token())
        chat, link, account = seen[0]
        self.assertEqual(chat.chat_id, str(GROUP_ID))
        self.assertEqual(
            (link.res_model, link.res_id), ("res.partner", self.test_partner.id)
        )
        self.assertEqual(account, self.test_account)

    def test_a_link_works_once(self):
        token = self._token()
        self._link(token)
        seen, send = self._link(token)
        self.assertFalse(seen)
        self.assertIn("expired", send.call_args.args[1])

    def test_someone_else_cannot_use_the_link(self):
        other = self.env["res.users"].create({"name": "Otro", "login": "otro_tg"})
        seen, send = self._link(self._token(user=other))
        self.assertFalse(seen)
        self.assertIn("Only the Odoo user", send.call_args.args[1])

    def test_a_member_who_is_not_administrator_cannot(self):
        seen, send = self._link(self._token(), admin_status="member")
        self.assertFalse(seen)
        self.assertIn("administrator", send.call_args.args[1])

    def test_a_command_for_another_bot_is_not_ours(self):
        self.test_bot.bot_username = "odoo_test_bot"
        seen, send = self._link_text(f"/start@other_bot {self._token()}")
        self.assertFalse(seen)
        self.assertFalse(send.called)

    def test_a_command_naming_this_bot_is(self):
        self.test_bot.bot_username = "odoo_test_bot"
        seen, _send = self._link_text(f"/start@Odoo_Test_Bot {self._token()}")
        self.assertTrue(seen)

    def test_an_account_token_does_not_connect_a_group(self):
        seen, _send = self._link(self._token(purpose="bind"))
        self.assertFalse(seen)

    def test_a_group_token_does_not_bind_an_account(self):
        token = self._token()
        link = (
            self.env["telegram.link.token"]
            .sudo()
            ._consume(self.test_bot, token, self.test_account)
        )
        self.assertFalse(link)
