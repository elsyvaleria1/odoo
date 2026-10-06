from odoo import fields
from odoo.fields import Domain
from odoo.tests.common import freeze_time, new_test_user

from odoo.addons.mail.tests.common import MailCommon


@freeze_time("2024-05-20 10:00:00")
class TestDiscussMeetings(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.host = new_test_user(cls.env, "test_meeting_host", tz="UTC")
        cls.env = cls.env(user=cls.host)

    def _start_meeting(self, name):
        # create_date comes from the database clock, which freeze_time does not reach
        with self.mock_datetime_and_now(fields.Datetime.now()):
            return self.env["discuss.channel"]._create_group(
                self.host.partner_id.ids,
                default_display_mode="video_full_screen",
                name=name,
            )

    def _search(self, channels, domain):
        return self.env["discuss.channel"].search(
            Domain("id", "in", channels.ids) & domain
        )

    def test_a_meeting_takes_place_when_it_is_started(self):
        meeting = self._start_meeting("Ad-hoc Call")
        self.assertEqual(meeting.meeting_start_dt, meeting.create_date)
        self.assertEqual(meeting.meeting_stop_dt, meeting.create_date)
        group = self.env["discuss.channel"]._create_group(
            self.host.partner_id.ids, name="Not a meeting"
        )
        self.assertFalse(group.meeting_start_dt)
        self.assertFalse(group.meeting_stop_dt)

    def test_a_meeting_lasts_as_long_as_its_call(self):
        meeting = self._start_meeting("Ad-hoc Call")
        meeting.self_member_id.sudo()._rtc_join_call()
        self.assertEqual(meeting.meeting_stop_dt, meeting.create_date)
        self.assertFalse(meeting.is_meeting_over)
        with freeze_time("2024-05-20 10:30:00"):
            meeting.self_member_id.sudo()._rtc_leave_call()
        meeting.invalidate_recordset(["meeting_stop_dt", "is_meeting_over"])
        self.assertEqual(
            meeting.meeting_stop_dt,
            fields.Datetime.from_string("2024-05-20 10:30:00"),
        )
        self.assertTrue(meeting.is_meeting_over)

    def test_a_thread_takes_place_with_its_meeting(self):
        meeting = self._start_meeting("Ad-hoc Call")
        thread = meeting._create_sub_channel(name="Notes")
        self.assertEqual(thread.meeting_start_dt, meeting.create_date)
        self.assertEqual(
            self._search(thread, self.env["discuss.channel"]._get_meeting_domain()),
            thread,
        )

    def test_today_only_matches_the_meetings_started_today(self):
        today = self._start_meeting("Ad-hoc Call")
        with freeze_time("2024-05-19 10:00:00"):
            yesterday = self._start_meeting("Yesterday Call")
        group = self.env["discuss.channel"]._create_group(
            self.host.partner_id.ids, name="Not a meeting"
        )
        self.assertEqual(
            self._search(
                today + yesterday + group,
                self.env["discuss.channel"]._get_meeting_today_domain(),
            ),
            today,
        )

    def test_a_meeting_is_over_once_its_call_ended(self):
        calling = self._start_meeting("Ad-hoc Call")
        idle = self._start_meeting("Ended Call")
        # the call history is written by the RTC machinery, never by the user
        self.env["discuss.call.history"].sudo().create(
            [
                {"channel_id": calling.id, "start_dt": fields.Datetime.now()},
                {
                    "channel_id": idle.id,
                    "start_dt": fields.Datetime.now(),
                    "end_dt": fields.Datetime.now(),
                },
            ]
        )
        channels = calling + idle
        self.assertEqual(
            self._search(channels, Domain("is_meeting_over", "=", True)), idle
        )
        self.assertEqual(
            self._search(channels, Domain("is_meeting_over", "=", False)), calling
        )
        self.assertEqual(
            self.env["discuss.channel"]
            .search(Domain("id", "in", channels.ids), order="is_meeting_over, id DESC")
            .ids,
            [calling.id, idle.id],
            "the meeting still going on comes first",
        )
