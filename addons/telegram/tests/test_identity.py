from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import TelegramBotTestCase


def _update(chat_id, chat_type, from_id, username="someone", text="/quiensoy"):
    return {
        "message_id": 1,
        "from": {"id": from_id, "username": username, "first_name": "Someone"},
        "chat": {"id": chat_id, "type": chat_type},
        "date": 1,
        "text": text,
    }


class IdentityCase(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def _resolve(self, update):
        return self.controller._acquire_chat_and_identity(self.test_bot, update)

    def _account(self, tg_user_id, username="someone"):
        return self.env["telegram.account"]._from_telegram(
            {"id": tg_user_id, "username": username, "first_name": "Someone"}
        )


class TestWhoAnUpdateActsAs(IdentityCase):
    def test_the_bound_sender_acts_as_its_user(self):
        chat, partner, user = self._resolve(_update("12345", "private", 12345))

        self.assertEqual(chat, self.test_chat)
        self.assertEqual(partner, self.test_partner)
        self.assertEqual(user, self.test_user)

    def test_a_private_chat_records_its_person(self):
        chat, partner, user = self._resolve(_update("777001", "private", 777001))

        self.assertEqual(chat.account_id.tg_user_id, "777001")
        self.assertFalse(partner)
        self.assertFalse(user)

    def test_claiming_a_bound_username_claims_nothing(self):
        _chat, partner, user = self._resolve(
            _update("777002", "private", 777002, username="testuser")
        )

        self.assertFalse(partner)
        self.assertFalse(user)

    def test_a_group_serves_a_bound_member_as_unlinked(self):
        chat, partner, user = self._resolve(_update("-100500", "supergroup", 12345))

        self.assertFalse(chat.account_id)
        self.assertFalse(partner)
        self.assertFalse(user)

    def test_a_chat_first_seen_outbound_adopts_its_person_later(self):
        chat = self.env["telegram.chat"]._acquire_chat("12346", self.test_bot.id)
        self.assertFalse(chat.account_id)

        chat_after, _partner, _user = self._resolve(_update("12346", "private", 12346))

        self.assertEqual(chat_after, chat)
        self.assertEqual(chat.account_id.tg_user_id, "12346")

    def test_one_account_serves_every_bot(self):
        other_bot = self.env["telegram.bot"].create(
            {
                "name": "Other Bot",
                "credential_id": self._make_bot_credential(
                    "Other", "987654321:ZYX-other-token-abcdefghij"
                ).id,
            }
        )
        chat, partner, user = self.env["telegram.router"]._acquire_chat_and_identity(
            other_bot, _update("12345", "private", 12345)
        )

        self.assertEqual(chat.account_id, self.test_account)
        self.assertEqual(partner, self.test_partner)
        self.assertEqual(user, self.test_user)

    def test_a_revoked_binding_acts_as_nobody(self):
        self.test_binding._revoke("admin")

        _chat, partner, user = self._resolve(_update("12345", "private", 12345))

        self.assertFalse(partner)
        self.assertFalse(user)

    def test_an_expired_binding_acts_as_nobody_before_the_cron_runs(self):
        account = self._account(555001)
        account._bind(
            self.test_partner,
            method="migration",
            expires_at=fields.Datetime.now() - timedelta(minutes=1),
        )

        self.assertFalse(account._acting_user("internal"))
        self.assertFalse(account._acting_partner())

    def test_the_cron_revokes_expired_bindings(self):
        account = self._account(555002)
        binding = account._bind(
            self.test_partner,
            method="migration",
            expires_at=fields.Datetime.now() - timedelta(minutes=1),
        )

        self.env["telegram.binding"]._cron_expire()

        self.assertEqual(binding.state, "revoked")
        self.assertEqual(binding.revoked_reason, "expired")

    def test_a_contact_binding_acts_as_the_contacts_one_internal_user(self):
        account = self._account(555003)
        account._bind(self.test_partner, method="invitation")

        self.assertEqual(account._acting_user("internal"), self.test_user)

    def test_a_contact_with_two_internal_users_acts_as_neither(self):
        self.env["res.users"].create(
            {
                "name": "Second",
                "login": "second@example.com",
                "partner_id": self.test_partner.id,
            }
        )
        account = self._account(555004)
        account._bind(self.test_partner, method="invitation")

        self.assertFalse(account._acting_user("internal"))
        self.assertEqual(account._acting_partner(), self.test_partner)

    def test_a_portal_user_is_not_an_internal_user(self):
        portal_partner = self._create_partner({"name": "Portal Person"})
        portal = self.env["res.users"].create(
            {
                "name": "Portal Person",
                "login": "portal@example.com",
                "partner_id": portal_partner.id,
                "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            }
        )
        account = self._account(555005)
        account._bind(portal_partner, user=portal, method="session")

        self.assertFalse(account._acting_user("internal"))
        self.assertEqual(account._acting_user("portal"), portal)


class TestBindingLifecycle(IdentityCase):
    def test_a_binding_is_journaled(self):
        events = self.env["telegram.binding.event"].search(
            [("binding_ref", "=", self.test_binding.id)]
        )
        self.assertEqual(events.mapped("event"), ["proven"])
        self.assertTrue(
            self.env["auth.event"]
            .sudo()
            .search_count(
                [
                    ("event", "=", "credential_issued"),
                    ("model_name", "=", "telegram.binding"),
                    ("credential_ref", "=", self.test_binding.id),
                ]
            )
        )

    def test_revoking_is_journaled_and_terminal(self):
        self.test_binding._revoke("user")

        self.assertEqual(
            self.env["telegram.binding.event"]
            .search([("binding_ref", "=", self.test_binding.id)])
            .mapped("event"),
            ["revoked", "proven"],
        )
        with self.assertRaises(AccessError):
            self.test_binding.write({"state": "active"})

    def test_a_binding_never_changes_whom_it_binds(self):
        other = self._create_partner({"name": "Other"})
        with self.assertRaises(AccessError):
            self.test_binding.write({"partner_id": other.id})

    def test_a_binding_is_never_deleted(self):
        with self.assertRaises(AccessError):
            self.test_binding.unlink()

    def test_binding_again_supersedes_the_active_binding(self):
        other = self._create_partner({"name": "Other Person"})
        new = self.test_account._bind(other, method="invitation")

        self.assertEqual(self.test_binding.state, "revoked")
        self.assertEqual(self.test_binding.revoked_reason, "superseded")
        self.assertEqual(self.test_account.binding_id, new)
        self.assertEqual(self.test_chat.partner_id, other)

    def test_the_journal_is_append_only(self):
        event = self.env["telegram.binding.event"].search([], limit=1)
        with self.assertRaises(AccessError):
            event.write({"reason": "admin"})
        with self.assertRaises(AccessError):
            event.unlink()


@tagged("post_install", "-at_install")
class TestLinkTokens(IdentityCase):
    def setUp(self):
        super().setUp()
        self.test_bot.bot_username = "test_bot"
        self.tokens = self.env["telegram.link.token"]

    def _start(self, token, chat_id="880001"):
        update = _update(chat_id, "private", int(chat_id), text=f"/start {token}")
        with self.mock_api_gateway_post() as post, self.mock_rate_limiter():
            self.controller._dispatch_message(self.test_bot, update)
        chat = self.env["telegram.chat"].search([("chat_id", "=", chat_id)])
        return chat, post

    def test_a_session_token_binds_the_user_who_minted_it(self):
        token = self.tokens.with_user(self.test_user)._issue_for_session(self.test_bot)

        chat, _post = self._start(token)

        binding = chat.account_id.binding_id
        self.assertEqual(binding.user_id, self.test_user)
        self.assertEqual(binding.method, "session")
        self.assertEqual(chat.account_id._acting_user("internal"), self.test_user)

    def test_an_invitation_binds_the_contact(self):
        contact = self._create_partner({"name": "Field Worker"})
        token = self.tokens._issue_invitation(self.test_bot, contact)

        chat, _post = self._start(token)

        self.assertEqual(chat.account_id.partner_id, contact)
        self.assertFalse(chat.account_id.binding_id.user_id)

    def test_a_token_binds_once(self):
        token = self.tokens.with_user(self.test_user)._issue_for_session(self.test_bot)
        self._start(token, chat_id="880002")

        chat, _post = self._start(token, chat_id="880003")

        self.assertFalse(chat.account_id.binding_id)

    def test_an_expired_token_binds_nothing(self):
        token = self.tokens.with_user(self.test_user)._issue_for_session(self.test_bot)
        self.tokens.search(
            [("token_hash", "=", self.tokens._hash(token))]
        ).sudo().write({"date_to": self.env.cr.now() - timedelta(seconds=1)})

        chat, _post = self._start(token)

        self.assertFalse(chat.account_id.binding_id)

    def test_another_bots_token_binds_nothing(self):
        other_bot = self.env["telegram.bot"].create(
            {
                "name": "Other Bot",
                "credential_id": self._make_bot_credential(
                    "Other", "987654322:ZYX-other-token-abcdefghij"
                ).id,
            }
        )
        token = self.tokens.with_user(self.test_user)._issue_for_session(other_bot)

        chat, _post = self._start(token)

        self.assertFalse(chat.account_id.binding_id)

    def test_a_token_in_a_group_binds_nothing(self):
        token = self.tokens.with_user(self.test_user)._issue_for_session(self.test_bot)
        update = _update("-100700", "supergroup", 880004, text=f"/start {token}")
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.controller._dispatch_message(self.test_bot, update)

        account = self.env["telegram.account"].search([("tg_user_id", "=", "880004")])
        self.assertFalse(account.binding_id)
        self.assertTrue(
            self.tokens.search([("token_hash", "=", self.tokens._hash(token))])
        )
        self.assertFalse(
            self.tokens.sudo()
            .search([("token_hash", "=", self.tokens._hash(token))])
            .consumed_at
        )

    def test_only_the_hash_is_stored(self):
        token = self.tokens.with_user(self.test_user)._issue_for_session(self.test_bot)

        self.assertFalse(self.tokens.sudo().search([("token_hash", "=", token)]))
        self.assertTrue(
            self.tokens.sudo().search([("token_hash", "=", self.tokens._hash(token))])
        )

    def test_disconnect_revokes_the_senders_binding(self):
        update = _update("12345", "private", 12345, text="/desconectar")
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.controller._dispatch_message(self.test_bot, update)

        self.assertEqual(self.test_binding.state, "revoked")
        self.assertEqual(self.test_binding.revoked_reason, "user")

    def test_the_connect_route_needs_a_bot_username(self):
        self.test_bot.bot_username = False
        self.assertFalse(self.test_bot._deep_link("x"))


class TestMiniAppUser(IdentityCase):
    def test_the_bound_account_resolves(self):
        self.assertEqual(self.test_bot._mini_app_user("12345"), self.test_user)

    def test_an_unknown_telegram_user_resolves_to_nobody(self):
        self.assertFalse(self.test_bot._mini_app_user("999999"))

    def test_an_unbound_account_resolves_to_nobody(self):
        self._account(555010)
        self.assertFalse(self.test_bot._mini_app_user("555010"))

    def test_the_tier_is_honoured(self):
        portal_partner = self._create_partner({"name": "Portal Mini"})
        portal = self.env["res.users"].create(
            {
                "name": "Portal Mini",
                "login": "portal-mini@example.com",
                "partner_id": portal_partner.id,
                "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            }
        )
        account = self._account(555011)
        account._bind(portal_partner, user=portal, method="session")

        self.assertFalse(self.test_bot._mini_app_user("555011"))
        self.assertEqual(self.test_bot._mini_app_user("555011", "portal"), portal)


class TestChatLookups(IdentityCase):
    def test_for_user_finds_the_bound_private_chat(self):
        self.assertEqual(
            self.env["telegram.chat"]._for_user(self.test_user, self.test_bot),
            self.test_chat,
        )

    def test_for_user_ignores_a_revoked_binding(self):
        self.test_binding._revoke("admin")
        self.assertFalse(self.env["telegram.chat"]._for_user(self.test_user))

    def test_for_user_ignores_a_group_chat(self):
        self._resolve(_update("-100800", "supergroup", 12345))
        self.assertEqual(
            self.env["telegram.chat"]._for_user(self.test_user), self.test_chat
        )

    def test_getme_fills_the_bot_identity(self):
        response = {
            "ok": True,
            "result": {
                "username": "agro_bot",
                "can_join_groups": True,
                "can_read_all_group_messages": False,
            },
        }
        with patch.object(
            type(self.test_bot._get_telegram_client()),
            "get_me",
            return_value=response,
        ):
            self.test_bot._read_identity()

        self.assertEqual(self.test_bot.bot_username, "agro_bot")
        self.assertEqual(
            self.test_bot._deep_link("tok"), "https://t.me/agro_bot?start=tok"
        )
        self.assertFalse(self.test_bot.can_read_all_group_messages)


class TestRevokeOverRpc(IdentityCase):
    def test_a_user_cannot_revoke_a_binding_over_rpc(self):
        other = self._bound_account("660101", self._create_partner({"name": "Other"}))
        with self.assertRaises(AccessError):
            other.with_user(self.test_user).action_revoke()
        with self.assertRaises(AccessError):
            other.binding_id.with_user(self.test_user).action_revoke()
        self.assertTrue(other.binding_id)

    def test_a_user_cannot_disconnect_somebody_else(self):
        other_user = self.env["res.users"].create(
            {"name": "Other User", "login": "other-rpc@example.com"}
        )
        with self.assertRaises(AccessError):
            other_user.with_user(self.test_user).action_telegram_disconnect()


class TestFirstContactStandIn(IdentityCase):
    def test_proving_an_identity_merges_the_first_contact_stand_in(self):
        account = self._account(555020)
        stand_in = self._create_partner({"name": "Telegram Stranger"})
        first_binding = account._bind(stand_in, method="contact")

        real = self._create_partner({"name": "Known Customer"})
        account._bind(real, method="invitation")

        self.assertFalse(stand_in.exists())
        self.assertEqual(account.partner_id, real)
        self.assertTrue(first_binding.exists())
        self.assertEqual(first_binding.partner_id, real)
        self.assertEqual(first_binding.state, "revoked")

    def test_a_proven_contact_is_never_merged_away(self):
        account = self._account(555021)
        first = self._create_partner({"name": "First Proven"})
        account._bind(first, method="invitation")
        second = self._create_partner({"name": "Second Proven"})
        account._bind(second, method="invitation")
        self.assertTrue(first.exists())
