from datetime import datetime
from unittest.mock import patch

from psycopg.errors import CheckViolation, UniqueViolation

from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestCalendarSyncLink(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env["calendar.sync.account"]
        cls.startClassPatcher(
            patch.object(
                type(Account)._fields["provider"], "_selection", {"fake": "Fake"}
            )
        )
        cls.user = new_test_user(cls.env, login="link_user")
        cls.other = new_test_user(cls.env, login="link_other")
        cls.account = Account._for(cls.user, "fake")
        cls.other_account = Account._for(cls.other, "fake")
        cls.event = cls.env["calendar.event"].create(
            {
                "name": "Linked",
                "start": datetime(2026, 10, 6, 9),
                "stop": datetime(2026, 10, 6, 10),
            }
        )
        cls.recurrence = cls.env["calendar.recurrence"].create(
            {"repeat_unit": "day", "repeat_number": 2, "event_tz": "UTC"}
        )

    def _link(self, account=None, **values):
        return self.env["calendar.sync.link"].create(
            {"account_id": (account or self.account).id, **values}
        )

    def _refused(self, error, **values):
        with (
            self.assertRaises(error),
            mute_logger("odoo.db"),
            self.env.cr.savepoint(),
        ):
            self._link(**values)
            self.env.flush_all()

    def test_a_link_is_to_an_event_or_a_recurrence(self):
        self._refused(
            CheckViolation,
            event_id=self.event.id,
            recurrence_id=self.recurrence.id,
        )
        to_event = self._link(event_id=self.event.id)
        to_recurrence = self._link(recurrence_id=self.recurrence.id)
        self.assertEqual(self.event.calendar_sync_link_ids, to_event)
        self.assertEqual(self.recurrence.calendar_sync_link_ids, to_recurrence)

    def test_a_record_is_linked_to_each_account_once(self):
        self._link(event_id=self.event.id, remote_id="e1")
        self._refused(UniqueViolation, event_id=self.event.id)
        self._link(self.other_account, event_id=self.event.id, remote_id="e1")
        self.assertEqual(len(self.event.calendar_sync_link_ids), 2)

    def test_a_deleted_record_leaves_a_tombstone(self):
        link = self._link(event_id=self.event.id, remote_id="gone")
        self._link(remote_id="earlier tombstone")
        self.event.unlink()
        self.assertTrue(link.exists())
        self.assertFalse(link.event_id)
        self.assertEqual(link.remote_id, "gone")

    def test_an_account_takes_its_links_with_it(self):
        link = self._link(event_id=self.event.id)
        kept = self._link(self.other_account, event_id=self.event.id)
        self.account.unlink()
        self.assertFalse(link.exists())
        self.assertTrue(kept.exists())
