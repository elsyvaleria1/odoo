from datetime import date

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from .common import ResourceCase
from odoo.addons.base.models.resource_utils import week_type_of


@tagged("post_install", "-at_install")
class TestResourceCalendarAttendance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Attendance Calendar", "tz": "UTC"}
        )

    def _attendance(self, hour_from, hour_to, day_period="morning", dayofweek="5"):
        return self.env["resource.calendar.attendance"].create(
            {
                "name": "Slot",
                "calendar_id": self.calendar.id,
                "dayofweek": dayofweek,
                "hour_from": hour_from,
                "hour_to": hour_to,
                "day_period": day_period,
            }
        )

    def test_duration_hours_is_span(self):
        self.assertEqual(self._attendance(8.0, 12.0).duration_hours, 4.0)
        self.assertEqual(
            self._attendance(12.0, 13.0, day_period="lunch").duration_hours, 0.0
        )

    def test_onchange_hours_clamps_bounds(self):
        attendance = self.env["resource.calendar.attendance"].new(
            {
                "calendar_id": self.calendar.id,
                "dayofweek": "0",
                "hour_from": 25.0,
                "hour_to": -1.0,
                "day_period": "morning",
            }
        )
        attendance._onchange_hours()
        self.assertEqual(attendance.hour_from, 23.99)
        self.assertEqual(attendance.hour_to, attendance.hour_from)

    def test_duration_days_by_period(self):
        self.assertEqual(
            self._attendance(12.0, 13.0, day_period="lunch").duration_days, 0
        )
        self.assertEqual(
            self._attendance(
                8.0, 18.0, day_period="full_day", dayofweek="6"
            ).duration_days,
            1,
        )

    def test_week_type_parity(self):
        first = week_type_of(date(2024, 1, 1))
        next_week = week_type_of(date(2024, 1, 8))
        self.assertIn(first, ("0", "1"), "the selection key of week_type")
        self.assertNotEqual(first, next_week)

    def test_hours_stay_within_the_day_and_in_order(self):
        for hour_from, hour_to in ((25.0, 26.0), (-1.0, 8.0), (8.0, 24.5), (14.0, 8.0)):
            with (
                self.subTest(hour_from=hour_from, hour_to=hour_to),
                self.assertRaises(ValidationError),
            ):
                self._attendance(hour_from, hour_to)
        self.assertEqual(
            self._attendance(0.0, 24.0, dayofweek="6").duration_hours, 24.0
        )


@tagged("post_install", "-at_install")
class TestDurationBasedAverageHours(TransactionCase):
    def test_duration_based_average_hours(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "Duration based Calendar",
                "attendance_ids": False,
                "duration_based": True,
            }
        )
        for dow, name in (("0", "Mon"), ("1", "Tue"), ("2", "Wed")):
            self.env["resource.calendar.attendance"].create(
                {
                    "name": name,
                    "calendar_id": calendar.id,
                    "dayofweek": dow,
                    "day_period": "full_day",
                    "duration_hours": 4.0,
                }
            )
        self.assertEqual(calendar.hours_per_week, 12)
        self.assertEqual(calendar.hours_per_day, 4)

    def test_non_duration_based_uses_hour_bounds(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "Hour based Calendar", "attendance_ids": False}
        )
        for dow, name in (("0", "Mon"), ("1", "Tue"), ("2", "Wed")):
            self.env["resource.calendar.attendance"].create(
                {
                    "name": name,
                    "calendar_id": calendar.id,
                    "dayofweek": dow,
                    "day_period": "full_day",
                    "hour_from": 8,
                    "hour_to": 16,
                }
            )
        self.assertEqual(calendar.hours_per_week, 24)
        self.assertEqual(calendar.hours_per_day, 8)


@tagged("post_install", "-at_install")
class TestFullDayMidpointSplit(TransactionCase):
    def test_full_day_split_uses_midpoint(self):
        from datetime import date

        calendar = self.env["resource.calendar"].create(
            {"name": "Late shift", "tz": "UTC", "attendance_ids": False}
        )
        self.env["resource.calendar.attendance"].create(
            {
                "name": "Mon",
                "calendar_id": calendar.id,
                "dayofweek": "0",
                "day_period": "full_day",
                "hour_from": 10,
                "hour_to": 18,
            }
        )
        monday = date(2025, 1, 6)
        self.assertEqual(
            calendar._get_hours_for_date(monday, day_period="morning"),
            (10.0, 14.0),
        )
        self.assertEqual(
            calendar._get_hours_for_date(monday, day_period="afternoon"),
            (14.0, 18.0),
        )


@tagged("post_install", "-at_install")
class TestDurationHoursClearedBounds(TransactionCase):
    def test_duration_zeroed_when_hours_cleared(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "Clear Cal", "tz": "UTC"}
        )
        attendance = calendar.attendance_ids.filtered(
            lambda a: a.day_period == "morning"
        )[0]
        self.assertGreater(attendance.duration_hours, 0)
        attendance.write({"hour_from": 0.0, "hour_to": 0.0})
        self.assertEqual(
            attendance.duration_hours,
            0.0,
            "clearing the bounds must not leave a stale duration",
        )


@tagged("post_install", "-at_install")
class TestDurationHoursRecompute(TransactionCase):
    def test_duration_hours_recomputed_on_day_period_change(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "Recompute calendar", "attendance_ids": False}
        )
        attendance = self.env["resource.calendar.attendance"].create(
            {
                "name": "Lunch then work",
                "calendar_id": calendar.id,
                "dayofweek": "0",
                "day_period": "lunch",
                "hour_from": 8,
                "hour_to": 16,
            }
        )
        self.assertEqual(attendance.duration_hours, 0)
        attendance.day_period = "full_day"
        self.assertEqual(attendance.duration_hours, 8)


@tagged("post_install", "-at_install")
class TestDurationDaysDepends(TransactionCase):
    def test_duration_days_recomputes_on_hours_change(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "Duration-days depends", "tz": "UTC"}
        )
        attendance = self.env["resource.calendar.attendance"].create(
            {
                "name": "Sat AM",
                "calendar_id": calendar.id,
                "dayofweek": "5",
                "hour_from": 8,
                "hour_to": 10,
                "day_period": "morning",
            }
        )
        self.assertEqual(attendance.duration_days, 0.5)

        attendance.hour_to = 18

        self.assertEqual(
            attendance.duration_days,
            1.0,
            "duration_days must follow duration_hours, not stay stale.",
        )

    def test_duration_days_recomputes_on_calendar_hours_change(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "hours-per-day leg",
                "tz": "UTC",
                "attendance_ids": [
                    Command.create(
                        {
                            "name": "Mon AM",
                            "dayofweek": "0",
                            "hour_from": 8,
                            "hour_to": 14,
                            "day_period": "morning",
                        }
                    ),
                    Command.create(
                        {
                            "name": "Mon PM",
                            "dayofweek": "0",
                            "hour_from": 14,
                            "hour_to": 16,
                            "day_period": "afternoon",
                        }
                    ),
                ],
            }
        )
        target = calendar.attendance_ids.filtered(lambda a: a.name == "Mon AM")
        filler = calendar.attendance_ids.filtered(lambda a: a.name == "Mon PM")
        self.assertEqual(calendar.hours_per_day, 8)
        self.assertEqual(target.duration_days, 0.5)

        filler.hour_to = 15

        self.assertEqual(calendar.hours_per_day, 7)
        self.assertEqual(
            target.duration_days,
            1.0,
            "duration_days must follow calendar_id.hours_per_day, not only its own hours.",
        )


@tagged("post_install", "-at_install")
class TestTwoWeeksWeekType(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Two weeks", "tz": "UTC"}
        )
        cls.calendar.action_switch_two_weeks()

    def test_week_type_is_required_on_a_two_weeks_calendar(self):
        with self.assertRaises(ValidationError):
            self.env["resource.calendar.attendance"].create(
                {
                    "calendar_id": self.calendar.id,
                    "name": "orphan",
                    "dayofweek": "2",
                    "hour_from": 9,
                    "hour_to": 17,
                    "day_period": "morning",
                    "week_type": False,
                }
            )

    def test_clearing_week_type_is_rejected(self):
        line = self.calendar.attendance_ids.filtered(lambda a: not a.display_type)[0]
        with self.assertRaises(ValidationError):
            line.week_type = False

    def test_sections_may_keep_their_own_week_type(self):
        sections = self.calendar.attendance_ids.filtered(
            lambda a: a.display_type == "line_section"
        )
        self.assertEqual(len(sections), 2)
        self.assertEqual({s.week_type for s in sections}, {"0", "1"})

    def test_single_week_calendar_still_allows_unset_week_type(self):
        plain = self.env["resource.calendar"].create({"name": "Plain", "tz": "UTC"})
        self.assertTrue(
            self.env["resource.calendar.attendance"].create(
                {
                    "calendar_id": plain.id,
                    "name": "normal",
                    "dayofweek": "5",
                    "hour_from": 9,
                    "hour_to": 17,
                    "day_period": "morning",
                }
            )
        )


@tagged("post_install", "-at_install")
class TestAttendanceDependsCompleteness(TransactionCase):
    def test_display_name_follows_display_type(self):
        attendance = self.env["resource.calendar.attendance"].search([], limit=1)
        self.assertTrue(attendance, "need a calendar attendance to probe")
        self.assertDependsComplete(
            attendance,
            computed_fields=["display_name"],
            probe_fields=["display_type", "name"],
        )


class TestAttendanceOverlap(ResourceCase):
    def test_single_zero_length_attendance_is_not_an_overlap(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "zero",
                "company_id": self.company.id,
                "tz": "UTC",
                "attendance_ids": [Command.clear()],
            }
        )
        calendar.attendance_ids = [
            Command.create(
                {
                    "name": "zero length",
                    "dayofweek": "0",
                    "hour_from": 9.0,
                    "hour_to": 9.0,
                    "day_period": "morning",
                }
            )
        ]
        calendar.flush_recordset()
        self.assertEqual(len(calendar.attendance_ids), 1)

    def test_duration_based_zero_day_does_not_brick_the_calendar(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "duration", "company_id": self.company.id, "tz": "UTC"}
        )
        calendar.action_switch_duration_based()
        calendar.flush_recordset()

        attendance = calendar.attendance_ids.filtered(lambda a: not a.display_type)[0]
        attendance.duration_hours = 0.0
        calendar.flush_recordset()
        self.assertEqual(attendance.hour_from, attendance.hour_to)

        calendar.attendance_ids = [
            Command.create(
                {
                    "name": "Saturday",
                    "dayofweek": "5",
                    "hour_from": 9.0,
                    "hour_to": 11.0,
                    "day_period": "morning",
                }
            )
        ]
        calendar.flush_recordset()

    def test_real_overlap_is_still_rejected(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "overlapping",
                "company_id": self.company.id,
                "tz": "UTC",
                "attendance_ids": [Command.clear()],
            }
        )
        with self.assertRaises(ValidationError):
            calendar.attendance_ids = [
                Command.create(
                    {
                        "name": "a",
                        "dayofweek": "0",
                        "hour_from": 8.0,
                        "hour_to": 12.0,
                        "day_period": "morning",
                    }
                ),
                Command.create(
                    {
                        "name": "b",
                        "dayofweek": "0",
                        "hour_from": 11.0,
                        "hour_to": 15.0,
                        "day_period": "afternoon",
                    }
                ),
            ]
            calendar.flush_recordset()

    def test_section_without_week_type_is_rejected(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "2w", "company_id": self.company.id, "tz": "UTC"}
        )
        calendar.action_switch_two_weeks()
        calendar.flush_recordset()
        with self.assertRaises(ValidationError):
            self.env["resource.calendar.attendance"].create(
                {
                    "name": "Orphan section",
                    "calendar_id": calendar.id,
                    "dayofweek": "0",
                    "hour_from": 0,
                    "hour_to": 0,
                    "day_period": "morning",
                    "display_type": "line_section",
                }
            )

    def test_legacy_section_without_week_type_still_reads(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "2w legacy", "company_id": self.company.id, "tz": "UTC"}
        )
        calendar.action_switch_two_weeks()
        calendar.flush_recordset()
        section = calendar.attendance_ids.filtered(
            lambda a: a.display_type == "line_section"
        )[0]
        self.env.cr.execute(
            "UPDATE resource_calendar_attendance SET week_type = NULL WHERE id = %s",
            (section.id,),
        )
        section.invalidate_recordset()
        self.assertTrue(section.display_name)
