import dataclasses
from unittest.mock import MagicMock, patch

import psycopg
from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.db import db_connect
from odoo.exceptions import ConcurrencyError, ValidationError
from odoo.libs.guarded_http import GuardedSession
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests.common import (
    HttpCase,
    TransactionCase,
    new_test_user,
    tagged,
    users,
)
from odoo.tools import mute_logger
from odoo.tools.misc import limited_field_access_token

from odoo.addons.mail.tests.common import MailCommon
from odoo.addons.mail.tools.discuss import Store


@tagged("RTC", "post_install", "-at_install")
class TestRtcSessionCountConcurrency(TransactionCase):
    def setUp(self):
        super().setUp()
        with db_connect(self.env.cr.dbname).cursor() as cr:
            env = self.env(cr=cr)
            partners = env["res.partner"].create(
                [{"name": f"rtc race {index}"} for index in range(2)]
            )
            channel = (
                env["discuss.channel"]
                .with_context(install_mode=True)
                .create(
                    {
                        "name": "rtc race",
                        "channel_type": "group",
                        "channel_member_ids": [
                            Command.create({"partner_id": partner.id})
                            for partner in partners
                        ],
                    }
                )
            )
            cr.commit()
            self.channel_id = channel.id
            self.partner_ids = partners.ids
            self.member_ids = channel.channel_member_ids.sorted("id").ids
        self.addCleanup(self._drop_committed_rows)

    def _drop_committed_rows(self):
        with db_connect(self.env.cr.dbname).cursor() as cr:
            cr.execute("DELETE FROM discuss_channel WHERE id = %s", [self.channel_id])
            cr.execute(
                "DELETE FROM mail_message WHERE model = 'discuss.channel' AND res_id = %s",
                [self.channel_id],
            )
            cr.execute("DELETE FROM res_partner WHERE id = ANY(%s)", [self.partner_ids])
            cr.commit()

    def _read_call_state(self, cr):
        self.env(cr=cr)["discuss.channel"].browse(self.channel_id).sudo().mapped(
            "rtc_session_ids.id"
        )

    def _commit_retrying(self, cr, action):
        failures = 0
        while True:
            try:
                with mute_logger("odoo.db"):
                    action(self.env(cr=cr))
                cr.commit()
                return failures
            except psycopg.errors.SerializationFailure:
                failures += 1
                cr.rollback()
                if failures > 3:
                    raise

    def _committed_history(self):
        with db_connect(self.env.cr.dbname).cursor() as cr:
            cr.execute(
                "SELECT count(*), count(*) FILTER (WHERE end_dt IS NULL)"
                "  FROM discuss_call_history WHERE channel_id = %s",
                [self.channel_id],
            )
            return cr.fetchone()

    def _join(self, env, member_id):
        env["discuss.channel.rtc.session"].create({"channel_member_id": member_id})

    def test_concurrent_joins_start_the_call_once(self):
        with (
            db_connect(self.env.cr.dbname).cursor() as cr_a,
            db_connect(self.env.cr.dbname).cursor() as cr_b,
        ):
            self._read_call_state(cr_a)
            self._read_call_state(cr_b)
            self._join(self.env(cr=cr_a), self.member_ids[0])
            cr_a.commit()
            retries = self._commit_retrying(
                cr_b, lambda env: self._join(env, self.member_ids[1])
            )
        self.assertEqual(
            self._committed_history(),
            (1, 1),
            "two members joining an idle channel at once start a single call",
        )
        self.assertEqual(retries, 1, "the join that counted a stale call retried")

    def test_concurrent_leaves_end_the_call(self):
        with db_connect(self.env.cr.dbname).cursor() as cr:
            for member_id in self.member_ids:
                self._join(self.env(cr=cr), member_id)
            session_ids = (
                self.env(cr=cr)["discuss.channel.rtc.session"]
                .search([("channel_id", "=", self.channel_id)], order="id")
                .ids
            )
            cr.commit()
        with (
            db_connect(self.env.cr.dbname).cursor() as cr_a,
            db_connect(self.env.cr.dbname).cursor() as cr_b,
        ):
            self._read_call_state(cr_a)
            self._read_call_state(cr_b)
            self.env(cr=cr_a)["discuss.channel.rtc.session"].browse(
                session_ids[0]
            ).unlink()
            cr_a.commit()
            retries = self._commit_retrying(
                cr_b,
                lambda env: (
                    env["discuss.channel.rtc.session"].browse(session_ids[1]).unlink()
                ),
            )
        self.assertEqual(
            self._committed_history(),
            (1, 0),
            "the last of two concurrent leaves ends the call",
        )
        self.assertEqual(retries, 1, "the leave that counted a stale call retried")


@tagged("post_install", "-at_install")
class TestDiscussHardening(MailCommon, HttpCase):
    def _bus_messages(self, notification_type):
        return [
            json_loads(notif.message)["payload"]
            for notif in self._new_bus_notifs
            if json_loads(notif.message)["type"] == notification_type
        ]

    @users("employee")
    @mute_logger("odoo.models.unlink")
    def test_call_ended_by_gc_lasts_until_the_last_activity(self):
        channel = self.env["discuss.channel"]._create_group(
            partners_to=self.partner_employee.ids
        )
        channel.self_member_id.sudo()._rtc_join_call()
        session = channel.self_member_id.sudo().rtc_session_ids
        last_activity = fields.Datetime.now() - relativedelta(hours=20)
        session.flush_model()
        self.env.cr.execute(
            "UPDATE discuss_channel_rtc_session SET write_date = %s WHERE id = %s",
            (last_activity, session.id),
        )
        session.invalidate_recordset(["write_date"])
        self.env["discuss.channel.rtc.session"].sudo()._gc_inactive_sessions()
        history = channel.sudo().call_history_ids
        self.assertEqual(len(history), 1)
        self.assertEqual(history.end_dt, last_activity)

    @users("employee")
    @mute_logger("odoo.models.unlink")
    def test_leaving_a_call_ends_it_now(self):
        channel = self.env["discuss.channel"]._create_group(
            partners_to=self.partner_employee.ids
        )
        channel.self_member_id.sudo()._rtc_join_call()
        before = fields.Datetime.now()
        channel.self_member_id.sudo()._rtc_leave_call()
        self.assertGreaterEqual(channel.sudo().call_history_ids.end_dt, before)

    @mute_logger("odoo.models.unlink")
    def test_rejoin_below_the_sfu_threshold_keeps_the_call_on_one_transport(self):
        bob, carol, dave = (
            new_test_user(self.env, login, groups="base.group_user")
            for login in ("sfu_bob", "sfu_carol", "sfu_dave")
        )
        channel = (
            self.env["discuss.channel"]
            .with_user(bob)
            ._create_group(partners_to=(bob | carol | dave).partner_id.ids)
        )
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("mail.use_sfu_server", True)
        params.set_param("mail.sfu_server_url", "https://sfu.example.com")
        self.env["credential.credential"]._set_system_secret(
            "mail.sfu_server_key", "sfu-server-key"
        )
        response = MagicMock(ok=True, status_code=200)
        response.json.return_value = {
            "uuid": "sfu-channel",
            "url": "https://sfu.example.com",
        }

        def member_of(user):
            return channel.sudo().channel_member_ids.filtered(
                lambda member: member.partner_id == user.partner_id
            )

        with patch.object(GuardedSession, "request", return_value=response):
            for user in (bob, carol, dave):
                member_of(user)._rtc_join_call()
            self.assertEqual(channel.sudo().sfu_channel_uuid, "sfu-channel")
            member_of(dave)._rtc_leave_call()
            store = Store()
            self._reset_bus()
            with self.mock_bus():
                member_of(bob)._rtc_join_call(store)
        self.assertEqual(
            channel.sudo().sfu_channel_uuid,
            "sfu-channel",
            "carol is still on the SFU: dropping it would split the call",
        )
        self.assertEqual(
            store.get_result()["Rtc"]["serverInfo"]["channelUUID"],
            "sfu-channel",
            "the rejoining peer joins the SFU the others are on",
        )
        self.assertFalse(
            self._bus_messages("discuss.channel.rtc.session/sfu_hot_swap"),
            "nobody changes transport, so nobody is told to",
        )

    def test_portal_mention_in_a_sub_channel_invites_the_mentioned_partner(self):
        portal = new_test_user(self.env, "hardening_portal", groups="base.group_portal")
        channel = self.env["discuss.channel"]._create_channel(
            name="Public", group_id=None
        )
        channel.group_public_id = False
        channel._add_members(users=portal | self.user_employee)
        sub_channel = channel._create_sub_channel(name="Thread")
        sub_channel._add_members(partners=portal.partner_id)
        self.assertNotIn(
            self.partner_employee, sub_channel.channel_member_ids.partner_id
        )

        self.authenticate(portal.login, portal.login)
        self.call_jsonrpc(
            "/mail/message/post",
            {
                "thread_model": "discuss.channel",
                "thread_id": sub_channel.id,
                "post_data": {
                    "body": "ping",
                    "message_type": "comment",
                    "partner_ids": self.partner_employee.ids,
                    "partner_ids_mention_token": {
                        str(self.partner_employee.id): limited_field_access_token(
                            self.partner_employee, "id", scope="mail.message_mention"
                        )
                    },
                },
            },
        )

        self.assertIn(self.partner_employee, sub_channel.channel_member_ids.partner_id)

    def _count_creator_serializations(self, creator, fetch_params):
        Channel = type(self.env["discuss.channel"])
        to_store_defaults = Channel._to_store_defaults
        targets = []

        def spy(channel, target):
            if target.channel is None or target.channel == creator:
                targets.append(channel.ids)
            return to_store_defaults(channel, target)

        self.authenticate(creator.login, creator.login)
        with patch.object(Channel, "_to_store_defaults", spy):
            result = self.call_jsonrpc("/mail/action", {"fetch_params": [fetch_params]})
        return targets, result

    def test_creating_a_group_serializes_it_once_for_its_creator(self):
        creator = new_test_user(self.env, "group_creator", groups="base.group_user")
        other = new_test_user(self.env, "group_other", groups="base.group_user")
        targets, result = self._count_creator_serializations(
            creator, ["/discuss/create_group", {"partners_to": other.partner_id.ids}]
        )
        self.assertEqual(len(targets), 1)
        self.assertEqual(len(result["discuss.channel"]), 1)
        self.assertEqual(result["discuss.channel"][0]["member_count"], 2)

    def test_creating_a_chat_serializes_it_once_for_its_creator(self):
        creator = new_test_user(self.env, "chat_creator", groups="base.group_user")
        other = new_test_user(self.env, "chat_other", groups="base.group_user")
        targets, result = self._count_creator_serializations(
            creator,
            ["/discuss/get_or_create_chat", {"partners_to": other.partner_id.ids}],
        )
        self.assertEqual(len(targets), 1)
        self.assertEqual(result["discuss.channel"][0]["channel_type"], "chat")
        targets, result = self._count_creator_serializations(
            creator,
            ["/discuss/get_or_create_chat", {"partners_to": other.partner_id.ids}],
        )
        self.assertEqual(len(targets), 1, "reopening an existing chat too")
        self.assertEqual(result["discuss.channel"][0]["channel_type"], "chat")

    def test_creating_a_channel_serializes_it_once_for_its_creator(self):
        creator = new_test_user(self.env, "channel_creator", groups="base.group_user")
        targets, result = self._count_creator_serializations(
            creator, ["/discuss/create_channel", {"name": "Once"}]
        )
        self.assertEqual(len(targets), 1)
        self.assertEqual(result["discuss.channel"][0]["name"], "Once")

    @users("employee")
    def test_custom_channel_name_is_sent_once(self):
        channel = self.env["discuss.channel"]._create_group(
            partners_to=self.partner_employee.ids
        )
        self._reset_bus()
        with self.mock_bus():
            channel.channel_set_custom_name("Renamed")
        sent = [
            payload
            for payload in self._bus_messages("mail.record/insert")
            if "custom_channel_name"
            in json_dumps(payload.get("discuss.channel.member", []))
        ]
        self.assertEqual(len(sent), 1, sent)

    def _restricted_auto_subscribed_channel(self):
        group = self.env["res.groups"].create({"name": "Hardening Restricted"})
        channel = self.env["discuss.channel"]._create_channel(
            name="Restricted", group_id=group.id
        )
        channel.group_ids = group
        manager = new_test_user(
            self.env,
            "hardening_user_manager",
            groups="base.group_user,base.group_erp_manager",
        )
        self.assertFalse(
            self.env["discuss.channel"]
            .with_user(manager)
            .search([("id", "=", channel.id)]),
            "precondition: the user manager cannot read the channel",
        )
        return group, channel, manager

    def test_group_write_subscribes_channels_the_writer_cannot_read(self):
        group, channel, manager = self._restricted_auto_subscribed_channel()
        newcomer = new_test_user(
            self.env, "hardening_newcomer", groups="base.group_user"
        )
        group.with_user(manager).write({"user_ids": [Command.link(newcomer.id)]})
        self.assertIn(newcomer.partner_id, channel.channel_member_ids.partner_id)

    def test_user_write_subscribes_channels_the_writer_cannot_read(self):
        group, channel, manager = self._restricted_auto_subscribed_channel()
        newcomer = new_test_user(
            self.env, "hardening_newcomer", groups="base.group_user"
        )
        newcomer.with_user(manager).write({"group_ids": [Command.link(group.id)]})
        self.assertIn(newcomer.partner_id, channel.channel_member_ids.partner_id)

    def test_group_write_subscribes_only_the_users_it_adds(self):
        group, channel, _manager = self._restricted_auto_subscribed_channel()
        existing = new_test_user(
            self.env, "hardening_existing", groups="base.group_user"
        )
        group.write({"user_ids": [Command.link(existing.id)]})
        newcomer = new_test_user(
            self.env, "hardening_newcomer", groups="base.group_user"
        )
        Channel = type(self.env["discuss.channel"])
        with patch.object(
            Channel,
            "_subscribe_users_automatically",
            autospec=True,
            side_effect=Channel._subscribe_users_automatically,
        ) as subscribe:
            group.write({"user_ids": [Command.link(newcomer.id)]})
        self.assertEqual(subscribe.call_count, 1)
        self.assertEqual(
            subscribe.call_args.kwargs.get("partners"), newcomer.partner_id
        )
        self.assertIn(newcomer.partner_id, channel.channel_member_ids.partner_id)

    def test_presence_insert_race_is_a_concurrency_error(self):
        user = self.env.ref("base.user_admin")
        self.assertFalse(
            user.sudo().presence_ids, "precondition: no presence in this snapshot"
        )
        self.env["res.partner"].search_count([])

        def delete_committed():
            with db_connect(self.env.cr.dbname).cursor() as cr:
                cr.execute("DELETE FROM mail_presence WHERE user_id = %s", [user.id])

        with db_connect(self.env.cr.dbname).cursor() as other:
            other.execute(
                "INSERT INTO mail_presence (user_id, status, last_poll, last_presence)"
                " VALUES (%s, 'online', now(), now())",
                [user.id],
            )
        self.addCleanup(delete_committed)
        with mute_logger("odoo.db"), self.assertRaises(ConcurrencyError):
            self.env["mail.presence"]._update_presence(user)

        marker = self.env["res.partner"].create({"name": "still in the transaction"})
        Cron = type(self.env["ir.cron"])
        with patch.object(
            Cron, "_commit_progress", side_effect=AssertionError("cron API in HTTP")
        ):
            self.env["mail.presence"]._try_update_presence(user)
        self.assertTrue(marker.exists(), "a lost presence race keeps the transaction")

    def test_guest_channel_ids_is_not_a_membership_back_door(self):
        channel = self.env["discuss.channel"]._create_channel(
            name="Guests", group_id=None
        )
        guest = self.env["mail.guest"].create({"name": "Back door"})
        member = channel._add_members(guests=guest)
        guest.write({"channel_ids": [Command.unlink(channel.id)]})
        guest.invalidate_recordset()
        self.assertTrue(
            member.exists(), "a membership is removed by discuss.channel.member only"
        )
        self.assertEqual(guest.channel_ids, channel)

    def test_channel_ids_follows_member_unlink(self):
        channel = self.env["discuss.channel"]._create_channel(
            name="Guests", group_id=None
        )
        guest = self.env["mail.guest"].create({"name": "Leaver"})
        channel._add_members(guests=guest)
        self.assertEqual(guest.channel_ids, channel)
        self.assertNotIn(channel, self.partner_employee.channel_ids)
        channel._add_members(partners=self.partner_employee)
        self.assertIn(channel, self.partner_employee.channel_ids)
        channel.channel_member_ids.filtered(lambda m: m.guest_id).unlink()
        self.assertFalse(guest.channel_ids)
        self.assertEqual(
            self.env["mail.guest"].search([("channel_ids", "in", channel.ids)]),
            self.env["mail.guest"],
        )
        self.assertEqual(
            self.env["res.partner"].search(
                [
                    ("channel_ids", "in", channel.ids),
                    ("id", "=", self.partner_employee.id),
                ]
            ),
            self.partner_employee,
        )

    def _patched_policies(self, channel_type, **changes):
        Channel = type(self.env["discuss.channel"])
        policies = {
            name: dataclasses.replace(policy, **changes)
            if name == channel_type
            else policy
            for name, policy in Channel._channel_type_policies().items()
        }
        return patch.object(Channel, "_channel_type_policy_map", return_value=policies)

    @users("employee")
    def test_mention_suggestions_follow_the_type_policy(self):
        self.env["discuss.channel"]._create_group(
            partners_to=self.partner_employee.ids, name="Hashtag group"
        )
        suggestions = self.env["discuss.channel"].get_mention_suggestions("Hashtag")
        self.assertFalse(suggestions.get("discuss.channel"))
        with self._patched_policies("group", mentionable_by_hashtag=True):
            suggestions = self.env["discuss.channel"].get_mention_suggestions("Hashtag")
        self.assertEqual(len(suggestions["discuss.channel"]), 1)

    @users("employee")
    def test_new_message_separator_must_be_a_message_of_the_channel(self):
        channel = self.env["discuss.channel"]._create_group(
            partners_to=self.partner_employee.ids
        )
        other = self.env["discuss.channel"]._create_group(
            partners_to=self.partner_employee.ids
        )
        message = channel.message_post(body="mine", message_type="comment")
        foreign = other.message_post(body="theirs", message_type="comment")
        member = channel.self_member_id
        for invalid in (0, -1, foreign.id, message.id + 1000):
            with self.assertRaises(ValidationError):
                member._update_new_message_separator(invalid)
        member._update_new_message_separator(message.id)
        self.assertEqual(member.new_message_separator, message.id)


@tagged("post_install", "-at_install")
class TestChannelMentionSuggestionsLimit(TransactionCase):
    def test_the_limit_a_caller_asks_for_is_clamped(self):
        Channel = self.env["discuss.channel"]
        limits = []
        search = type(Channel).search

        def spy(model, domain, *args, **kwargs):
            limits.append(kwargs.get("limit"))
            return search(model, domain, *args, **kwargs)

        with patch.object(type(Channel), "search", spy):
            Channel.get_mention_suggestions("", limit=10**6)
        self.assertLessEqual(limits[0], 100)


@tagged("post_install", "-at_install")
class TestGuestCookie(HttpCase):
    def test_guest_cookie_is_httponly_and_same_site_lax(self):
        channel = self.env["discuss.channel"]._create_channel(
            name="Cookie", group_id=None
        )
        channel.group_public_id = False
        response = self.url_open(channel.invitation_url)
        self.assertEqual(response.status_code, 200)
        dgid = [
            header
            for header in response.raw.headers.getlist("Set-Cookie")
            if header.startswith("dgid=")
        ]
        self.assertEqual(len(dgid), 1)
        attributes = {part.strip().lower() for part in dgid[0].split(";")}
        self.assertIn("httponly", attributes)
        self.assertIn("samesite=lax", attributes)
        self.assertNotIn("secure", attributes, "plain http carries no secure flag")
