"""What every adapter answers the same, held against the provider's own API.

An adapter's `tests/test_contract.py` mixes `CalendarSyncContract` into an
HttpCase and supplies `fake_server()`: a `FakeCalendarServer` answering the
provider's service at its `_request`, so the adapter's transport and its
conversions run as they do against the provider."""

from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.addons.calendar_sync.models.res_users import ResUsers as CalendarSyncUsers
from odoo.addons.mail.tests.common import mail_new_test_user


class FakeCalendarServer:
    """A provider's calendars, kept in memory and spoken to in its own API.

    The scenarios read and drive it through this interface alone; ids are
    the ones the provider gives, in the calendar of the user they belong to."""

    def __init__(self, env) -> None:
        self.env = env
        # (user id, operation, remote id) of every change Odoo sent
        self.ops: list[tuple[int, str, str]] = []
        # {operation: HTTP status} refused once each
        self.refusals: dict[str, int] = {}
        # inserts that land and then lose their answer
        self.lost_answers = 0
        # when the provider says its changes happened: far ahead by default,
        # so they read as newer than anything Odoo wrote; a scenario sets it
        # to put a change before or after one of Odoo's
        self.clock = datetime(2100, 1, 1)

    def stamp(self, version: int) -> datetime:
        """The time of the provider's `version`th change, naive UTC."""
        return self.clock + timedelta(seconds=version)

    @staticmethod
    def connection(user) -> str:
        return f"connection-{user.id}"

    def user_of(self, connection):
        return self.env["res.users"].browse(int(connection.rsplit("-", 1)[1]))

    def patched(self):
        """The patch that puts this server behind the provider's service."""
        raise NotImplementedError

    # -- what someone does in the provider's own calendars -------------------

    def add(self, user, name, start, stop, attendees=()) -> str:
        """An item `user` creates in their calendar, inviting `attendees`;
        its id there."""
        raise NotImplementedError

    def rename(self, user, remote_id, name) -> None:
        raise NotImplementedError

    def delete(self, user, remote_id) -> None:
        """`user` deletes the item: the organizer cancels it for everyone, an
        attendee removes their copy."""
        raise NotImplementedError

    def expire_token(self, user) -> None:
        raise NotImplementedError

    # -- what the provider holds ----------------------------------------------

    def items(self, user) -> dict[str, dict]:
        """{remote id: {"name", "start", "stop", "answers": {email: state}}}
        of the live items of `user`'s calendar, states in Odoo's words."""
        raise NotImplementedError

    def copy_id(self, user, remote_id_elsewhere) -> str | None:
        """The id `user`'s calendar has for the item another calendar knows
        as `remote_id_elsewhere`."""
        raise NotImplementedError


class CalendarSyncContract:
    """Scenarios every adapter answers the same."""

    # the scenarios are this mixin's, run by each adapter's class
    allow_inherited_tests_method = True
    code = None

    def fake_server(self) -> FakeCalendarServer:
        raise NotImplementedError

    def setUp(self):
        super().setUp()
        self.server = self.fake_server()
        Account = self.env["calendar.sync.account"]
        Account._set_paused(self.code, False)
        self.organizer = mail_new_test_user(
            self.env, login="contract_organizer", email="organizer@contract.test"
        )
        self.attendee = mail_new_test_user(
            self.env, login="contract_attendee", email="attendee@contract.test"
        )
        self.outsider = mail_new_test_user(
            self.env, login="contract_outsider", email="outsider@contract.test"
        )
        self.synchronizing = self.organizer | self.attendee
        server = self.server
        synchronizing = self.synchronizing

        def connection(user, code):
            if code == self.code and user in synchronizing:
                return server.connection(user)
            return self.env["integration.connection"]

        self.startPatcher(
            patch.object(CalendarSyncUsers, "_calendar_sync_connection", connection)
        )
        self.startPatcher(server.patched())
        self.start = datetime.now().replace(microsecond=0) + timedelta(days=3)
        self.stop = self.start + timedelta(hours=1)

    # -- helpers -------------------------------------------------------------

    def sync(self, user):
        """A run of `user`'s synchronization, and what it sends."""
        result = user.with_user(user).sudo()._calendar_sync_run(self.code)
        self.push()
        return result

    def push(self):
        """What a commit does next: flush, then send what waits for it."""
        self.env.flush_all()
        funcs = self.env.cr.postcommit._funcs
        while funcs:
            funcs.popleft()()
        self.env.invalidate_all()

    def link(self, record, user):
        Link = self.env["calendar.sync.link"]._engine()
        return Link.search(
            [
                ("account_id.user_id", "=", user.id),
                ("account_id.provider", "=", self.code),
                (Link._field_of(record), "=", record.id),
            ]
        )

    def event(self, organizer=None, **values):
        organizer = organizer or self.organizer
        return (
            self.env["calendar.event"]
            .with_user(organizer)
            .create(
                {
                    "name": "Planning",
                    "start": self.start,
                    "stop": self.stop,
                    "user_id": organizer.id,
                    "partner_ids": [(6, 0, (organizer | self.attendee).partner_id.ids)],
                    **values,
                }
            )
        )

    def events_named(self, name):
        return self.env["calendar.event"].search([("name", "=", name)])

    def ops_of(self, user):
        return [op[1:] for op in self.server.ops if op[0] == user.id]

    # -- read from the provider ------------------------------------------------

    def test_an_item_of_the_calendar_becomes_one_event(self):
        remote_id = self.server.add(
            self.organizer, "From the provider", self.start, self.stop, [self.attendee]
        )
        self.sync(self.organizer)
        event = self.events_named("From the provider")
        self.assertEqual(len(event), 1)
        self.assertEqual(event.user_id, self.organizer)
        self.assertEqual((event.start, event.stop), (self.start, self.stop))
        self.assertIn(self.attendee.partner_id, event.partner_ids)
        self.assertEqual(self.link(event, self.organizer).remote_id, remote_id)
        self.assertEqual(self.server.ops, [], "what was read is not sent back")

        self.sync(self.organizer)
        self.assertEqual(len(self.events_named("From the provider")), 1)

    def test_a_renamed_item_renames_its_event(self):
        remote_id = self.server.add(self.organizer, "Before", self.start, self.stop)
        self.sync(self.organizer)
        self.server.rename(self.organizer, remote_id, "After")
        self.sync(self.organizer)
        self.assertFalse(self.events_named("Before"))
        self.assertEqual(len(self.events_named("After")), 1)

    def test_an_item_its_organizer_deletes_deletes_the_event(self):
        remote_id = self.server.add(self.organizer, "Cancelled", self.start, self.stop)
        self.sync(self.organizer)
        self.assertTrue(self.events_named("Cancelled"))
        self.server.delete(self.organizer, remote_id)
        self.sync(self.organizer)
        self.assertFalse(self.events_named("Cancelled"))

    def test_an_attendees_copy_is_the_organizers_event(self):
        """The attendee's calendar holds the organizer's item: reading it links
        the attendee's calendar to the same event, under the id it has there,
        and leaves the organizer's link as it was."""
        remote_id = self.server.add(
            self.organizer, "Shared", self.start, self.stop, [self.attendee]
        )
        self.sync(self.organizer)
        self.sync(self.attendee)
        event = self.events_named("Shared")
        self.assertEqual(len(event), 1)
        self.assertEqual(self.link(event, self.organizer).remote_id, remote_id)
        self.assertEqual(
            self.link(event, self.attendee).remote_id,
            self.server.copy_id(self.attendee, remote_id),
        )

    def test_an_attendee_removing_the_item_declines_it(self):
        """Removing an invitation from one's own calendar declines it: the
        organizer's event stays."""
        remote_id = self.server.add(
            self.organizer, "Declined", self.start, self.stop, [self.attendee]
        )
        self.sync(self.organizer)
        self.sync(self.attendee)
        self.server.delete(self.attendee, self.server.copy_id(self.attendee, remote_id))
        self.sync(self.attendee)
        event = self.events_named("Declined")
        self.assertEqual(len(event), 1)
        self.assertEqual(
            event.attendee_ids.filtered(
                lambda attendee: attendee.partner_id == self.attendee.partner_id
            ).state,
            "declined",
        )

    def test_a_stale_token_reads_the_whole_calendar(self):
        self.sync(self.organizer)
        self.server.add(self.organizer, "Missed", self.start, self.stop)
        self.server.expire_token(self.organizer)
        self.sync(self.organizer)
        self.assertEqual(len(self.events_named("Missed")), 1)

    # -- sent to the provider --------------------------------------------------

    def test_an_odoo_event_is_inserted_once_in_its_organizers_calendar(self):
        event = self.event(name="From Odoo")
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        self.assertTrue(remote_id)
        self.assertEqual(
            self.server.items(self.organizer)[remote_id]["name"], "From Odoo"
        )
        self.assertEqual(self.ops_of(self.organizer), [("insert", remote_id)])

        self.sync(self.organizer)
        self.sync(self.attendee)
        self.assertEqual(len(self.events_named("From Odoo")), 1)
        self.assertEqual(len(self.ops_of(self.organizer)), 1)
        self.assertFalse(self.ops_of(self.attendee))

    def test_an_edit_reaches_the_organizers_item(self):
        event = self.event()
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        event.with_user(self.organizer).name = "Renamed in Odoo"
        self.push()
        self.assertEqual(
            self.server.items(self.organizer)[remote_id]["name"], "Renamed in Odoo"
        )
        self.assertEqual(self.ops_of(self.organizer)[-1], ("patch", remote_id))

    def test_an_attendees_edit_goes_out_through_the_organizer(self):
        event = self.event()
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        event.with_user(self.attendee).name = "Renamed by the attendee"
        self.push()
        self.assertEqual(
            self.server.items(self.organizer)[remote_id]["name"],
            "Renamed by the attendee",
        )
        self.assertFalse(self.ops_of(self.attendee))

    def test_a_deleted_event_is_deleted_from_the_provider(self):
        event = self.event()
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        event.with_user(self.organizer).unlink()
        self.push()
        self.assertNotIn(remote_id, self.server.items(self.organizer))

    def test_an_archived_event_is_deleted_from_the_provider(self):
        event = self.event()
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        event.with_user(self.organizer).action_archive()
        self.push()
        self.assertNotIn(remote_id, self.server.items(self.organizer))
        self.assertFalse(self.link(event, self.organizer))

    def test_an_event_of_an_organizer_who_does_not_synchronize_is_not_sent(self):
        self.event(organizer=self.outsider, name="Not ours to send")
        self.push()
        self.sync(self.attendee)
        self.assertEqual(self.server.ops, [])

    def test_an_answer_reaches_the_organizer(self):
        event = self.event()
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        event.attendee_ids.filtered(
            lambda attendee: attendee.partner_id == self.attendee.partner_id
        ).with_user(self.attendee).do_accept()
        self.push()
        self.assertEqual(
            self.server.items(self.organizer)[remote_id]["answers"][
                self.attendee.email
            ],
            "accepted",
        )

    def test_a_paused_provider_sends_nothing(self):
        self.env["calendar.sync.account"]._set_paused(self.code, True)
        self.event()
        self.push()
        self.assertEqual(self.server.ops, [])

    def test_an_edit_made_while_paused_is_sent_once_resumed(self):
        event = self.event()
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        self.env["calendar.sync.account"]._set_paused(self.code, True)
        event.with_user(self.organizer).name = "Renamed while paused"
        self.push()
        self.assertEqual(
            self.server.items(self.organizer)[remote_id]["name"], "Planning"
        )

        self.env["calendar.sync.account"]._set_paused(self.code, False)
        self.sync(self.organizer)
        self.assertEqual(
            self.server.items(self.organizer)[remote_id]["name"], "Renamed while paused"
        )

    def test_a_delete_owed_while_paused_is_made_once_resumed(self):
        event = self.event()
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        self.env["calendar.sync.account"]._set_paused(self.code, True)
        event.with_user(self.organizer).unlink()
        self.push()
        self.assertIn(remote_id, self.server.items(self.organizer))

        self.env["calendar.sync.account"]._set_paused(self.code, False)
        self.sync(self.organizer)
        self.assertNotIn(remote_id, self.server.items(self.organizer))

    def test_a_refused_edit_is_noted_once_and_sent_again_when_it_changes(self):
        event = self.event()
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        self.server.refusals["patch"] = 400
        event.with_user(self.organizer).name = "Refused"
        self.push()
        self.sync(self.organizer)
        self.assertEqual(
            self.server.items(self.organizer)[remote_id]["name"], "Planning"
        )
        self.assertTrue(self.link(event, self.organizer).error)

        event.with_user(self.organizer).name = "Accepted"
        self.push()
        self.assertEqual(
            self.server.items(self.organizer)[remote_id]["name"], "Accepted"
        )
        self.assertFalse(self.link(event, self.organizer).error)

    def test_a_reset_forgets_the_calendar_and_deletes_what_it_asks(self):
        """A reset leaves the user free to come back with another account: their
        calendar's links go, and the events they organize go from it when
        asked."""
        event = self.event(name="Before the reset")
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        self.env["wizard.calendar.sync.reset"].create(
            {
                "provider": self.code,
                "user_id": self.organizer.id,
                "delete_policy": "delete_remote",
                "sync_policy": "new",
            }
        ).reset_account()
        self.push()
        self.assertNotIn(remote_id, self.server.items(self.organizer))
        self.assertFalse(self.link(event, self.organizer))
        self.assertTrue(event.exists())
        self.assertGreaterEqual(
            self.organizer._calendar_sync_account(self.code).insert_since,
            event.create_date,
        )

    def test_a_refused_insert_is_noted_once(self):
        self.server.refusals["insert"] = 403
        event = self.event()
        self.push()
        self.sync(self.organizer)
        self.sync(self.organizer)
        self.assertFalse(self.server.items(self.organizer))
        self.assertTrue(self.link(event, self.organizer).error)
        self.assertEqual(
            len(
                event.message_ids.filtered(
                    lambda message: "refused this event" in (message.body or "")
                )
            ),
            1,
        )

    def test_an_insert_whose_answer_was_lost_lands_once(self):
        self.server.lost_answers = 1
        event = self.event(name="Sent twice")
        self.push()
        self.assertFalse(self.link(event, self.organizer).remote_id)
        self.sync(self.organizer)
        self.assertEqual(len(self.server.items(self.organizer)), 1)
        self.assertEqual(len(self.events_named("Sent twice")), 1)
        self.assertTrue(self.link(event, self.organizer).remote_id)

    def test_an_edit_made_after_a_lost_insert_answer_reaches_the_item(self):
        """The retried insert finds the item the first attempt left, which
        holds the values of then."""
        self.server.lost_answers = 1
        event = self.event(name="Lost")
        self.push()
        event.with_user(self.organizer).name = "Renamed after loss"
        self.push()
        self.sync(self.organizer)
        self.assertEqual(
            [item["name"] for item in self.server.items(self.organizer).values()],
            ["Renamed after loss"],
        )
        self.assertEqual(event.name, "Renamed after loss")

    def test_an_event_deleted_after_a_lost_insert_answer_stays_deleted(self):
        self.server.lost_answers = 1
        event = self.event(name="Lost then deleted")
        self.push()
        event.with_user(self.organizer).unlink()
        self.push()
        self.sync(self.organizer)
        self.sync(self.organizer)
        self.assertFalse(self.server.items(self.organizer))
        self.assertFalse(self.events_named("Lost then deleted"))

    def test_an_answer_given_while_paused_reaches_the_organizer_once_resumed(self):
        event = self.event(name="Answered while paused")
        self.push()
        self.sync(self.attendee)
        remote_id = self.link(event, self.organizer).remote_id
        self.env["calendar.sync.account"]._set_paused(self.code, True)
        event.attendee_ids.filtered(
            lambda attendee: attendee.partner_id == self.attendee.partner_id
        ).with_user(self.attendee).do_accept()
        self.push()
        self.env["calendar.sync.account"]._set_paused(self.code, False)
        self.sync(self.attendee)
        self.sync(self.organizer)
        self.assertEqual(
            self.server.items(self.organizer)[remote_id]["answers"][
                self.attendee.email
            ],
            "accepted",
        )

    def test_a_reset_deleting_the_items_declines_nothing_for_the_attendees(self):
        event = self.event(name="Reset with attendees")
        self.push()
        self.sync(self.attendee)
        self.env["wizard.calendar.sync.reset"].create(
            {
                "provider": self.code,
                "user_id": self.organizer.id,
                "delete_policy": "delete_remote",
                "sync_policy": "all",
            }
        ).reset_account()
        self.push()
        self.sync(self.attendee)
        self.assertNotEqual(
            event.attendee_ids.filtered(
                lambda attendee: attendee.partner_id == self.attendee.partner_id
            ).state,
            "declined",
        )

    def test_an_edit_owed_after_a_patch_is_not_overwritten_by_the_patch(self):
        """The version a patch answers is Odoo's own: reading it back must not
        overwrite an edit Odoo still owes."""
        event = self.event(name="V0")
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        event.with_user(self.organizer).name = "V1"
        self.push()
        self.env["calendar.sync.account"]._set_paused(self.code, True)
        event.with_user(self.organizer).name = "V2"
        self.push()
        self.env["calendar.sync.account"]._set_paused(self.code, False)
        self.sync(self.organizer)
        self.assertEqual(event.name, "V2")
        self.assertEqual(self.server.items(self.organizer)[remote_id]["name"], "V2")

    def _owe_an_edit_while_the_organizer_renames(self, provider_change_at):
        """Odoo owes the edit "Odoo's" while the organizer renames the item
        in the provider "Theirs", at `provider_change_at` relative to Odoo's
        edit; then the synchronization resumes."""
        event = self.event(name="Before")
        self.push()
        remote_id = self.link(event, self.organizer).remote_id
        self.env["calendar.sync.account"]._set_paused(self.code, True)
        event.with_user(self.organizer).name = "Odoo's"
        self.push()
        self.env.flush_all()
        self.server.clock = event.write_date + provider_change_at
        self.server.rename(self.organizer, remote_id, "Theirs")
        self.env["calendar.sync.account"]._set_paused(self.code, False)
        self.sync(self.organizer)
        return event, remote_id

    def test_a_provider_change_older_than_an_edit_odoo_owes_loses_to_it(self):
        event, remote_id = self._owe_an_edit_while_the_organizer_renames(
            timedelta(hours=-1)
        )
        self.assertEqual(event.name, "Odoo's")
        self.assertEqual(self.server.items(self.organizer)[remote_id]["name"], "Odoo's")

    def test_a_provider_change_newer_than_an_edit_odoo_owes_wins(self):
        event, remote_id = self._owe_an_edit_while_the_organizer_renames(
            timedelta(hours=1)
        )
        self.assertEqual(event.name, "Theirs")
        self.assertEqual(self.server.items(self.organizer)[remote_id]["name"], "Theirs")

    def test_an_attendees_read_keeps_the_other_attendees_answers(self):
        """An attendee's copy may hide the others' answers (Outlook's does):
        reading it must not reset them."""
        event = self.event(
            partner_ids=[
                (6, 0, (self.organizer | self.attendee | self.outsider).partner_id.ids)
            ]
        )
        self.push()
        event.attendee_ids.filtered(
            lambda attendee: attendee.partner_id == self.outsider.partner_id
        ).with_user(self.outsider).do_accept()
        self.push()
        self.sync(self.attendee)
        self.assertEqual(
            event.attendee_ids.filtered(
                lambda attendee: attendee.partner_id == self.outsider.partner_id
            ).state,
            "accepted",
        )
