import inspect
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from psycopg.errors import SerializationFailure

import odoo.http
from odoo import SUPERUSER_ID, api
from odoo.db import db_connect
from odoo.exceptions import AccessError, UserError
from odoo.libs._vendor.useragents import UserAgentParser
from odoo.libs.callbacks import Callbacks
from odoo.tests import BaseCase, TransactionCase, new_test_user, tagged
from odoo.tests.utils import get_db_name

from odoo.addons.base.models import auth_user_client, auth_user_client_session
from odoo.addons.base.models.ir_autovacuum import is_autovacuum

KEY = "k" * 43


class _Session(dict):
    def __init__(self, uid, sid):
        super().__init__()
        self.uid = uid
        self.sid = sid
        self.trace = None

    def update_trace(self, request):
        return self.trace


class _Response:
    def __init__(self):
        self.cookies = {}

    def set_cookie(self, key, value, **options):
        self.cookies[key] = value


class DeviceCase(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env["auth.user.client"].with_context(active_test=False).search([]).unlink()
        self.sessions = {}
        if not self._registry_patched:
            self.registry_enter_test_mode()

    def _seen(
        self,
        when,
        *,
        sid="sid_rdev_" + "a" * 60,
        key=KEY,
        ip="10.0.0.1",
        platform="linux",
        browser="firefox",
        issue=False,
        uid=None,
        at_login=None,
    ):
        session = self.sessions.setdefault(
            (uid or self.env.uid, sid), _Session(uid or self.env.uid, sid)
        )
        stamp = datetime.fromisoformat(when).replace(tzinfo=UTC).timestamp()
        session.trace = {
            "platform": platform,
            "browser": browser,
            "ip_address": ip,
            "first_activity": stamp,
            "last_activity": stamp,
        }
        response = _Response() if issue else None
        request = SimpleNamespace(
            session=session,
            app=odoo.http.root,
            httprequest=SimpleNamespace(
                cookies={auth_user_client.CLIENT_KEY_COOKIE: key} if key else {}
            ),
            future_response=response,
        )
        if "auth_client_id" not in session:
            login_request = request if at_login is not False else None
            with patch.object(
                type(self.env.cr), "now", return_value=datetime.fromisoformat(when)
            ):
                self.env["auth.user.client"]._bind_session(session, login_request)
        self.env["auth.user.client"]._observe(request)
        self.env.invalidate_all()
        return response

    def _devices(self):
        return self.env["auth.user.client"].with_context(active_test=False).search([])

    def _device(self, sessions=("sid_rdev_manual",), active=True, **vals):
        device = self.env["auth.user.client"].create(
            {
                "user_id": self.env.uid,
                "recognition_key_hash": f"hash_{vals.get('name', '')}_{sessions[:1]}",
                "last_activity": "2020-01-01 00:00:00",
                "active": active,
                **vals,
            }
        )
        for identifier in sessions:
            self.env["auth.user.client.session"].create(
                {
                    "client_id": device.id,
                    "session_identifier": identifier,
                    "last_activity": vals.get("last_activity", "2020-01-01"),
                    "active": active,
                }
            )
        return device


class TestDeviceUpsert(DeviceCase):
    def test_a_browser_is_one_device_across_its_sessions(self):
        self._seen("2026-07-01 08:00:00", sid="sid_rdev_morning" + "a" * 50)
        self._seen(
            "2026-07-02 09:00:00", sid="sid_rdev_next_day" + "a" * 50, ip="10.0.0.2"
        )

        device = self._devices()
        self.assertEqual(len(device), 1)
        self.assertEqual(len(device.session_ids), 2)
        self.assertEqual(device.first_activity, datetime(2026, 7, 1, 8, 0))
        self.assertEqual(device.last_activity, datetime(2026, 7, 2, 9, 0))
        self.assertEqual(device.ip_address, "10.0.0.2")
        self.assertEqual(
            device.address_ids.mapped("ip_address"), ["10.0.0.2", "10.0.0.1"]
        )

    def test_the_first_visit_issues_the_key_the_next_one_presents(self):
        response = self._seen("2026-07-01 08:00:00", key=None, issue=True)
        issued = response.cookies[auth_user_client.CLIENT_KEY_COOKIE]
        self.assertRegex(issued, r"^[A-Za-z0-9_-]{43}$")
        device = self._devices()
        self.assertEqual(device.recognition_key_hash, auth_user_client._sha256(issued))
        self.assertNotIn(issued, device.recognition_key_hash)

        again = self._seen(
            "2026-07-03 08:00:00", sid="sid_rdev_later" + "a" * 50, key=issued
        )
        self.assertIsNone(again)
        self.assertEqual(self._devices(), device)
        self.assertEqual(len(device.session_ids), 2)

    def test_a_session_without_a_key_gets_none_until_it_logs_in(self):
        responses = [
            self._seen("2026-07-01 09:00:00", key=None, issue=True, at_login=False)
            for _parallel_request in range(3)
        ]
        self.assertFalse(any(response.cookies for response in responses))
        self.assertEqual(len(self._devices()), 1, "one browser, one device")

    def test_a_malformed_key_is_replaced(self):
        response = self._seen("2026-07-01 08:00:00", key="not-a-key", issue=True)
        self.assertIn(auth_user_client.CLIENT_KEY_COOKIE, response.cookies)

    def test_without_a_key_each_session_is_a_device(self):
        self._seen("2026-07-01 08:00:00", key=None, sid="sid_rdev_one" + "a" * 50)
        self._seen("2026-07-01 09:00:00", key=None, sid="sid_rdev_two" + "a" * 50)
        self.assertEqual(len(self._devices()), 2)

    def test_the_keyless_hash_matches_the_migration(self):
        self.env.cr.execute(
            """
            SELECT encode(sha256(convert_to(concat_ws(
                chr(31), 'session', 'sid_x', coalesce(NULL, ''), 'firefox'
            ), 'UTF8')), 'hex')
            """
        )
        self.assertEqual(
            self.env.cr.fetchone()[0],
            auth_user_client._device_key_hash(None, "sid_x", None, "firefox"),
        )

    def test_two_users_on_one_browser_are_two_devices(self):
        other = new_test_user(self.env, login="rdev_other")
        self._seen("2026-07-01 08:00:00")
        self._seen("2026-07-01 09:00:00", uid=other.id, sid="sid_rdev_o" + "a" * 50)
        self.assertEqual(
            sorted(self._devices().mapped("user_id").ids),
            sorted([self.env.uid, other.id]),
        )

    def test_late_trace_keeps_the_latest_address(self):
        self._seen("2026-07-01 12:00:00", ip="10.0.0.2")
        self._seen("2026-07-01 08:00:00", ip="10.0.0.1")
        device = self._devices()
        self.assertEqual(device.ip_address, "10.0.0.2")
        self.assertEqual(device.first_activity, datetime(2026, 7, 1, 8, 0))

    def test_activity_cannot_revive_a_revoked_client(self):
        sid = "sid_rdev_" + "a" * 60
        self._seen("2026-07-01 08:00:00", sid=sid)
        self.env["auth.user.client.session"]._mark_revoked([sid[:42]])
        self.assertFalse(self.env["auth.user.client"].search([]))
        self._seen("2026-07-01 09:00:00", sid=sid)
        self.assertFalse(self.env["auth.user.client"].search([]))
        self.assertFalse(self._devices().session_ids.filtered("active"))
        self.assertFalse(
            self.env["auth.user.client"]._is_session_valid(
                self.sessions[(self.env.uid, sid)]
            )
        )

    def test_platform_type_follows_the_platform(self):
        self._seen("2026-07-01 08:00:00", platform="android", browser="chrome")
        self.assertEqual(self._devices().platform_type, "mobile")


class TestDeviceModel(DeviceCase):
    def test_autovacuums(self):
        def vacuums(model):
            return {
                name
                for name, _func in inspect.getmembers(
                    self.env[model].__class__, is_autovacuum
                )
            }

        self.assertEqual(vacuums("auth.user.client"), {"_gc_revoked_clients"})
        self.assertEqual(
            vacuums("auth.user.client.session"),
            {"_update_revoked", "_gc_ended_sessions"},
        )
        self.assertEqual(vacuums("auth.user.client.address"), {"_gc_stale_addresses"})

    def test_mobile_platforms_are_parser_vocabulary(self):
        emitted = {name for _regex, name in UserAgentParser.platforms}
        self.assertLessEqual(auth_user_client._MOBILE_PLATFORMS, emitted)
        self.assertEqual(auth_user_client._platform_type("Android"), "mobile")
        self.assertEqual(auth_user_client._platform_type(None), "unknown")

    def test_display_names(self):
        cases = {
            ("iphone", "safari", False): "iPhone Safari",
            ("windows phone", "edge", False): "Windows Phone Edge",
            ("macos", "samsung", False): "macOS Samsung Internet",
            (False, False, False): "Unknown Unknown",
            ("linux", "firefox", "Work laptop"): "Work laptop",
        }
        for (platform, browser, name), expected in cases.items():
            device = self._device(
                sessions=(f"sid_rdev_{platform}_{browser}_{name}",),
                platform=platform,
                browser=browser,
                name=name,
            )
            self.assertEqual(device.display_name, expected)

    def test_a_user_renames_their_device_and_nothing_else(self):
        user = new_test_user(self.env, login="rdev_renamer", groups="base.group_user")
        mine = self._device(sessions=("sid_rdev_mine",), user_id=user.id)
        theirs = self._device(sessions=("sid_rdev_theirs",))

        mine.with_user(user).write({"name": "Work laptop"})
        self.assertEqual(mine.display_name, "Work laptop")
        with self.assertRaises(AccessError):
            mine.with_user(user).write({"active": False})
        with self.assertRaises(AccessError):
            theirs.with_user(user).write({"name": "Mine now"})

    def test_rename_opens_the_rename_form(self):
        action = self._device().action_rename()
        self.assertEqual(action["res_model"], "auth.user.client")
        self.assertEqual(action["target"], "new")
        self.assertEqual(
            action["views"],
            [(self.env.ref("base.auth_user_client_view_rename").id, "form")],
        )

    def test_a_revoked_device_cannot_be_unarchived(self):
        device = self._device(active=False)
        with self.assertRaises(UserError):
            device.action_unarchive()
        self.assertFalse(device.active)

    def test_is_current_without_request(self):
        self.assertFalse(self._device().is_current)

    def test_a_device_stays_while_one_of_its_sessions_lives(self):
        device = self._device(sessions=("sid_rdev_a", "sid_rdev_b"))
        Session = self.env["auth.user.client.session"]
        self.assertEqual(Session._mark_revoked(["sid_rdev_a"]), 1)
        self.assertTrue(device.active)
        self.assertEqual(Session._mark_revoked(["sid_rdev_b"]), 1)
        self.assertFalse(device.active)
        self.assertFalse(self.env.user.auth_client_ids)
        self.assertEqual(Session._mark_revoked(["sid_rdev_b"]), 0)

    def test_revoking_a_device_ends_all_its_sessions(self):
        first, second = "sid_rdev_" + "a" * 33, "sid_rdev_" + "b" * 33
        device = self._device(sessions=(first, second))
        callbacks = Callbacks()
        with (
            patch.object(self.env.cr, "postcommit", callbacks),
            patch.object(
                type(auth_user_client.root.session_store),
                "remove_sessions_for_identifiers",
            ) as remove,
        ):
            device._revoke()
            remove.assert_not_called()
            callbacks.run()
        self.assertEqual(sorted(remove.call_args.args[0]), [first, second])
        self.assertFalse(device.active)
        self.assertFalse(
            device.with_context(active_test=False).session_ids.filtered("active")
        )

    def test_revoking_a_device_without_a_live_session_archives_it(self):
        device = self._device(sessions=())
        with patch.object(
            type(auth_user_client.root.session_store), "remove_sessions_for_identifiers"
        ) as remove:
            device._revoke()
        remove.assert_not_called()
        self.assertFalse(device.active)


class TestUpdateRevoked(DeviceCase):
    def _update_revoked_sessions(self, live, budget=float("inf")):
        store = SimpleNamespace(
            get_missing_session_identifiers=lambda identifiers: (
                set(identifiers) - set(live)
            )
        )
        with (
            patch.object(
                auth_user_client_session, "root", SimpleNamespace(session_store=store)
            ),
            patch.object(
                type(self.env["ir.cron"]), "_commit_progress", lambda *a, **k: budget
            ),
        ):
            result = self.env["auth.user.client.session"].sudo()._update_revoked()
        self.env.invalidate_all()
        return result

    def test_missing_sessions_are_revoked(self):
        gone = self._device(sessions=("sid_rdev_gone",))
        live = self._device(sessions=("sid_rdev_live",))
        recent = self._device(
            sessions=("sid_rdev_recent",), last_activity=datetime.now()
        )

        self.assertEqual(
            self._update_revoked_sessions(live={"sid_rdev_live"}), (1, False)
        )

        self.assertFalse(gone.active)
        self.assertTrue(live.active)
        self.assertTrue(recent.active, "a recently active session is not asked about")

    def test_batches_cover_every_candidate(self):
        devices = [self._device(sessions=(f"sid_rdev_{n}",)) for n in range(7)]
        with patch.object(auth_user_client, "_REVOKE_SWEEP_BATCH", 2):
            result = self._update_revoked_sessions(live={"sid_rdev_1", "sid_rdev_4"})
        self.assertEqual(result, (5, False))
        self.assertEqual(
            [device.active for device in devices],
            [False, True, False, False, True, False, False],
        )

    def test_stops_when_the_time_budget_is_spent(self):
        self._device(sessions=("sid_rdev_x",))
        self._device(sessions=("sid_rdev_y",))
        with patch.object(auth_user_client, "_REVOKE_SWEEP_BATCH", 1):
            self.assertEqual(
                self._update_revoked_sessions(live=(), budget=0), (1, True)
            )


class TestRevokedRetention(DeviceCase):
    def test_revoked_devices_expire_with_their_sessions_and_addresses(self):
        now = datetime.now()
        expired = self._device(
            sessions=("sid_rdev_old",),
            active=False,
            last_activity=now - timedelta(days=91),
        )
        session = expired.with_context(active_test=False).session_ids
        address = self.env["auth.user.client.address"].create(
            {"client_id": expired.id, "ip_address": "10.0.0.1"}
        )
        kept_recent = self._device(
            sessions=("sid_rdev_recent",),
            active=False,
            last_activity=now - timedelta(days=89),
        )
        kept_active = self._device(
            sessions=("sid_rdev_active",), last_activity=now - timedelta(days=400)
        )

        self.assertEqual(self.env["auth.user.client"]._gc_revoked_clients(), (1, False))
        self.env.invalidate_all()

        self.assertFalse(expired.exists() or session.exists() or address.exists())
        self.assertTrue(kept_recent.exists())
        self.assertTrue(kept_active.exists())

    def test_ended_sessions_of_a_live_device_expire(self):
        now = datetime.now()
        device = self._device(sessions=("sid_rdev_live",), last_activity=now)
        Session = self.env["auth.user.client.session"]
        ended = Session.create(
            {
                "client_id": device.id,
                "session_identifier": "sid_rdev_ended",
                "last_activity": now - timedelta(days=91),
                "active": False,
            }
        )
        self.assertEqual(Session._gc_ended_sessions(), (1, False))
        self.env.invalidate_all()
        self.assertFalse(ended.exists())
        self.assertEqual(device.session_ids.session_identifier, "sid_rdev_live")

    def test_recent_session_end_survives_both_cleanup_orders(self):
        Client = self.env["auth.user.client"]
        Session = self.env["auth.user.client.session"]
        for parent_first in (True, False):
            with self.subTest(parent_first=parent_first):
                client = self._device(
                    sessions=(f"sid_retention_{parent_first}",),
                    last_activity=self.env.cr.now() - timedelta(days=100),
                )
                session = client.session_ids
                Session._mark_revoked([session.session_identifier], reason="logout")
                self.env.flush_all()
                collectors = [Client._gc_revoked_clients, Session._gc_ended_sessions]
                if not parent_first:
                    collectors.reverse()
                for collect in collectors:
                    self.assertEqual(collect(), (0, False))
                self.env.invalidate_all()
                self.assertTrue(client.exists())
                self.assertTrue(session.exists())
                self.assertEqual(session.ended_at, self.env.cr.now())
                client.unlink()

    def test_expired_session_end_allows_both_cleanup_orders(self):
        Client = self.env["auth.user.client"]
        Session = self.env["auth.user.client.session"]
        for parent_first in (True, False):
            with self.subTest(parent_first=parent_first):
                client = self._device(
                    sessions=(f"sid_expired_retention_{parent_first}",),
                    active=False,
                    last_activity=self.env.cr.now() - timedelta(days=100),
                )
                session = client.with_context(active_test=False).session_ids
                session.ended_at = self.env.cr.now() - timedelta(days=91)
                self.env.flush_all()
                collectors = [Client._gc_revoked_clients, Session._gc_ended_sessions]
                if not parent_first:
                    collectors.reverse()
                for collect in collectors:
                    collect()
                self.env.invalidate_all()
                self.assertFalse(client.exists())
                self.assertFalse(session.exists())

    def test_retention_is_configurable(self):
        stale = self._device(
            active=False, last_activity=datetime.now() - timedelta(days=10)
        )
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("base.device_retention_days", "0")
        self.assertIsNone(self.env["auth.user.client"]._gc_revoked_clients())
        self.assertIsNone(self.env["auth.user.client.session"]._gc_ended_sessions())
        self.assertIsNone(self.env["auth.user.client.address"]._gc_stale_addresses())
        self.assertTrue(stale.exists())
        icp.set_param("base.device_retention_days", "7")
        self.assertEqual(self.env["auth.user.client"]._gc_revoked_clients(), (1, False))
        self.assertFalse(stale.exists())

    def test_stale_addresses_expire_but_not_the_current_one(self):
        now = datetime.now()
        device = self._device(ip_address="10.0.0.3", last_activity=now)
        Address = self.env["auth.user.client.address"]
        stale, recent, current = (
            Address.create(
                {"client_id": device.id, "ip_address": ip, "last_activity": when}
            )
            for ip, when in (
                ("10.0.0.1", now - timedelta(days=91)),
                ("10.0.0.2", now - timedelta(days=89)),
                ("10.0.0.3", now - timedelta(days=200)),
            )
        )
        self.env.flush_all()

        self.assertEqual(Address._gc_stale_addresses(), (1, False))
        self.env.invalidate_all()

        self.assertFalse(stale.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(current.exists(), "the device's current address stays")

    def test_batches_report_remaining_work(self):
        for n in range(3):
            self._device(sessions=(f"sid_rdev_{n}",), active=False)
        with patch.object(auth_user_client, "_RETENTION_BATCH", 2):
            self.assertEqual(
                self.env["auth.user.client"]._gc_revoked_clients(), (2, True)
            )
            self.assertEqual(
                self.env["auth.user.client"]._gc_revoked_clients(), (1, False)
            )


class TestEndOtherSessions(TransactionCase):
    def test_other_user_cannot_end_sessions_even_without_visible_clients(self):
        actor = new_test_user(
            self.env, login="client_epoch_actor", groups="base.group_user"
        )
        victim = new_test_user(
            self.env, login="client_epoch_victim", groups="base.group_user"
        )
        epoch = victim.session_epoch
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            victim.with_user(actor).action_revoke_all_devices.__wrapped__(
                victim.with_user(actor)
            )
        self.assertEqual(victim.session_epoch, epoch)

    def test_epoch_revocation_ends_its_persisted_associations(self):
        user = self.env.user
        client = self.env["auth.user.client"].create(
            {
                "user_id": user.id,
                "recognition_key_hash": "epoch-association-probe",
            }
        )
        association = self.env["auth.user.client.session"].create(
            {
                "client_id": client.id,
                "session_identifier": "epoch-association-session",
            }
        )
        user._end_other_sessions()
        self.assertFalse(association.active)
        self.assertEqual(association.end_reason, "revoked")
        self.assertTrue(association.ended_at)
        self.assertFalse(client.active)

    def test_the_epoch_changes_every_session_token(self):
        user = self.env.user
        before = user._get_session_token("a" * 84)
        epoch = user.session_epoch
        user._end_other_sessions()
        self.assertEqual(user.session_epoch, epoch + 1)
        self.assertNotEqual(user._get_session_token("a" * 84), before)


class TestClientAuthority(DeviceCase):
    def setUp(self):
        super().setUp()
        self.env = self.env(user=self.env.ref("base.user_admin").id, su=True)

    def test_cookie_and_user_agent_changes_do_not_rebind(self):
        self._seen("2026-07-01 08:00:00")
        client = self._devices()
        self._seen("2026-07-01 09:00:00", key="x" * 43, browser="chrome")
        self.assertEqual(self._devices(), client)
        self.assertEqual(client.recognition_key_hash, auth_user_client._sha256(KEY))
        self.assertEqual(client.browser, "chrome")

    def test_new_login_cannot_restore_a_revoked_session(self):
        self._seen("2026-07-01 08:00:00")
        client = self._devices()
        old_session = next(iter(self.sessions.values()))
        self.assertTrue(client._is_session_valid(old_session))
        client._revoke()
        self._seen("2026-07-01 09:00:00", sid="new_login" + "b" * 60)
        new_session = list(self.sessions.values())[-1]
        self.assertEqual(self._devices(), client)
        self.assertFalse(client._is_session_valid(old_session))
        self.assertTrue(client._is_session_valid(new_session))
        self.assertEqual(client.session_generation, 1)

    def test_store_cleanup_failure_does_not_restore_authority(self):
        self._seen("2026-07-01 08:00:00")
        client = self._devices()
        session = next(iter(self.sessions.values()))
        callbacks = Callbacks()
        with (
            patch.object(self.env.cr, "postcommit", callbacks),
            patch.object(
                odoo.http.root.session_store,
                "remove_sessions_for_identifiers",
                side_effect=OSError("unavailable"),
            ),
            self.assertLogs("odoo.addons.base.models.auth_user_client", "WARNING"),
        ):
            client._revoke()
            callbacks.run()
        self.assertFalse(client._is_session_valid(session))
        self.assertFalse(client.active)

    def test_user_epoch_is_checked_without_a_token_cache(self):
        self._seen("2026-07-01 08:00:00")
        session = next(iter(self.sessions.values()))
        self.assertTrue(self._devices()._is_session_valid(session))
        self.env.cr.execute(
            "UPDATE res_users SET session_epoch = COALESCE(session_epoch, 0) + 1 WHERE id = %s",
            [self.env.uid],
        )
        self.assertFalse(self._devices()._is_session_valid(session))

    def test_a_caller_holding_a_fresh_primary_cursor_opens_none(self):
        self._seen("2026-07-01 08:00:00")
        client = self._devices()
        session = next(iter(self.sessions.values()))
        with patch.object(
            type(self.env.registry),
            "cursor",
            side_effect=AssertionError("no second cursor"),
        ):
            self.assertTrue(
                client._is_session_valid(session, fresh_primary_cr=self.env.cr)
            )
            client._revoke()
            self.assertFalse(
                client._is_session_valid(session, fresh_primary_cr=self.env.cr)
            )

    def test_probe_is_bounded_and_requires_administrator(self):
        client = self._device(active=True)
        client.active = False
        orphan = self._device(sessions=())
        self.env.flush_all()
        report = client._probe_integrity(limit=1)
        self.assertEqual(report["inactive_clients_with_active_sessions"], client.ids)
        self.assertEqual(report["active_clients_without_active_sessions"], orphan.ids)
        user = new_test_user(
            self.env, login="client_probe_user", groups="base.group_user"
        )
        with self.assertRaises(AccessError):
            client.with_user(user)._probe_integrity()

    def test_binding_logs_contain_no_recognition_or_session_secrets(self):
        sid = "private_session" + "a" * 60
        with self.assertLogs("odoo.debug", "DEBUG") as logged:
            self._seen("2026-07-01 08:00:00", sid=sid)
        output = "\n".join(logged.output)
        self.assertIn("session_bound", output)
        self.assertNotIn(KEY, output)
        self.assertNotIn(sid[:42], output)


@tagged("post_install", "-at_install")
class TestConcurrentClientLogout(BaseCase):
    def test_last_two_logouts_serialize_the_client_state(self):
        db_name = get_db_name()
        prefix = f"logout-race-{uuid4().hex}"
        identifiers = [f"{prefix}-{number}" for number in range(2)]
        with db_connect(db_name).cursor() as cr:
            cr.execute(
                "INSERT INTO auth_user_client(user_id, recognition_key_hash, "
                "recognition_method, session_generation, active) "
                "VALUES (%s, %s, 'session', 0, TRUE) RETURNING id",
                [SUPERUSER_ID, prefix],
            )
            (client_id,) = cr.fetchone()
            for identifier in identifiers:
                cr.execute(
                    "INSERT INTO auth_user_client_session(client_id, session_identifier, active) "
                    "VALUES (%s, %s, TRUE)",
                    [client_id, identifier],
                )
        barrier = threading.Barrier(2, timeout=10)

        def logout(identifier):
            for attempt in range(3):
                try:
                    with db_connect(db_name).cursor() as cr:
                        cr.execute("SET LOCAL lock_timeout = '10s'")
                        cr.execute(
                            "SELECT active FROM auth_user_client WHERE id = %s",
                            [client_id],
                        )
                        if attempt == 0:
                            barrier.wait()
                        api.Environment(cr, SUPERUSER_ID, {})[
                            "auth.user.client.session"
                        ]._mark_revoked([identifier], reason="logout")
                    return attempt
                except SerializationFailure:
                    continue
            raise AssertionError("Concurrent logout exhausted serialization retries")

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                retries = list(executor.map(logout, identifiers))
            self.assertEqual(sorted(retries), [0, 1])
            with db_connect(db_name).cursor() as cr:
                cr.execute(
                    "SELECT active FROM auth_user_client WHERE id = %s", [client_id]
                )
                self.assertEqual(cr.fetchone(), (False,))
                cr.execute(
                    "SELECT count(*) FROM auth_user_client_session WHERE client_id = %s AND active",
                    [client_id],
                )
                self.assertEqual(cr.fetchone(), (0,))
        finally:
            with db_connect(db_name).cursor() as cr:
                cr.execute("DELETE FROM auth_event WHERE client_ref = %s", [client_id])
                cr.execute("DELETE FROM auth_user_client WHERE id = %s", [client_id])
