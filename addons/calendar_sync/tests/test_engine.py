import dataclasses
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import SQL

from odoo.addons.calendar_sync.provider import (
    CalendarSyncCapabilities,
    CalendarSyncProvider,
)
from odoo.addons.calendar_sync.remote import ErrorKind, RemoteKind
from odoo.addons.calendar_sync.tests.fake_calendar import FakeAdapter, FakeCalendars

START, STOP = datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 10)
LATER = datetime(2100, 1, 1)


@tagged("post_install", "-at_install")
class TestCalendarSyncEngine(TransactionCase):
    """The engine against two fake providers: "fake_outlook" gives an item an id
    per calendar, "fake_google" one id in every calendar and takes the insert id
    as the item's."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.providers = {}
        for code, capabilities in (
            ("fake_outlook", CalendarSyncCapabilities()),
            (
                "fake_google",
                CalendarSyncCapabilities(shared_ids=True, client_insert_id=True),
            ),
        ):
            service = cls.env["integration.service"].create(
                {
                    "name": f"Fake {code}",
                    "code": f"fake_{code}",
                    "endpoint_url": f"https://{code}.fake.test",
                    "environment": "production",
                    "auth_type": "oauth2",
                    "allow_user_credentials": True,
                    "oauth_auth_endpoint": f"https://{code}.fake.test/authorize",
                    "oauth_token_endpoint": f"https://{code}.fake.test/token",
                    "oauth_scope": False,
                }
            )
            service._set_oauth_client("client", "secret", company=False)
            cls.env["ir.model.data"].create(
                {
                    "module": "calendar_sync",
                    "name": f"test_engine_{code}",
                    "model": "integration.service",
                    "res_id": service.id,
                }
            )
            cls.providers[code] = (
                service,
                CalendarSyncProvider(
                    code=code,
                    label=code.title(),
                    key=f"calendar_{code}",
                    service=f"calendar_sync.test_engine_{code}",
                    scope="calendar",
                    paused_param=f"calendar_sync.test_{code}_paused",
                    adapter="calendar.sync.adapter",
                    capabilities=capabilities,
                ),
            )
        # beside the providers installed, whose adapters keep running
        Account = type(cls.env["calendar.sync.account"])
        installed = Account._calendar_sync_providers
        cls.startClassPatcher(
            patch.object(
                Account,
                "_calendar_sync_providers",
                lambda account: {
                    **installed(account),
                    **{code: p for code, (__, p) in cls.providers.items()},
                },
            )
        )
        field = Account._fields["provider"]
        cls.startClassPatcher(
            patch.object(
                field,
                "_selection",
                {
                    **dict(field._selection),
                    "fake_outlook": "Fake Outlook",
                    "fake_google": "Fake Google",
                },
            )
        )
        cls.organizer = new_test_user(cls.env, login="engine_organizer")
        cls.attendee = new_test_user(cls.env, login="engine_attendee")

    def setUp(self):
        super().setUp()
        self.servers = {
            "fake_outlook": FakeCalendars("fake_outlook", shared_ids=False),
            "fake_google": FakeCalendars("fake_google", shared_ids=True),
        }
        Account = type(self.env["calendar.sync.account"])
        installed = Account._adapter_of
        self.startPatcher(
            patch.object(
                Account,
                "_adapter_of",
                lambda account, code: (
                    FakeAdapter(self.servers[code])
                    if code in self.servers
                    else installed(account, code)
                ),
            )
        )

    # -- helpers -------------------------------------------------------------

    def _authorize(self, user, code="fake_outlook"):
        connection = self.env["integration.connection"]._personal(
            self.providers[code][0], user, scope="calendar"
        )
        connection._oauth_store_tokens(
            {"access_token": "a", "refresh_token": "r", "expires_in": 3600}, ""
        )
        return user._calendar_sync_account(code)

    def _sync(self, user, code="fake_outlook"):
        result = user.with_user(user).sudo()._calendar_sync_run(code)
        self._push()
        return result

    def _push(self):
        """What a commit does: flush, then run what waits for the commit."""
        self.env.flush_all()
        funcs = self.env.cr.postcommit._funcs
        while funcs:
            funcs.popleft()()
        self.env.invalidate_all()

    def _links(self, record, code="fake_outlook"):
        return self.env["calendar.sync.link"]._of(record, code)

    def _event(self, organizer=None, context=None, **values):
        organizer = organizer or self.organizer
        return (
            self.env["calendar.event"]
            .with_user(organizer)
            .with_context(**(context or {}))
            .create(
                {
                    "name": "Meeting",
                    "start": START,
                    "stop": STOP,
                    "user_id": organizer.id,
                    "partner_ids": [(6, 0, (organizer | self.attendee).partner_id.ids)],
                    **values,
                }
            )
        )

    def _capabilities(self, code="fake_outlook", **capabilities):
        """`code`'s provider with `capabilities` changed, for this test."""
        service, provider = self.providers[code]
        self.providers[code] = (
            service,
            dataclasses.replace(
                provider,
                capabilities=dataclasses.replace(provider.capabilities, **capabilities),
            ),
        )
        self.addCleanup(self.providers.__setitem__, code, (service, provider))

    def _linked_event(self, code="fake_outlook", **values):
        """An event the organizer's calendar holds, in sync."""
        account = self._authorize(self.organizer, code)
        event = self._event(**values)
        self._push()
        self.servers[code].sent.clear()
        return account, event

    # -- pull ----------------------------------------------------------------

    def test_a_remote_event_is_created_once_and_linked(self):
        account = self._authorize(self.organizer)
        server = self.servers["fake_outlook"]
        remote_id = server.add(account, name="From Outlook", start=START, stop=STOP)

        self.assertTrue(self._sync(self.organizer))
        link = self.env["calendar.sync.link"].search([("remote_id", "=", remote_id)])
        self.assertEqual(link.account_id, account)
        self.assertEqual(link.event_id.name, "From Outlook")
        self.assertEqual(link.universal_id, f"uid-{remote_id}")
        self.assertFalse(link.pending)
        self.assertEqual(server.sent, [], "what came from Outlook is not sent back")

        self.assertFalse(self._sync(self.organizer), "nothing changed")
        self.assertEqual(
            self.env["calendar.event"].search_count([("name", "=", "From Outlook")]), 1
        )

    def test_a_remote_change_applies_only_when_newer_than_odoo(self):
        account, event = self._linked_event()
        remote_id = self._links(event).remote_id
        server = self.servers["fake_outlook"]

        server.change(account, remote_id, name="Older than Odoo's")
        self._sync(self.organizer)
        self.assertEqual(event.name, "Meeting")

        server.change(account, remote_id, name="Newer", updated=LATER)
        self._sync(self.organizer)
        self.assertEqual(event.name, "Newer")

    def test_an_unchanged_version_is_not_applied_again(self):
        account, event = self._linked_event()
        link = self._links(event)
        server = self.servers["fake_outlook"]
        server.change(account, link.remote_id, name="Remote", updated=LATER)
        self._sync(self.organizer)
        event.with_context(calendar_sync_applying="fake_outlook").name = "Local"

        server.changed[account.id] = [link.remote_id]
        self._sync(self.organizer)
        self.assertEqual(event.name, "Local", "the same version is not read twice")

    def test_an_item_of_another_calendar_is_adopted_by_its_universal_id(self):
        __, event = self._linked_event()
        organizer_link = self._links(event)
        attendee_account = self._authorize(self.attendee)
        server = self.servers["fake_outlook"]
        copy_id = server.add(
            attendee_account,
            name="Meeting",
            start=START,
            stop=STOP,
            uid=organizer_link.universal_id,
        )

        self._sync(self.attendee)
        links = self._links(event)
        self.assertEqual(len(links), 2)
        self.assertEqual(
            links.filtered(lambda l: l.account_id == attendee_account).remote_id,
            copy_id,
        )
        self.assertEqual(
            self.env["calendar.event"].search_count([("name", "=", "Meeting")]), 1
        )

    def test_a_shared_id_is_adopted_by_another_calendar(self):
        __, event = self._linked_event("fake_google")
        remote_id = self._links(event, "fake_google").remote_id
        attendee_account = self._authorize(self.attendee, "fake_google")
        self.servers["fake_google"].add(
            attendee_account,
            remote_id,
            name="Meeting",
            start=START,
            stop=STOP,
            uid="other",
        )

        self._sync(self.attendee, "fake_google")
        self.assertEqual(
            self._links(event, "fake_google").mapped("remote_id"),
            [remote_id, remote_id],
        )

    def test_the_providers_hint_links_a_record_with_no_link(self):
        account = self._authorize(self.organizer)
        event = self._event(name="Made in Odoo")
        self._links(event).unlink()
        self.servers["fake_outlook"].calendar(account).clear()
        remote_id = self.servers["fake_outlook"].add(
            account, name="Made in Odoo", start=START, stop=STOP, hint=event.id
        )

        self._sync(self.organizer)
        self.assertEqual(self._links(event).remote_id, remote_id)

    def test_the_organizer_deletes_an_attendee_declines(self):
        account, event = self._linked_event()
        server = self.servers["fake_outlook"]
        server.change(account, self._links(event).remote_id, cancelled=True)
        self._sync(self.organizer)
        self.assertFalse(event.exists())

        account, event = self._linked_event()
        attendee_account = self._authorize(self.attendee)
        copy_id = server.add(
            attendee_account, uid=self._links(event).universal_id, name="Meeting"
        )
        self._sync(self.attendee)
        server.change(attendee_account, copy_id, cancelled=True)
        self._sync(self.attendee)
        self.assertTrue(event.exists())
        self.assertEqual(
            event.attendee_ids.filtered(
                lambda a: a.partner_id == self.attendee.partner_id
            ).state,
            "declined",
        )

    def test_a_series_is_created_with_its_events_linked_to_its_occurrences(self):
        account = self._authorize(self.organizer)
        server = self.servers["fake_outlook"]
        master = server.add(
            account, kind=RemoteKind.SERIES, name="Daily", start=START, stop=STOP
        )
        occurrences = [
            server.add(
                account,
                kind=RemoteKind.OCCURRENCE,
                master=master,
                name="Daily",
                start=START + timedelta(days=day),
                stop=STOP + timedelta(days=day),
            )
            for day in range(2)
        ]

        self._sync(self.organizer)
        Link = self.env["calendar.sync.link"]._engine()
        recurrence = Link.search([("remote_id", "=", master)]).recurrence_id
        self.assertTrue(recurrence)
        self.assertEqual(
            [Link.search([("remote_id", "=", rid)]).event_id for rid in occurrences],
            list(recurrence.calendar_event_ids.sorted("start")),
        )
        self.assertEqual(server.sent, [], "a series read from Outlook is not sent back")

    def test_an_occurrence_changed_alone_goes_to_its_series(self):
        """An item of a series this calendar holds, listed without its series,
        changes that series' event; it is never an event of its own."""
        account = self._authorize(self.organizer)
        server = self.servers["fake_outlook"]
        master = server.add(
            account, kind=RemoteKind.SERIES, name="Daily", start=START, stop=STOP
        )
        occurrences = [
            server.add(
                account,
                kind=RemoteKind.OCCURRENCE,
                master=master,
                name="Daily",
                start=START + timedelta(days=day),
                stop=STOP + timedelta(days=day),
            )
            for day in range(2)
        ]
        self._sync(self.organizer)
        Link = self.env["calendar.sync.link"]._engine()
        Link.search([("remote_id", "in", occurrences)]).unlink()
        events = self.env["calendar.event"].search_count([])

        server.change(account, occurrences[1], name="Moved in Outlook", updated=LATER)
        self._sync(self.organizer)

        self.assertEqual(self.env["calendar.event"].search_count([]), events)
        event = Link.search([("remote_id", "=", occurrences[1])]).event_id
        self.assertEqual(event.name, "Moved in Outlook")
        self.assertEqual(
            event.recurrence_id, Link.search([("remote_id", "=", master)]).recurrence_id
        )

    def test_a_stale_token_reads_the_whole_calendar(self):
        account = self._authorize(self.organizer)
        self.servers["fake_outlook"].add(account, name="Kept", start=START, stop=STOP)
        account.sync_token = "stale"
        self.servers["fake_outlook"].changed.clear()
        self._sync(self.organizer)
        self.assertEqual(
            self.env["calendar.event"].search_count([("name", "=", "Kept")]), 1
        )
        self.assertNotEqual(account.sync_token, "stale")

    # -- push ----------------------------------------------------------------

    def test_an_event_is_inserted_through_its_organizer(self):
        account = self._authorize(self.organizer)
        self._authorize(self.attendee)
        event = self._event()
        self._push()
        server = self.servers["fake_outlook"]
        link = self._links(event)
        self.assertEqual(link.account_id, account)
        self.assertEqual(server.sent, [("insert", account.id, link.remote_id)])
        self.assertFalse(link.pending)
        self.assertTrue(link.insert_id)

    def test_an_event_of_an_organizer_who_does_not_synchronize_is_not_inserted(self):
        self._authorize(self.attendee)
        event = self._event()
        self._sync(self.attendee)
        self.assertFalse(self._links(event))
        self.assertEqual(self.servers["fake_outlook"].sent, [])

    def test_an_edit_is_sent_by_the_organizer_and_clears_every_link(self):
        account, event = self._linked_event()
        attendee_account = self._authorize(self.attendee)
        self.servers["fake_outlook"].add(
            attendee_account, uid=self._links(event).universal_id, name="Meeting"
        )
        self._sync(self.attendee)
        self.servers["fake_outlook"].sent.clear()

        event.with_user(self.organizer).name = "Renamed"
        self.assertEqual(self._links(event).mapped("pending"), [True, True])
        self._push()
        self.assertEqual(
            self.servers["fake_outlook"].sent,
            [
                (
                    "patch",
                    account.id,
                    self._links(event)
                    .filtered(lambda l: l.account_id == account)
                    .remote_id,
                )
            ],
        )
        self.assertEqual(self._links(event).mapped("pending"), [False, False])

    def test_an_edit_sends_that_record_alone_and_at_once(self):
        account, event = self._linked_event()
        waiting = self._event(
            name="Waiting for the next run", context={"no_calendar_sync": True}
        )
        self._push()
        self.servers["fake_outlook"].sent.clear()
        self.servers["fake_outlook"].contexts.clear()

        event.with_user(self.organizer).name = "Renamed"
        self._push()
        self.assertEqual(
            self.servers["fake_outlook"].sent,
            [("patch", account.id, self._links(event).remote_id)],
        )
        self.assertTrue(
            self.servers["fake_outlook"].contexts[0]["calendar_sync_interactive"]
        )
        self.assertFalse(self._links(waiting))

        self._sync(self.organizer)
        self.assertTrue(self._links(waiting).remote_id, "the run sends the rest")

    def test_a_first_synchronization_sends_without_mails(self):
        self._authorize(self.organizer)
        self._event(context={"no_calendar_sync": True})
        self._sync(self.organizer)
        self.assertTrue(self.servers["fake_outlook"].contexts[0]["calendar_sync_quiet"])

        self._event(name="Later")
        self._sync(self.organizer)
        self.assertFalse(
            self.servers["fake_outlook"].contexts[-1]["calendar_sync_quiet"]
        )

    def test_an_answer_goes_out_through_the_organizer(self):
        account, event = self._linked_event()
        self._authorize(self.attendee)
        attendee = event.attendee_ids.filtered(
            lambda a: a.partner_id == self.attendee.partner_id
        )
        attendee.with_user(self.attendee).do_accept()
        self._push()
        self.assertEqual(
            self.servers["fake_outlook"].sent,
            [("patch", account.id, self._links(event).remote_id)],
        )

    def test_an_answer_goes_out_from_the_attendees_own_calendar(self):
        """With an answer endpoint, an attendee answers in their own calendar,
        under the id their copy has there: the organizer's copy is not sent."""
        self._capabilities(answer_endpoint=True)
        __, event = self._linked_event()
        server = self.servers["fake_outlook"]
        attendee_account = self._authorize(self.attendee)
        copy = server.add(attendee_account, uid=self._links(event).universal_id)
        attendee = event.attendee_ids.filtered(
            lambda a: a.partner_id == self.attendee.partner_id
        )
        attendee.with_user(self.attendee).do_accept()
        self._push()
        self.assertEqual(
            server.sent, [("answer", attendee_account.id, copy, "accepted")]
        )
        self.assertEqual(
            self._links(event)
            .filtered(lambda link: link.account_id == attendee_account)
            .remote_id,
            copy,
            "the attendee's calendar is linked: the next answer needs no lookup",
        )
        self.assertFalse(self._links(event).filtered("pending"))

    def test_a_series_is_not_inserted_where_odoo_makes_none(self):
        self._capabilities(series_inserts=False)
        self._authorize(self.organizer)
        event = self._event(recurrency=True)
        event._apply_recurrence_values(
            {
                "repeat_unit": "day",
                "repeat_interval": 1,
                "repeat_number": 2,
                "event_tz": "UTC",
            }
        )
        self._push()
        self._sync(self.organizer)
        self.assertFalse(self.servers["fake_outlook"].sent)

    def test_a_record_the_provider_would_refuse_is_refused_alone(self):
        """A record the adapter knows the provider refuses is not sent and is
        noted once; the others go on."""
        self._authorize(self.organizer)
        server = self.servers["fake_outlook"]
        refused, sent = self._event(name="Refused"), self._event(name="Sent")
        server.refusals[refused.id] = "an attendee has no email address"
        self._push()
        self._sync(self.organizer)

        self.assertEqual(self._links(refused).error, "an attendee has no email address")
        self.assertFalse(self._links(refused).remote_id)
        self.assertTrue(self._links(sent).remote_id)
        self.assertEqual(
            len(
                refused.message_ids.filtered(
                    lambda m: "refused this event" in (m.body or "")
                )
            ),
            1,
        )

    def test_an_insert_tells_the_adapter_what_it_inserted(self):
        account = self._authorize(self.organizer)
        event = self._event()
        self._push()
        self.assertEqual(
            self.servers["fake_outlook"].inserted, [(account.id, event.id)]
        )

    def test_an_unsynced_field_is_not_sent(self):
        __, event = self._linked_event()
        event.with_user(self.organizer).description = "notes"
        self.assertFalse(self._links(event).pending)

    def _assert_inserted_once_after_a_lost_answer(self, code):
        server = self.servers[code]
        account = self._authorize(self.organizer, code)
        server.lose_insert_answers = 1
        event = self._event()
        self._push()
        self.assertFalse(self._links(event, code).remote_id)

        self._sync(self.organizer, code)
        self.assertEqual(
            list(server.calendar(account)), [self._links(event, code).remote_id]
        )
        self.assertEqual(
            self.env["calendar.event"].search_count([("name", "=", event.name)]),
            1,
            "reading the item back does not make a second event of it",
        )

    def test_an_insert_whose_answer_was_lost_is_not_made_twice(self):
        self._assert_inserted_once_after_a_lost_answer("fake_outlook")

    def test_an_insert_with_its_own_id_whose_answer_was_lost_is_adopted(self):
        self._assert_inserted_once_after_a_lost_answer("fake_google")

    def test_a_deleted_event_is_deleted_from_the_calendars_holding_it(self):
        account, event = self._linked_event()
        remote_id = self._links(event).remote_id
        event.unlink()
        tombstone = (
            self.env["calendar.sync.link"]
            ._engine()
            .search([("remote_id", "=", remote_id)])
        )
        self.assertFalse(tombstone.event_id)
        self._push()
        self.assertEqual(
            self.servers["fake_outlook"].sent, [("delete", account.id, remote_id)]
        )
        self.assertFalse(tombstone.exists())

    def test_an_archived_event_is_deleted_remotely_and_unlinked(self):
        account, event = self._linked_event()
        remote_id = self._links(event).remote_id
        event.with_user(self.organizer).active = False
        self._push()
        self.assertEqual(
            self.servers["fake_outlook"].sent, [("delete", account.id, remote_id)]
        )
        self.assertFalse(self._links(event))

    def test_a_refused_event_is_noted_once_and_not_sent_again(self):
        self._authorize(self.organizer)
        server = self.servers["fake_outlook"]
        server.fail("insert", ErrorKind.FORBIDDEN)
        event = self._event()
        self._push()
        link = self._links(event)
        self.assertIn("refused", link.error)
        notes = event.message_ids.filtered(
            lambda m: "refused this event" in (m.body or "")
        )
        self.assertEqual(len(notes), 1)

        self._sync(self.organizer)
        self._sync(self.organizer)
        self.assertEqual(
            len(
                event.message_ids.filtered(
                    lambda m: "refused this event" in (m.body or "")
                )
            ),
            1,
        )

        server.failing.clear()
        event.with_user(self.organizer).name = "Fixed"
        self._push()
        self.assertTrue(self._links(event).remote_id, "a change sends it again")

    def test_an_item_gone_from_a_calendar_of_its_own_is_unlinked(self):
        account, event = self._linked_event()
        self.servers["fake_outlook"].calendar(account).clear()
        event.with_user(self.organizer).name = "Renamed"
        self._push()
        self.assertFalse(self._links(event))

    def test_an_item_gone_with_shared_ids_keeps_its_link(self):
        account, event = self._linked_event("fake_google")
        self.servers["fake_google"].calendar(account).clear()
        event.with_user(self.organizer).name = "Renamed"
        self._push()
        self.assertTrue(self._links(event, "fake_google").remote_id)
        self.assertFalse(self._links(event, "fake_google").pending)

    def test_a_throttled_calendar_stops_the_push_and_keeps_it_pending(self):
        __, event = self._linked_event()
        self.servers["fake_outlook"].fail("patch", ErrorKind.THROTTLED)
        event.with_user(self.organizer).name = "Later"
        self._push()
        self.assertTrue(self._links(event).pending)

    def test_a_user_who_stopped_does_not_mark_their_edits(self):
        __, event = self._linked_event()
        self.organizer.calendar_sync_stop("fake_outlook")
        event.with_user(self.organizer).name = "Kept here"
        self.assertFalse(self._links(event).pending)

    def test_a_change_read_from_one_provider_is_sent_to_the_other(self):
        account, event = self._linked_event()
        google_account = self._authorize(self.organizer, "fake_google")
        self._sync(self.organizer, "fake_google")
        google_id = self._links(event, "fake_google").remote_id
        self.assertTrue(google_id)
        self.servers["fake_google"].sent.clear()

        self.servers["fake_outlook"].change(
            account, self._links(event).remote_id, name="From Outlook", updated=LATER
        )
        self._sync(self.organizer)
        self.assertEqual(event.name, "From Outlook")
        self.assertEqual(
            self.servers["fake_google"].sent, [("patch", google_account.id, google_id)]
        )
        self.assertEqual(self.servers["fake_outlook"].sent, [])

    def test_the_reminder_cron_leaves_linked_events_to_the_provider(self):
        __, linked = self._linked_event()
        local = self._event(name="Local only", user_id=False)
        self._links(local).unlink()
        condition = self.env[
            "calendar.alarm_manager"
        ]._get_notify_alert_extra_conditions()
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "SELECT event.id FROM calendar_event event WHERE event.id = ANY(%s) %s",
                (linked | local).ids,
                condition,
            )
        )
        self.assertEqual([row[0] for row in self.env.cr.fetchall()], local.ids)
