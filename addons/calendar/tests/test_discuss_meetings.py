from datetime import datetime, timedelta

from odoo import Command, fields
from odoo.fields import Domain
from odoo.tests import Form
from odoo.tests.common import HttpCase, freeze_time, new_test_user

from odoo.addons.mail.tests.common import MailCommon


@freeze_time("2024-05-20 10:00:00")
class TestDiscussMeetings(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.organizer = new_test_user(
            cls.env, "test_meeting_organizer", groups="base.group_user", tz="UTC"
        )
        cls.attendee = new_test_user(
            cls.env, "test_meeting_attendee", groups="base.group_user", tz="UTC"
        )
        cls.editor = new_test_user(
            cls.env, "test_meeting_editor", groups="base.group_user", tz="UTC"
        )
        cls.env = cls.env(user=cls.organizer)

    def _create_meeting(self, name, start, with_videocall=True, **values):
        return self.env["calendar.event"].create(
            {
                "name": name,
                "partner_ids": [
                    Command.link(self.organizer.partner_id.id),
                    Command.link(self.attendee.partner_id.id),
                ],
                "start": start,
                "stop": start + timedelta(hours=1),
                "videocall_location": (
                    self.env["calendar.event"].get_discuss_videocall_location()
                    if with_videocall
                    else False
                ),
                **values,
            }
        )

    def _create_ad_hoc_meeting(self, name):
        with self.mock_datetime_and_now(fields.Datetime.now()):
            return self.env["discuss.channel"]._create_group(
                self.organizer.partner_id.ids,
                default_display_mode="video_full_screen",
                name=name,
            )

    def _create_recurring_meeting(self, name, start, **values):
        return self._create_meeting(
            name,
            start,
            recurrency=True,
            repeat_unit="week",
            repeat_interval=1,
            mon=True,
            repeat_type="count",
            repeat_number=3,
            event_tz="UTC",
            **values,
        )

    def _search(self, channels, domain):
        return self.env["discuss.channel"].search(
            Domain("id", "in", channels.ids) & domain
        )

    def test_filling_in_the_scheduling_form_creates_no_channel(self):
        channels = self.env["discuss.channel"].search([])
        link = self.env["calendar.event"].get_discuss_videocall_location()
        form = Form(
            self.env["calendar.event"].with_context(
                default_access_token=link.split("/")[-1],
                default_videocall_location=link,
                is_quick_create_form=True,
            ),
            view="calendar.view_calendar_event_form_quick_create",
        )
        form.allday = True
        self.assertEqual(
            self.env["discuss.channel"].search([]),
            channels,
            "the channel waits for the meeting to be saved",
        )

    def test_a_meeting_with_a_discuss_videocall_owns_a_pinned_channel(self):
        meeting = self._create_meeting("Product Demo", datetime(2024, 5, 20, 14, 0))
        channel = meeting.videocall_channel_id
        self.assertEqual(channel.name, "Product Demo")
        self.assertEqual(channel.channel_type, "group")
        self.assertEqual(channel.default_display_mode, "video_full_screen")
        self.assertEqual(
            channel.channel_member_ids.partner_id,
            self.organizer.partner_id + self.attendee.partner_id,
        )
        self.assertEqual(channel.description, meeting.display_time)
        self.assertTrue(
            all(channel.channel_member_ids.mapped("is_pinned")),
            "the meeting shows in the Meetings tab of every member",
        )

    def test_only_upcoming_meetings_with_a_discuss_videocall_get_a_channel(self):
        upcoming = self._create_meeting("Product Demo", datetime(2024, 5, 20, 14, 0))
        over = self._create_meeting("Retrospective", datetime(2024, 5, 19, 14, 0))
        no_videocall = self._create_meeting(
            "Coffee Break", datetime(2024, 5, 20, 16, 0), with_videocall=False
        )
        other_videocall = self._create_meeting(
            "Google Meet Call",
            datetime(2024, 5, 20, 17, 0),
            with_videocall=False,
            videocall_location="https://meet.google.com/odoo-test",
        )
        meetings = upcoming + over + no_videocall + other_videocall
        self.assertEqual(meetings.filtered("videocall_channel_id"), upcoming)

    def test_adding_a_videocall_afterwards_creates_the_channel(self):
        meeting = self._create_meeting(
            "Product Demo", datetime(2024, 5, 20, 14, 0), with_videocall=False
        )
        meeting._set_discuss_videocall_location()
        self.assertEqual(meeting.videocall_channel_id.name, "Product Demo")

    def test_editing_a_meeting_keeps_its_channel_in_line(self):
        meeting = self._create_meeting("Product Demo", datetime(2024, 5, 20, 14, 0))
        channel = meeting.videocall_channel_id
        meeting.write(
            {"name": "Product Demo v2", "start": datetime(2024, 5, 21, 14, 0)}
        )
        self.assertEqual(meeting.videocall_channel_id, channel)
        self.assertEqual(channel.name, "Product Demo v2")
        self.assertEqual(channel.description, meeting.display_time)

    def test_an_edit_that_leaves_the_channel_alone_reads_no_meeting_back(self):
        meeting = self._create_meeting("Product Demo", datetime(2024, 5, 20, 14, 0))
        meeting.write({"description": "Agenda"})
        self.env.flush_all()

        with self.assertQueryCount(5):
            meeting.write({"description": "Agenda, revised"})

    def test_an_editor_outside_the_channel_keeps_it_in_line(self):
        meeting = self._create_meeting("Product Demo", datetime(2024, 5, 20, 14, 0))
        channel = meeting.videocall_channel_id
        meeting.with_user(self.editor).name = "Renamed by a colleague"
        self.assertNotIn(self.editor.partner_id, channel.channel_member_ids.partner_id)
        self.assertEqual(channel.name, "Renamed by a colleague")

    def test_deleting_a_meeting_retires_its_channel(self):
        deleted = self._create_meeting("Product Demo", datetime(2024, 5, 20, 14, 0))
        kept = self._create_meeting("Weekly Sync", datetime(2024, 5, 20, 15, 0))
        channels = deleted.videocall_channel_id + kept.videocall_channel_id
        deleted.unlink()
        self.assertEqual(channels.exists(), kept.videocall_channel_id)

    def test_deleting_a_meeting_with_messages_keeps_its_channel_unpinned(self):
        deleted = self._create_meeting("Product Demo", datetime(2024, 5, 20, 14, 0))
        channel = deleted.videocall_channel_id
        channel.message_post(body="Let's review the demo", message_type="comment")
        with freeze_time("2024-05-21 10:00:00"):
            deleted.unlink()
        self.assertTrue(channel.exists(), "its chat history is kept")
        self.assertFalse(channel.calendar_event_ids)
        self.assertFalse(
            any(channel.channel_member_ids.mapped("is_pinned")),
            "it drops out of the Meetings tab of everyone",
        )

    def test_a_recurrence_retires_its_channel_with_its_last_meeting(self):
        meeting = self._create_recurring_meeting(
            "Weekly Sync", datetime(2024, 5, 20, 14, 0)
        )
        occurrences = meeting.recurrence_id.calendar_event_ids
        self.assertEqual(len(occurrences), 3)
        channel = occurrences.videocall_channel_id
        self.assertEqual(len(channel), 1, "the occurrences share one video call")
        occurrences[0].unlink()
        self.assertTrue(channel.exists())
        occurrences.exists().unlink()
        self.assertFalse(channel.exists())

    def test_today_matches_the_meetings_taking_place_today(self):
        today = self._create_meeting("Product Demo", datetime(2024, 5, 20, 14, 0))
        spanning = self._create_meeting("Team Building", datetime(2024, 5, 19, 9, 0))
        spanning.stop = datetime(2024, 5, 21, 18, 0)
        tomorrow = self._create_meeting("Weekly Sync", datetime(2024, 5, 21, 14, 0))
        ad_hoc = self._create_ad_hoc_meeting("Ad-hoc Call")
        with freeze_time("2024-05-19 10:00:00"):
            yesterday = self._create_ad_hoc_meeting("Yesterday Call")
        channels = (
            (today + spanning + tomorrow).videocall_channel_id + ad_hoc + yesterday
        )
        self.assertEqual(
            self._search(
                channels, self.env["discuss.channel"]._get_meeting_today_domain()
            ),
            (today + spanning).videocall_channel_id + ad_hoc,
        )

    @freeze_time("2024-05-20 23:00:00")
    def test_today_follows_the_timezone_of_the_user(self):
        today_for_them = self._create_meeting(
            "Product Demo", datetime(2024, 5, 21, 10, 0)
        )
        tomorrow_for_them = self._create_meeting(
            "Weekly Sync", datetime(2024, 5, 21, 23, 0)
        )
        started_for_them = self._create_ad_hoc_meeting("Ad-hoc Call")
        with freeze_time("2024-05-20 20:00:00"):
            started_yesterday_for_them = self._create_ad_hoc_meeting("Earlier Call")
        channels = (
            (today_for_them + tomorrow_for_them).videocall_channel_id
            + started_for_them
            + started_yesterday_for_them
        )
        brussels = self.env["discuss.channel"].with_context(tz="Europe/Brussels")
        self.assertEqual(
            brussels.search(
                Domain("id", "in", channels.ids) & brussels._get_meeting_today_domain()
            ),
            today_for_them.videocall_channel_id + started_for_them,
        )

    def test_a_meeting_still_to_come_is_not_over(self):
        over = self._create_meeting("Retrospective", datetime(2024, 5, 20, 8, 0))
        with freeze_time("2024-05-20 08:30:00"):
            over._set_discuss_videocall_location()
        going_on = self._create_meeting("Product Demo", datetime(2024, 5, 20, 9, 30))
        to_come = self._create_meeting("Weekly Sync", datetime(2024, 5, 21, 14, 0))
        channels = (over + going_on + to_come).videocall_channel_id
        self.assertEqual(len(channels), 3)
        self.assertEqual(
            self._search(channels, Domain("is_meeting_over", "=", False)),
            (going_on + to_come).videocall_channel_id,
        )
        thread = to_come.videocall_channel_id._create_sub_channel(name="Agenda")
        self.assertFalse(thread.is_meeting_over, "a thread follows its meeting")

    def test_a_recurrence_takes_place_with_its_ongoing_or_next_meeting(self):
        meeting = self._create_recurring_meeting(
            "Weekly Sync", datetime(2024, 5, 20, 14, 0)
        )
        first, second, third = meeting.recurrence_id.calendar_event_ids.sorted("start")
        channel = meeting.videocall_channel_id
        self.assertEqual(
            (channel.meeting_start_dt, channel.meeting_stop_dt),
            (first.start, first.stop),
        )
        with freeze_time("2024-05-20 14:30:00"):
            channel.invalidate_recordset()
            self.assertEqual(channel.meeting_start_dt, first.start)
        with freeze_time("2024-05-20 16:00:00"):
            channel.invalidate_recordset()
            self.assertEqual(channel.meeting_start_dt, second.start)
        with freeze_time("2024-06-20 10:00:00"):
            channel.invalidate_recordset()
            self.assertEqual(channel.meeting_start_dt, third.start)

    def test_a_thread_takes_place_with_its_meeting(self):
        meeting = self._create_meeting("Product Demo", datetime(2024, 5, 20, 14, 0))
        thread = meeting.videocall_channel_id._create_sub_channel(name="Follow-up")
        self.assertEqual(thread.meeting_start_dt, meeting.start)
        self.assertEqual(thread.meeting_stop_dt, meeting.stop)


@freeze_time("2024-05-20 10:00:00")
class TestDiscussMeetingsGuest(HttpCase):
    def test_today_is_served_to_a_guest_who_cannot_read_the_meeting(self):
        organizer = new_test_user(
            self.env, "test_meeting_organizer", groups="base.group_user", tz="UTC"
        )
        meeting = (
            self.env["calendar.event"]
            .with_user(organizer)
            .create(
                {
                    "name": "Product Demo",
                    "partner_ids": [Command.link(organizer.partner_id.id)],
                    "start": datetime(2024, 5, 20, 14, 0),
                    "stop": datetime(2024, 5, 20, 15, 0),
                    "videocall_location": self.env[
                        "calendar.event"
                    ].get_discuss_videocall_location(),
                }
            )
        )
        guest = self.env["mail.guest"].create({"name": "Guest"})
        meeting.videocall_channel_id._add_members(guests=guest)
        self.authenticate(None, None)
        self.opener.cookies[guest._cookie_name] = guest._format_auth_cookie()
        data = self.call_jsonrpc(
            "/mail/data",
            {
                "fetch_params": [
                    [
                        "/mail/messaging_menu/discuss.channel/load_more",
                        {
                            "tab_id": "meeting",
                            "filter_ids": ["meeting_today"],
                            "limit": 30,
                        },
                        "page",
                    ],
                ],
            },
        )
        self.assertIn(
            meeting.videocall_channel_id.id,
            [channel["id"] for channel in data.get("discuss.channel", [])],
        )
