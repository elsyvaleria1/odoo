from contextlib import contextmanager
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.calendar_sync.provider import CalendarSyncProvider


@tagged("post_install", "-at_install")
class TestCalendarSyncEngine(HttpCase):
    """What every provider gets from the engine, run against a fake one."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["integration.service"].create(
            {
                "name": "Fake Calendar",
                "code": "fake_calendar",
                "endpoint_url": "https://api.fake.test",
                "environment": "production",
                "auth_type": "oauth2",
                "allow_user_credentials": True,
                "oauth_auth_endpoint": "https://login.fake.test/authorize",
                "oauth_token_endpoint": "https://login.fake.test/token",
                "oauth_scope": False,
            }
        )
        cls.env["ir.model.data"].create(
            {
                "module": "calendar_sync",
                "name": "test_service_fake",
                "model": "integration.service",
                "res_id": cls.service.id,
            }
        )
        cls.provider = CalendarSyncProvider(
            code="fake",
            label="Fake",
            key="calendar_fake",
            service="calendar_sync.test_service_fake",
            scope="calendar",
            paused_param="calendar_sync.test_fake_paused",
        )
        Account = type(cls.env["calendar.sync.account"])
        cls.startClassPatcher(
            patch.object(
                Account,
                "_calendar_sync_providers",
                lambda account: {"fake": cls.provider},
            )
        )
        cls.startClassPatcher(
            patch.object(Account._fields["provider"], "_selection", {"fake": "Fake"})
        )
        cls.user = new_test_user(cls.env, login="sync_user", groups="base.group_user")
        cls.other = new_test_user(cls.env, login="sync_other", groups="base.group_user")

    def setUp(self):
        super().setUp()
        self.ran = []
        self.restarted = []
        Users = type(self.env["res.users"])
        self.startPatcher(
            patch.object(
                Users,
                "_calendar_sync_run",
                lambda user, code: self.ran.append((user.login, code)) or True,
            )
        )
        self.startPatcher(
            patch.object(
                Users,
                "_calendar_sync_restart",
                lambda user, code: self.restarted.append((user.login, code)),
            )
        )

    def _authorize(self, user):
        connection = self.env["integration.connection"]._personal(
            self.service, user, scope="calendar"
        )
        connection._oauth_store_tokens(
            {"access_token": "a", "refresh_token": "r", "expires_in": 3600}, ""
        )
        return connection

    @contextmanager
    def _paused(self):
        Account = self.env["calendar.sync.account"]
        Account._set_paused("fake", True)
        try:
            yield
        finally:
            Account._set_paused("fake", False)

    def test_the_view_hears_every_installed_provider(self):
        self.assertEqual(
            self.env["res.users"].calendar_sync_providers(),
            [{"code": "fake", "label": "Fake", "key": "calendar_fake"}],
        )

    def test_the_status_follows_the_client_the_grant_and_the_user(self):
        def status():
            return self.user.check_synchronization_status()["calendar_fake"]

        self.assertEqual(status(), "missing_credentials")
        self.service._set_oauth_client("client", "secret", company=False)
        self.assertEqual(status(), "sync_stopped", "a client but no grant")
        self._authorize(self.user)
        self.assertEqual(status(), "sync_active")
        self.assertTrue(self.user._has_any_active_synchronization())
        self.user.calendar_sync_stop("fake")
        self.assertEqual(status(), "sync_stopped")
        with self._paused():
            self.assertEqual(status(), "sync_paused")

    def test_a_user_changes_only_their_own_synchronization(self):
        with self.assertRaises(AccessError):
            self.other.with_user(self.user).calendar_sync_stop("fake")
        with self.assertRaises(AccessError):
            self.other.with_user(self.user).calendar_sync_restart("fake")

        self.user.with_user(self.user).calendar_sync_stop("fake")
        self.assertTrue(self.user._calendar_sync_stopped("fake"))
        self.user.with_user(self.user).calendar_sync_restart("fake")
        self.assertFalse(self.user._calendar_sync_stopped("fake"))
        self.assertEqual(self.restarted, [("sync_user", "fake")])

    def test_the_cron_runs_who_authorized_and_did_not_stop(self):
        self._authorize(self.user)
        self._authorize(self.other)
        self.other.calendar_sync_stop("fake")

        with patch.object(type(self.env["ir.cron"]), "_commit_progress"):
            self.env["calendar.sync.account"]._cron_sync()

        self.assertEqual(self.ran, [("sync_user", "fake")])

    def test_a_paused_provider_is_not_run(self):
        self._authorize(self.user)
        with (
            self._paused(),
            patch.object(type(self.env["ir.cron"]), "_commit_progress"),
        ):
            self.env["calendar.sync.account"]._cron_sync()
        self.assertEqual(self.ran, [])

    def test_one_users_failure_does_not_stop_the_others(self):
        self._authorize(self.user)
        self._authorize(self.other)

        def run(user, code):
            if user.login == "sync_user":
                raise ValueError("provider down")
            self.ran.append((user.login, code))

        with (
            patch.object(type(self.env["res.users"]), "_calendar_sync_run", run),
            patch.object(self.env.cr, "rollback"),
            patch.object(type(self.env["ir.cron"]), "_commit_progress"),
        ):
            self.env["calendar.sync.account"]._cron_sync()

        self.assertEqual(self.ran, [("sync_other", "fake")])

    def _sync_data(self, code="fake"):
        return self.call_jsonrpc(
            f"/calendar_sync/{code}/sync_data", {"model": "calendar.event"}
        )

    def test_the_route_asks_for_a_client_then_an_authorization(self):
        self.authenticate("sync_user", "sync_user")
        self.assertEqual(self._sync_data()["status"], "need_config_from_admin")

        self.service._set_oauth_client("client", "secret", company=False)
        answer = self._sync_data()
        connection = self.env["integration.connection"]._find_personal(
            self.service, self.user
        )
        self.assertEqual(answer["status"], "need_auth")
        self.assertEqual(answer["url"], connection._oauth_authorize_url())
        self.assertEqual(connection.oauth_scope, "calendar")

    def test_the_route_runs_an_authorized_synchronization(self):
        self.service._set_oauth_client("client", "secret", company=False)
        self._authorize(self.user)
        self.authenticate("sync_user", "sync_user")

        self.assertEqual(self._sync_data()["status"], "need_refresh")
        self.assertEqual(self.ran, [("sync_user", "fake")])
