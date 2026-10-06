import base64
import datetime
import time
from contextlib import contextmanager
from unittest.mock import patch

import psycopg
from markupsafe import Markup

import odoo
from odoo import SUPERUSER_ID, Command, api
from odoo.exceptions import ConcurrencyError, MissingError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.service.transaction import retrying
from odoo.tests import TransactionCase, mute_logger, new_test_user, tagged

from odoo.addons.mail.models import mixin_mail_thread
from odoo.addons.mail.tests.test_fetchmail_server import (
    FetchmailCommon,
    MockedConnection,
    _message,
)


class _FakeSMTP:
    def quit(self):
        pass

    def close(self):
        pass


class TwoCursorsCase(TransactionCase):
    def setUp(self):
        super().setUp()
        self._committed = []
        self.enterContext(self.leave_registry_test_mode())
        self.addCleanup(self._drop_committed)

    def _drop_committed(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
            for model, domain in reversed(self._committed):
                env[model].sudo().search(domain).unlink()

    def _forget(self, model, domain):
        self._committed.append((model, domain))

    def _commit(self, action, uid=SUPERUSER_ID):
        with self.registry.cursor() as cr:
            return action(api.Environment(cr, uid, {}))

    def _cursor(self, uid=SUPERUSER_ID):
        cr = self.registry.cursor()
        self.addCleanup(cr.close)
        return api.Environment(cr, uid, {})

    def _snapshot(self, env):
        env.cr.execute("SELECT 1")

    def _retrying(self, env, action):
        tries = []

        def attempt():
            tries.append(1)
            return action(env)

        with mute_logger("odoo.db.cursor", "odoo.service.model"):
            result = retrying(attempt, env)
        return result, len(tries)

    def _user(self, env, login):
        user = new_test_user(env, login=f"{login}{time.time_ns()}", name=login)
        self._forget("res.partner", [("id", "=", user.partner_id.id)])
        self._forget("res.users", [("id", "=", user.id)])
        return user

    def _channel(self, env, partners, channel_type="group"):
        channel = (
            env["discuss.channel"]
            .with_context(install_mode=True)
            .create(
                {
                    "name": f"race {time.time_ns()}",
                    "channel_type": channel_type,
                    "channel_member_ids": [
                        Command.create({"partner_id": partner.id})
                        for partner in partners
                    ],
                }
            )
        )
        self._forget(
            "mail.message",
            [("model", "=", "discuss.channel"), ("res_id", "=", channel.id)],
        )
        self._forget("discuss.channel", [("id", "=", channel.id)])
        return channel

    def _bus_payloads(self, message_type, since_id):
        with self.registry.cursor() as cr:
            cr.execute(
                "SELECT message FROM bus_bus WHERE id > %s ORDER BY id", [since_id]
            )
            messages = [json_loads(message) for [message] in cr.fetchall()]
        return [m["payload"] for m in messages if m["type"] == message_type]

    def _last_bus_id(self):
        with self.registry.cursor() as cr:
            cr.execute("SELECT COALESCE(max(id), 0) FROM bus_bus")
            return cr.fetchone()[0]

    @contextmanager
    def _outside_test_mode(self):
        with patch.object(odoo.modules.module, "current_test", None):
            yield


@tagged("post_install", "-at_install", "mail_concurrency")
class TestMailSendClaim(TwoCursorsCase):
    def _mails(self, count):
        def create(env):
            mails = env["mail.mail"].create(
                [
                    {
                        "email_to": f"race{index}@example.com",
                        "email_from": "sender@example.com",
                        "subject": f"race {index} {time.time_ns()}",
                        "body_html": "<p>race</p>",
                    }
                    for index in range(count)
                ]
            )
            self._forget("mail.mail", [("id", "in", mails.ids)])
            self._forget("mail.message", [("id", "in", mails.mail_message_id.ids)])
            return mails.ids

        return self._commit(create)

    @contextmanager
    def _smtp(self, on_send=None):
        sent = []
        MailServer = self.registry["ir.mail_server"]

        def send_email(server, message, *args, **kwargs):
            sent.append((server.env.cr, message["Subject"]))
            if on_send:
                on_send(server.env.cr)
            return f"<race-{len(sent)}@example.com>"

        with (
            self._outside_test_mode(),
            patch.object(MailServer, "_connect__", lambda *a, **k: _FakeSMTP()),
            patch.object(MailServer, "send_email", send_email),
        ):
            yield sent

    def _states(self, mail_ids):
        with self.registry.cursor() as cr:
            cr.execute(
                "SELECT state FROM mail_mail WHERE id = ANY(%s) ORDER BY id",
                [mail_ids],
            )
            return [state for [state] in cr.fetchall()]

    def test_send_now_on_a_snapshot_older_than_the_queue_pass_sends_once(self):
        mail_ids = self._mails(1)
        user = self._cursor()
        self._snapshot(user)
        with self._smtp() as sent:
            self._commit(
                lambda env: env["mail.mail"].process_email_queue(email_ids=mail_ids)
            )
            self._retrying(
                user,
                lambda env: env["mail.mail"].browse(mail_ids).action_send_and_close(),
            )
        self.assertEqual(
            len(sent), 1, "the queue sent the mail; Send Now must not send it again"
        )
        self.assertEqual(self._states(mail_ids), ["sent"])

    def test_queue_pass_during_send_now_sends_each_mail_once(self):
        mail_ids = self._mails(2)
        user = self._cursor()
        queue_passes = []

        def queue_pass_while_first_is_on_the_wire(cr):
            if cr is user.cr and not queue_passes:
                queue_passes.append(1)
                self._commit(
                    lambda env: env["mail.mail"].process_email_queue(email_ids=mail_ids)
                )

        with self._smtp(queue_pass_while_first_is_on_the_wire) as sent:
            self._retrying(
                user,
                lambda env: env["mail.mail"].browse(mail_ids).action_send_and_close(),
            )
        self.assertEqual(queue_passes, [1])
        self.assertEqual(
            sorted(subject for _cr, subject in sent),
            sorted({subject for _cr, subject in sent}),
            "no mail may reach SMTP twice",
        )
        self.assertEqual(len(sent), 2)
        self.assertTrue(
            all(cr is user.cr for cr, _subject in sent),
            "the queue pass skips the mails Send Now holds",
        )
        self.assertEqual(self._states(mail_ids), ["sent", "sent"])

    def test_database_error_while_marking_stays_retryable(self):
        mail_ids = self._mails(2)

        def add_notification(env):
            mail = env["mail.mail"].browse(mail_ids[1])
            partner = env["res.partner"].create({"name": "race recipient"})
            self._forget("res.partner", [("id", "=", partner.id)])
            notification = env["mail.notification"].create(
                {
                    "mail_mail_id": mail.id,
                    "mail_message_id": mail.mail_message_id.id,
                    "res_partner_id": partner.id,
                    "notification_type": "email",
                    "notification_status": "ready",
                }
            )
            self._forget("mail.notification", [("id", "=", notification.id)])
            return notification.id

        notification_id = self._commit(add_notification)
        MailMail = self.registry["mail.mail"]
        mark_sending = MailMail._mark_sending

        def mark_sending_uncached_after_a_concurrent_commit(mail, *args, **kwargs):
            if mail.id == mail_ids[1]:
                mail.env.cr.execute("SELECT 1")
                mail.invalidate_recordset()
                self._commit(
                    lambda env: env.cr.execute(
                        "UPDATE mail_notification SET failure_reason = 'touched'"
                        " WHERE id = %s",
                        [notification_id],
                    )
                )
            return mark_sending(mail, *args, **kwargs)

        with (
            self._smtp() as sent,
            patch.object(
                MailMail,
                "_mark_sending",
                mark_sending_uncached_after_a_concurrent_commit,
            ),
            mute_logger("odoo.addons.mail.models.mail_mail", "odoo.db.cursor"),
            self.assertRaises(psycopg.errors.SerializationFailure),
        ):
            self._commit(
                lambda env: env["mail.mail"].process_email_queue(email_ids=mail_ids)
            )
        self.assertEqual(len(sent), 1)
        self.assertEqual(self._states(mail_ids), ["sent", "outgoing"])


@tagged("post_install", "-at_install", "mail_concurrency")
class TestWebPushAfterCommit(TwoCursorsCase):
    def test_retried_post_pushes_once(self):
        def setup(env):
            alice, bob = self._user(env, "alice"), self._user(env, "bob")
            channel = self._channel(env, alice.partner_id | bob.partner_id)
            devices = (
                env["mail.push.device"]
                .sudo()
                .create(
                    [
                        {
                            "partner_id": user.partner_id.id,
                            "endpoint": f"https://push.example.com/{user.login}",
                            "keys": json_dumps({"p256dh": "x", "auth": "y"}),
                        }
                        for user in (alice, bob)
                    ]
                )
            )
            self._forget("mail.push.device", [("id", "in", devices.ids)])
            return alice.id, bob.id, channel.id

        alice_id, bob_id, channel_id = self._commit(setup)
        pushes = []

        def partners_parameters(thread, partner_ids):
            devices = thread.env["mail.push.device"].sudo()
            return devices.search([("partner_id", "in", partner_ids)]), "priv", "pub"

        alice, bob = self._cursor(alice_id), self._cursor(bob_id)
        with (
            self._outside_test_mode(),
            patch.object(
                mixin_mail_thread,
                "push_to_end_point",
                lambda **kw: pushes.append(kw["device"]["endpoint"]),
            ),
            patch.object(
                self.registry["discuss.channel"],
                "_web_push_get_partners_parameters",
                partners_parameters,
            ),
        ):
            self._snapshot(bob)
            alice["discuss.channel"].browse(channel_id).message_post(
                body="from alice", message_type="comment"
            )
            alice.cr.commit()
            _message, tries = self._retrying(
                bob,
                lambda env: (
                    env["discuss.channel"]
                    .browse(channel_id)
                    .message_post(body="from bob", message_type="comment")
                ),
            )
        self.assertEqual(tries, 2, "bob's post conflicts with alice's and retries")
        self.assertEqual(
            len(pushes), 2, "one push per posted message, whatever the retries"
        )


@tagged("post_install", "-at_install", "mail_concurrency")
class TestDiscussGetOrCreateRaces(TwoCursorsCase):
    def test_two_tabs_joining_a_channel_join_once(self):
        def setup(env):
            partner = env["res.partner"].create({"name": "joiner"})
            self._forget("res.partner", [("id", "=", partner.id)])
            channel = self._channel(env, env["res.partner"], channel_type="channel")
            return partner.id, channel.id

        partner_id, channel_id = self._commit(setup)
        first, second = self._cursor(), self._cursor()
        self._snapshot(second)

        def join(env):
            env["discuss.channel"].browse(channel_id)._add_members(
                partners=env["res.partner"].browse(partner_id)
            )

        join(first)
        first.cr.commit()
        _result, tries = self._retrying(second, join)
        self.assertEqual(tries, 2)
        members = self._commit(
            lambda env: env["discuss.channel.member"].search_count(
                [("channel_id", "=", channel_id), ("partner_id", "=", partner_id)]
            )
        )
        self.assertEqual(members, 1)

    def test_rtc_join_from_two_devices_keeps_one_session(self):
        def setup(env):
            partner = env["res.partner"].create({"name": "caller"})
            self._forget("res.partner", [("id", "=", partner.id)])
            channel = self._channel(env, partner)
            return channel.channel_member_ids.id

        member_id = self._commit(setup)
        first, second = self._cursor(), self._cursor()
        self._snapshot(second)

        def join_call(env):
            env["discuss.channel.member"].browse(member_id)._rtc_join_call()

        join_call(first)
        first.cr.commit()
        _result, tries = self._retrying(second, join_call)
        self.assertEqual(tries, 2)
        sessions = self._commit(
            lambda env: (
                env["discuss.channel.rtc.session"]
                .search([("channel_member_id", "=", member_id)])
                .ids
            )
        )
        self.assertEqual(len(sessions), 1)

    def test_thread_created_twice_from_one_message_is_shared(self):
        def setup(env):
            channel = self._channel(env, env.user.partner_id, channel_type="channel")
            message = channel.message_post(body="thread me", message_type="comment")
            self._forget("discuss.channel", [("from_message_id", "=", message.id)])
            return channel.id, message.id

        channel_id, message_id = self._commit(setup)
        first, second = self._cursor(), self._cursor()
        self._snapshot(second)

        def create_thread(env):
            return (
                env["discuss.channel"]
                .browse(channel_id)
                ._create_sub_channel(from_message_id=message_id)
                .id
            )

        created = create_thread(first)
        first.cr.commit()
        shared, tries = self._retrying(second, create_thread)
        self.assertEqual(tries, 2)
        self.assertEqual(shared, created, "the second request opens the same thread")


@tagged("post_install", "-at_install", "mail_concurrency")
class TestAbsoluteStateBroadcasts(TwoCursorsCase):
    def _reaction_broadcasts(self, message_id, since_id):
        groups = []
        for payload in self._bus_payloads("mail.record/insert", since_id):
            groups += [
                (group["count"], sorted(group["partners"]))
                for group in payload.get("MessageReactions", [])
                if group["message"] == message_id
            ]
            groups += [
                (0, [])
                for message in payload.get("mail.message", [])
                if message["id"] == message_id
                and any(command == "DELETE" for command, _v in message["reactions"])
            ]
        return groups

    def _reaction_setup(self, reacted=False):
        def setup(env):
            partners = env["res.partner"].create(
                [{"name": "reacts first"}, {"name": "reacts second"}]
            )
            self._forget("res.partner", [("id", "in", partners.ids)])
            channel = self._channel(env, partners)
            message = channel.message_post(body="react", message_type="comment")
            if reacted:
                message._message_reaction("👍", "add", partners[0], env["mail.guest"])
            return message.id, partners.ids

        return self._commit(setup)

    def _react(self, env, message_id, partner_id, action):
        env["mail.message"].browse(message_id)._message_reaction(
            "👍", action, env["res.partner"].browse(partner_id), env["mail.guest"]
        )

    def test_concurrent_reactions_broadcast_the_full_group(self):
        message_id, (first_id, second_id) = self._reaction_setup()
        since = self._last_bus_id()
        first, second = self._cursor(), self._cursor()
        self._snapshot(second)
        self._react(first, message_id, first_id, "add")
        first.cr.commit()
        self._retrying(
            second, lambda env: self._react(env, message_id, second_id, "add")
        )
        self.assertEqual(
            self._reaction_broadcasts(message_id, since)[-1],
            (2, sorted([first_id, second_id])),
        )

    def test_reaction_added_while_another_is_removed(self):
        message_id, (first_id, second_id) = self._reaction_setup(reacted=True)
        since = self._last_bus_id()
        first, second = self._cursor(), self._cursor()
        self._snapshot(second)
        self._react(first, message_id, first_id, "remove")
        first.cr.commit()
        self._retrying(
            second, lambda env: self._react(env, message_id, second_id, "add")
        )
        self.assertEqual(
            self._reaction_broadcasts(message_id, since), [(0, []), (1, [second_id])]
        )

    def test_inbox_counter_after_two_tabs_mark_messages_done(self):
        def setup(env):
            user = self._user(env, "inbox")
            record = env["res.partner"].create({"name": "needaction record"})
            self._forget("res.partner", [("id", "=", record.id)])
            self._forget(
                "mail.message",
                [("model", "=", "res.partner"), ("res_id", "=", record.id)],
            )
            messages = [
                record.message_post(
                    body=f"needaction {index}",
                    partner_ids=user.partner_id.ids,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )
                for index in range(2)
            ]
            env["mail.notification"].search(
                [("mail_message_id", "in", [m.id for m in messages])]
            ).write({"notification_type": "inbox", "is_read": False})
            return user.id, [m.id for m in messages]

        user_id, message_ids = self._commit(setup)
        counter = self._commit(
            lambda env: (
                env["res.users"].browse(user_id).partner_id._get_needaction_count()
            )
        )
        since = self._last_bus_id()
        first, second = self._cursor(user_id), self._cursor(user_id)
        self._snapshot(second)
        first["mail.message"].browse(message_ids[0]).set_message_done()
        first.cr.commit()
        self._retrying(
            second,
            lambda env: env["mail.message"].browse(message_ids[1]).set_message_done(),
        )
        for payload in self._bus_payloads("mail.message/mark_as_read", since):
            if "needaction_inbox_counter" in payload:
                counter = payload["needaction_inbox_counter"]
            else:
                counter += payload["needaction_delta"]
        self.assertEqual(
            counter,
            self._commit(
                lambda env: (
                    env["res.users"].browse(user_id).partner_id._get_needaction_count()
                )
            ),
            "the counter the client derives from the broadcasts matches the database",
        )


@tagged("post_install", "-at_install", "mail_concurrency")
class TestScheduledMessageClaim(TwoCursorsCase):
    def _scheduled(self):
        def setup(env):
            record = env["res.partner"].create({"name": "scheduled record"})
            self._forget("res.partner", [("id", "=", record.id)])
            self._forget(
                "mail.message",
                [("model", "=", "res.partner"), ("res_id", "=", record.id)],
            )
            scheduled = (
                env["mail.scheduled.message"]
                .with_user(env.ref("base.user_admin"))
                .create(
                    {
                        "model": "res.partner",
                        "res_id": record.id,
                        "author_id": env.ref("base.user_admin").partner_id.id,
                        "body": "scheduled body",
                        "scheduled_date": datetime.datetime.now()
                        + datetime.timedelta(hours=1),
                    }
                )
            )
            self._forget("mail.scheduled.message", [("id", "=", scheduled.id)])
            env.cr.execute(
                "UPDATE mail_scheduled_message SET scheduled_date = now() at time zone"
                " 'UTC' - interval '1 minute' WHERE id = %s",
                [scheduled.id],
            )
            return record.id, scheduled.id

        return self._commit(setup)

    def _posted(self, record_id):
        return self._commit(
            lambda env: env["mail.message"].search_count(
                [
                    ("model", "=", "res.partner"),
                    ("res_id", "=", record_id),
                    ("body", "ilike", "scheduled body"),
                ]
            )
        )

    @contextmanager
    def _counting_posts(self):
        posts = []
        Partner = self.registry["res.partner"]
        message_post = Partner.message_post

        def counted(record, *args, **kwargs):
            posts.append(record.env.cr)
            return message_post(record, *args, **kwargs)

        with patch.object(Partner, "message_post", counted):
            yield posts

    def test_send_now_after_the_cron_posted_it(self):
        record_id, scheduled_id = self._scheduled()
        user = self._cursor(self.env.ref("base.user_admin").id)
        self._snapshot(user)
        with self._counting_posts() as posts:
            self._commit(
                lambda env: env["mail.scheduled.message"]._post_messages_cron()
            )
            with self.assertRaisesRegex(MissingError, "already been sent"):
                self._retrying(
                    user,
                    lambda env: (
                        env["mail.scheduled.message"]
                        .browse(scheduled_id)
                        .post_message()
                    ),
                )
        self.assertEqual(len(posts), 1, "the stale Send now posts nothing")
        self.assertEqual(self._posted(record_id), 1)

    def test_cron_during_send_now_leaves_it_to_send_now(self):
        record_id, scheduled_id = self._scheduled()
        user = self._cursor(self.env.ref("base.user_admin").id)
        cron_passes = []
        Partner = self.registry["res.partner"]
        message_post = Partner.message_post

        def post_while_the_cron_runs(record, *args, **kwargs):
            if record.env.cr is user.cr and not cron_passes:
                cron_passes.append(1)
                self._commit(
                    lambda env: env["mail.scheduled.message"]._post_messages_cron()
                )
            return message_post(record, *args, **kwargs)

        with patch.object(Partner, "message_post", post_while_the_cron_runs):
            _result, tries = self._retrying(
                user,
                lambda env: (
                    env["mail.scheduled.message"].browse(scheduled_id).post_message()
                ),
            )
        self.assertEqual(cron_passes, [1])
        self.assertEqual(tries, 1, "Send now, holding the message, is not disturbed")
        self.assertEqual(self._posted(record_id), 1)


@tagged("post_install", "-at_install", "mail_concurrency")
class TestUniqueRowRaces(TwoCursorsCase):
    def _race(self, action, first_uid=SUPERUSER_ID, second_uid=SUPERUSER_ID):
        first, second = self._cursor(first_uid), self._cursor(second_uid)
        self._snapshot(second)
        action(first)
        first.cr.commit()
        return self._retrying(second, action)

    def test_link_preview_attached_twice(self):
        url = f"https://race.example.com/{time.time_ns()}"

        def setup(env):
            preview = env["mail.link.preview"].create(
                {"source_url": url, "og_title": "race"}
            )
            self._forget("mail.link.preview", [("id", "=", preview.id)])
            channel = self._channel(env, env.user.partner_id)
            return channel.message_post(
                body=Markup('<a href="%s">link</a>') % url,
                message_type="comment",
            ).id

        message_id = self._commit(setup)
        _result, tries = self._race(
            lambda env: env["mail.link.preview"]._create_from_message_and_notify(
                env["mail.message"].browse(message_id)
            )
        )
        self.assertEqual(tries, 2)
        links = self._commit(
            lambda env: env["mail.message.link.preview"].search_count(
                [("message_id", "=", message_id)]
            )
        )
        self.assertEqual(links, 1)

    def test_push_device_registered_from_two_tabs(self):
        def encoded(raw):
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        endpoint = f"https://push.example.com/{time.time_ns()}"
        user_id = self._commit(lambda env: self._user(env, "pusher").id)
        self._forget("mail.push.device", [("endpoint", "=", endpoint)])
        vapid = self._commit(
            lambda env: (
                env["ir.config_parameter"]
                .sudo()
                .get_param("mail.web_push_vapid_public_key")
            )
        )
        self._commit(
            lambda env: (
                env["ir.config_parameter"]
                .sudo()
                .set_param("mail.web_push_vapid_public_key", "race-key")
            )
        )
        self.addCleanup(
            self._commit,
            lambda env: (
                env["ir.config_parameter"]
                .sudo()
                .set_param("mail.web_push_vapid_public_key", vapid)
            ),
        )
        _result, tries = self._race(
            lambda env: env["mail.push.device"].register_devices(
                vapid_public_key="race-key",
                endpoint=endpoint,
                keys={
                    "p256dh": encoded(b"\x04" + bytes(range(64))),
                    "auth": encoded(b"0123456789abcdef"),
                },
            ),
            user_id,
            user_id,
        )
        self.assertEqual(tries, 2)
        devices = self._commit(
            lambda env: (
                env["mail.push.device"]
                .sudo()
                .search_count([("endpoint", "=", endpoint)])
            )
        )
        self.assertEqual(devices, 1)

    def test_user_settings_created_from_two_tabs(self):
        def setup(env):
            user = self._user(env, "settings")
            env["res.users.settings"].sudo().search(
                [("user_id", "=", user.id)]
            ).unlink()
            return user.id

        user_id = self._commit(setup)
        _result, tries = self._race(
            lambda env: env["res.users.settings"]._get_or_create_for_user(env.user),
            user_id,
            user_id,
        )
        self.assertEqual(tries, 2)
        settings = self._commit(
            lambda env: (
                env["res.users.settings"]
                .sudo()
                .search_count([("user_id", "=", user_id)])
            )
        )
        self.assertEqual(settings, 1)

    def test_volume_set_from_two_tabs(self):
        def setup(env):
            user = self._user(env, "listener")
            partner = env["res.partner"].create({"name": "speaker"})
            self._forget("res.partner", [("id", "=", partner.id)])
            self._channel(env, user.partner_id | partner)
            settings = env["res.users.settings"]._get_or_create_for_user(user)
            return user.id, settings.id, partner.id

        user_id, settings_id, partner_id = self._commit(setup)
        volume_by_cursor = {}
        _result, tries = self._race(
            lambda env: (
                env["res.users.settings"]
                .browse(settings_id)
                .set_volume_setting(
                    partner_id,
                    volume_by_cursor.setdefault(
                        env.cr, 0.7 if volume_by_cursor else 0.3
                    ),
                )
            ),
            user_id,
            user_id,
        )
        self.assertEqual(tries, 2)
        stored = self._commit(
            lambda env: (
                env["res.users.settings.volumes"]
                .sudo()
                .search([("user_setting_id", "=", settings_id)])
                .mapped("volume")
            )
        )
        self.assertEqual(stored, [0.7], "the second tab's volume wins")

    def test_gif_favorite_added_from_two_tabs(self):
        gif_id = f"race{time.time_ns()}"
        self._forget("discuss.gif.favorite", [("tenor_gif_id", "=", gif_id)])
        _result, tries = self._race(
            lambda env: env["discuss.gif.favorite"]._add_favorite(gif_id)
        )
        self.assertEqual(tries, 2)
        favorites = self._commit(
            lambda env: env["discuss.gif.favorite"].search_count(
                [("tenor_gif_id", "=", gif_id)]
            )
        )
        self.assertEqual(favorites, 1)


@tagged("post_install", "-at_install", "mail_concurrency")
class TestFetchmailTransientErrors(FetchmailCommon):
    @mute_logger("odoo.addons.mail.models.fetchmail_server")
    def test_a_retryable_error_is_no_failed_attempt(self):
        server = self._server(name="transient database")
        connection = MockedConnection({1: _message(1)})
        errors = [
            psycopg.errors.SerializationFailure("could not serialize access"),
            ConcurrencyError("created by a concurrent transaction"),
            psycopg.errors.DeadlockDetected("deadlock detected"),
        ]
        delivered = []

        def message_process(obj, model, message, **kw):
            if errors:
                raise errors.pop(0)
            delivered.append(message)

        for _poll in range(4):
            with (
                self.sync_env_with_side_cursors(),
                self.registry.cursor() as cr,
                patch.object(type(server), "_connect__", lambda self, **kw: connection),
                patch.object(
                    self.registry["mixin.mail.thread"],
                    "message_process",
                    side_effect=message_process,
                    autospec=True,
                ),
            ):
                server.with_env(server.env(cr=cr)).sudo()._poll_mailboxes()
                if _poll < 3:
                    self.assertFalse(
                        server.with_env(server.env(cr=cr)).sudo().failure_ids,
                        "a transient database error is not a poison attempt",
                    )
        self.assertFalse(connection.quarantined)
        self.assertEqual(delivered, [_message(1)])
        self.assertEqual(connection.acknowledged, [1])
