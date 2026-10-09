from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC
from unittest.mock import patch

from freezegun import freeze_time

from odoo import api, fields
from odoo.modules.registry import Registry
from odoo.tests.common import HttpCase

from odoo.addons.calendar_google.utils.calendar_google import (
    TIMEOUT,
    GoogleCalendarService,
)
from odoo.addons.calendar_sync.models.res_users import ResUsers as CalendarSyncUsers
from odoo.addons.mail.tests.common import mail_new_test_user


def patch_api(func):
    def patched(self, *args, **kwargs):
        with self.mock_google_sync():
            return func(self, *args, **kwargs)

    return patched


@patch.object(
    CalendarSyncUsers,
    "_calendar_sync_connection",
    lambda user, code: code == "google" and "dummy-token",
)
class TestSyncGoogle(HttpCase):
    def setUp(self):
        super().setUp()
        self.google_service = GoogleCalendarService(self.env)
        self.env["calendar.sync.account"]._set_paused("google", False)
        self.organizer_user = mail_new_test_user(self.env, login="organizer_user")
        self.attendee_user = mail_new_test_user(self.env, login="attendee_user")

    def apply_google(self, model_name, gevents, user=None, default_reminders=()):
        """What a synchronization reads of `gevents`, applied as `user` (the
        current user) receives them; the records of `model_name` it changed,
        or all of them without one."""
        user = (user or self.env.user)._calendar_sync_as_owner()
        account = user._calendar_sync_account("google")._as_engine()
        changes = self.env["calendar.sync.adapter.google"]._changes(
            gevents, default_reminders
        )
        records = account._pull(changes)
        if not model_name:
            return records
        return (
            self.env[model_name]
            .union(*(r for r in records if r._name == model_name))
            .with_env(self.env)
        )

    @contextmanager
    def mock_datetime_and_now(self, mock_dt):
        """
        Used when synchronization date (using env.cr.now()) is important
        in addition to standard datetime mocks. Used mainly to detect sync
        issues.
        """
        # cr.now() is contractually a datetime; coerce a string so consumers
        # doing datetime arithmetic on it (e.g. ir.cron._now) don't break.
        now_dt = (
            fields.Datetime.to_datetime(mock_dt)
            if isinstance(mock_dt, str)
            else mock_dt
        )
        # cr.now() is naive UTC in production; normalize a tz-aware freeze
        # point so it (and freeze_time) stay on that convention, else
        # naive/aware comparisons (e.g. ir.cron._now) crash. Mirrors mail
        # freeze_all_time.
        if now_dt.tzinfo is not None:
            now_dt = now_dt.astimezone(UTC).replace(tzinfo=None)
        with freeze_time(now_dt), patch.object(self.env.cr, "now", lambda: now_dt):
            yield

    @contextmanager
    def mock_google_sync(self):
        """Record what is sent to Google instead of sending it: (values, the
        timeout when it is not the default) per insert, per patch by id, and
        the deleted ids."""
        self._gsync_deleted_ids = []
        self._gsync_insert_values = []
        self._gsync_patch_values = defaultdict(list)

        def kwargs(timeout):
            return {} if timeout == TIMEOUT else {"timeout": timeout}

        def _mock_insert(
            service, values, connection=None, timeout=TIMEOUT, need_video_call=True
        ):
            if connection:
                self._gsync_insert_values.append((values, kwargs(timeout)))
            return {}

        def _mock_patch(service, event_id, values, connection=None, timeout=TIMEOUT):
            if connection:
                self._gsync_patch_values[event_id].append((values, kwargs(timeout)))

        def _mock_delete(service, event_id, connection=None, timeout=TIMEOUT):
            if connection:
                self._gsync_deleted_ids.append(event_id)

        with (
            self.env.cr.savepoint(),
            patch.object(GoogleCalendarService, "insert", _mock_insert),
            patch.object(GoogleCalendarService, "patch", _mock_patch),
            patch.object(GoogleCalendarService, "delete", _mock_delete),
        ):
            yield

    def push_google(self):
        """What a commit does next: flush, then send what waits for it."""
        self.env.flush_all()
        funcs = self.env.cr.postcommit._funcs
        while funcs:
            funcs.popleft()()
        self.env.invalidate_all()

    def send_google(self, records):
        """What a run sends of `records`, each through the account Google takes
        its changes from; a linked record is sent whatever its state."""
        self.set_google_pending(records)
        Account = self.env["calendar.sync.account"]
        running = (
            Account._for(self.env.user, "google")
            if self.env.user._calendar_sync_active("google")
            else Account
        )
        by_writer = {}
        for record in records:
            if writer := Account._writer(record, "google", running):
                by_writer.setdefault(writer.id, []).append((record._name, record.id))
        self.env.flush_all()
        with Registry(self.env.cr.dbname).cursor() as cr:
            Accounts = api.Environment(cr, self.env.uid, {})["calendar.sync.account"]
            for account_id, only in by_writer.items():
                account = Accounts._as_engine().browse(account_id)
                owner = account.user_id._calendar_sync_as_owner()
                account.with_env(owner.env).with_context(**self.env.context)._push(only)
        self.env.invalidate_all()

    def google_id(self, record):
        """`record`'s id in Google; its links must agree on one."""
        return record._google_id()

    def find_google(self, model, value, operator="="):
        """The records of `model` Google holds under ids matching `value`."""
        field = self.env["calendar.sync.link"]._field_of(model)
        links = (
            self.env["calendar.sync.link"]
            ._engine()
            .search(
                [
                    ("account_id.provider", "=", "google"),
                    ("remote_id", operator, value),
                    (field, "!=", False),
                ]
            )
        )
        return model.search([("id", "in", links[field].ids)])

    def link_google(self, records, google_ids, user=None):
        """Link `records` to `google_ids`, one for all or one per record (a
        falsy one unlinks), in `user`'s calendar, the current user's by
        default; `records`."""
        if not isinstance(google_ids, list):
            google_ids = [google_ids] * len(records)
        account = self.env["calendar.sync.account"]._for(
            user or self.env.user, "google"
        )
        for record, google_id in zip(records, google_ids, strict=True):
            record._google_unlink()
            if google_id:
                record._google_link(account, {record.id: google_id})
        if records._name == "calendar.recurrence":
            records.calendar_event_ids._google_link_instances()
        return records

    def google_pending(self, record):
        """Whether Google has yet to hear of `record`: a link of it waits to be
        sent, or it has none and is active."""
        links = self.env["calendar.sync.link"]._of(record, "google")
        return bool(links.filtered("pending")) or (not links and record.active)

    def set_google_pending(self, records, pending=True):
        self.env["calendar.sync.link"]._of(records, "google").pending = pending

    @contextmanager
    def mock_google_service(self):
        self._gservice_request_uris = []

        def _mock_request(service, connection, method, path, **kwargs):
            self._gservice_request_uris.append(path)
            return {}

        with patch.object(
            GoogleCalendarService,
            "_request",
            autospec=True,
            side_effect=_mock_request,
        ):
            yield

    def assertGoogleEventDeleted(self, google_id):
        self.push_google()
        self.assertIn(
            google_id, self._gsync_deleted_ids, "Event should have been deleted"
        )

    def assertGoogleEventNotDeleted(self):
        self.push_google()
        self.assertFalse(self._gsync_deleted_ids)

    def assertGoogleEventInserted(self, values, timeout=None):
        self.push_google()
        self.assertEqual(len(self._gsync_insert_values), 1)
        matching = []
        for insert_values, insert_kwargs in self._gsync_insert_values:
            if all(
                insert_values.get(key, False) == value for key, value in values.items()
            ):
                matching.append((insert_values, insert_kwargs))
        self.assertGreaterEqual(
            len(matching), 1, "There must be at least 1 matching insert."
        )
        insert_values, insert_kwargs = matching[0]
        self.assertDictEqual(insert_kwargs, {"timeout": timeout} if timeout else {})

    def assertGoogleEventInsertedMultiTime(self, values, timeout=None):
        self.push_google()
        self.assertGreaterEqual(len(self._gsync_insert_values), 1)
        matching = []
        for insert_values, insert_kwargs in self._gsync_insert_values:
            if all(
                insert_values.get(key, False) == value for key, value in values.items()
            ):
                matching.append((insert_values, insert_kwargs))
        self.assertGreaterEqual(
            len(matching), 1, "There must be at least 1 matching insert."
        )
        insert_values, insert_kwargs = matching[0]
        self.assertDictEqual(insert_kwargs, {"timeout": timeout} if timeout else {})

    def assertGoogleEventNotInserted(self):
        self.push_google()
        self.assertFalse(self._gsync_insert_values)

    def assertGoogleEventPatched(self, google_id, values, timeout=None):
        self.push_google()
        patch_values_all = self._gsync_patch_values.get(google_id)
        self.assertTrue(patch_values_all)
        matching = []
        for patch_values, patch_kwargs in patch_values_all:
            if all(patch_values.get(key, False) == values[key] for key in values):
                matching.append((patch_values, patch_kwargs))
        self.assertGreaterEqual(
            len(matching), 1, "There must be at least 1 matching patch."
        )
        patch_values, patch_kwargs = matching[0]
        self.assertDictEqual(patch_kwargs, {"timeout": timeout} if timeout else {})

    def assertGoogleEventNotPatched(self):
        self.push_google()
        self.assertFalse(self._gsync_patch_values)

    def assertGoogleAPINotCalled(self):
        self.assertGoogleEventNotPatched()
        self.assertGoogleEventNotInserted()
        self.assertGoogleEventNotDeleted()

    def assertGoogleEventSendUpdates(self, expected_value):
        self.push_google()
        self.assertEqual(len(self._gservice_request_uris), 1)
        uri = self._gservice_request_uris[0]
        uri_parameter = "sendUpdates=%s" % expected_value
        self.assertIn(uri_parameter, uri, "The URL should contain %s" % uri_parameter)

    def call_post_commit_hooks(self):
        self.push_google()
