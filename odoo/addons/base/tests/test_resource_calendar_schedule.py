from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.libs.datetime import timezone
from odoo.libs.intervals import Intervals
from odoo.tests import TransactionCase, tagged

from odoo.addons.base.models.resource_utils import week_type_of


def _lines(hour_from, hour_to, days=range(5), **extra):
    return [Command.clear()] + [
        Command.create(
            {
                "name": f"Day {day}",
                "dayofweek": str(day),
                "hour_from": hour_from,
                "hour_to": hour_to,
                "day_period": "afternoon",
                **extra,
            }
        )
        for day in days
    ]


def _hours(intervals):
    return sum((stop - start).total_seconds() / 3600 for start, stop, _ in intervals)


class TestCalendarSchedule(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Calendar = cls.env["resource.calendar"]
        cls.Exception = cls.env["resource.schedule.exception"]
        cls.calendar = cls.Calendar.create({"name": "40h UTC", "tz": "UTC"})
        cls.monday = date(2026, 10, 5)
        cls.monday_start = datetime.combine(cls.monday, time.min, UTC)
        cls.tuesday_start = cls.monday_start + timedelta(days=1)

    def _resource(self, **vals):
        return self.env["resource.resource"].create(
            {"name": "Worker", "calendar_id": self.calendar.id, "tz": "UTC", **vals}
        )

    def test_whole_day_exception_covers_a_line_ending_at_midnight(self):
        night = self.Calendar.create(
            {"name": "Night", "tz": "UTC", "attendance_ids": _lines(16, 24)}
        )
        self.Exception.create(
            {
                "name": "Holiday",
                "calendar_id": night.id,
                "date_from": datetime.combine(self.monday, time.min),
            }
        )
        self.assertFalse(
            night._work_intervals_batch(self.monday_start, self.tuesday_start)[False]
        )
        unusual = night._get_unusual_days(self.monday_start, self.monday_start)
        self.assertTrue(unusual["2026-10-05"])
        self.assertEqual(
            night.plan_days(
                1, datetime.combine(self.monday, time.min), compute_leaves=True
            ),
            datetime.combine(self.monday + timedelta(days=2), time.min),
            "the day planned is Tuesday, whose line ends at its midnight",
        )

    def test_a_plan_beyond_the_horizon_reads_the_schedule_a_few_times(self):
        Calendar = self.env.registry["resource.calendar"]
        with patch.object(
            Calendar,
            "_work_intervals_batch",
            autospec=True,
            side_effect=Calendar._work_intervals_batch,
        ) as reads:
            found = self.calendar.plan_days(
                3000, datetime.combine(self.monday, time.min), compute_leaves=True
            )
        self.assertIsNone(found)
        self.assertLessEqual(
            reads.call_count, 8, "windows double: not one reading per fortnight"
        )

    def test_a_daylight_saving_night_holds_its_real_hours(self):
        brussels = self.Calendar.create(
            {
                "name": "Brussels nights",
                "tz": "Europe/Brussels",
                "attendance_ids": _lines(0, 6, days=range(7)),
            }
        )
        zone = timezone("Europe/Brussels")
        night = datetime(2026, 3, 29, tzinfo=zone)
        self.assertEqual(
            brussels.get_work_hours_count(night, night + timedelta(days=1)),
            5.0,
            "the clocks skip 02:00 to 03:00: six wall hours are five",
        )
        self.assertEqual(
            brussels.plan_hours(5.0, night.replace(tzinfo=None) - timedelta(hours=1)),
            datetime(2026, 3, 29, 4),
            "five planned hours from local midnight end at 06:00 local, 04:00 UTC",
        )

    def test_a_day_ends_at_the_next_midnight(self):
        clock = self.Calendar.create(
            {"name": "Round the clock", "tz": "UTC", "attendance_ids": _lines(0, 24)}
        )
        wednesday_start = self.monday_start + timedelta(days=2)
        intervals = clock._attendance_intervals_batch(
            self.monday_start, wednesday_start + timedelta(days=1)
        )[False]
        self.assertEqual(
            [(start, stop) for start, stop, _meta in intervals],
            [
                (self.monday_start, self.tuesday_start),
                (self.tuesday_start, wednesday_start),
                (wednesday_start, wednesday_start + timedelta(days=1)),
            ],
        )
        merged = Intervals(intervals)
        self.assertEqual(len(merged), 1, "touching days are one span of time")
        self.assertEqual(
            dict(clock._get_hours_by_day(merged)),
            {self.monday + timedelta(days=offset): 24.0 for offset in range(3)},
            "a span crossing midnights still counts day by day",
        )
        self.assertEqual(
            clock._get_duration_data(merged),
            {"days": 3.0, "hours": 72.0},
        )

    def test_a_whole_day_exception_reads_as_its_day_to_24_00(self):
        exception = self.Exception.create(
            {
                "name": "Holiday",
                "calendar_id": self.calendar.id,
                "date_from": datetime.combine(self.monday, time.min),
            }
        )
        self.assertEqual(
            exception.date_to,
            datetime.combine(self.monday + timedelta(days=1), time.min),
        )
        self.assertEqual(exception.local_date_to, self.monday)
        self.assertEqual(exception.local_hour_to, 24.0)
        exception.local_date_to = self.monday + timedelta(days=1)
        self.assertEqual(
            exception.date_to,
            datetime.combine(self.monday + timedelta(days=2), time.min),
        )

    def test_resource_absence_holds_through_any_schedule(self):
        resource = self._resource()
        other = self.Calendar.create({"name": "Other", "tz": "UTC"})
        self.Exception.create(
            {
                "name": "Sick",
                "resource_id": resource.id,
                "date_from": datetime(2026, 10, 5, 0, 0),
                "date_to": datetime(2026, 10, 6),
            }
        )
        for calendar in (self.calendar, other):
            intervals = calendar._work_intervals_batch(
                self.monday_start, self.tuesday_start, resource
            )[resource.id]
            self.assertFalse(intervals, calendar.name)

    def test_schedule_closure_stays_on_its_schedule(self):
        other = self.Calendar.create({"name": "Other", "tz": "UTC"})
        self.Exception.create(
            {
                "name": "Closed",
                "calendar_id": self.calendar.id,
                "date_from": datetime(2026, 10, 5, 0, 0),
                "date_to": datetime(2026, 10, 6),
            }
        )
        self.assertEqual(
            _hours(
                other._work_intervals_batch(self.monday_start, self.tuesday_start)[
                    False
                ]
            ),
            8.0,
        )

    def test_planning_reads_the_resource_zone_with_or_without_leaves(self):
        tokyo = self._resource(tz="Asia/Tokyo")
        start = datetime(2026, 10, 5, 0, 0)
        for compute_leaves in (False, True):
            self.assertEqual(
                self.calendar.plan_hours(
                    1, start, compute_leaves=compute_leaves, resource=tokyo
                ),
                datetime(2026, 10, 5, 1, 0),
                f"compute_leaves={compute_leaves}",
            )

    def test_single_week_calendar_ignores_week_tags(self):
        tagged = self.Calendar.create(
            {
                "name": "Tagged",
                "tz": "UTC",
                "attendance_ids": _lines(8, 12, week_type="0"),
            }
        )
        for monday in (self.monday, self.monday + timedelta(days=7)):
            self.assertTrue(tagged._is_working_day(monday), monday)
            self.assertEqual(tagged._get_hours_for_date(monday), (8.0, 12.0))

    def test_unusual_days_read_in_the_schedule_zone(self):
        evening = self.Calendar.create(
            {
                "name": "Evening",
                "tz": "America/Mexico_City",
                "attendance_ids": _lines(18, 22),
            }
        )
        friday = self.monday + timedelta(days=4)
        unusual = evening._get_unusual_days(
            datetime.combine(friday, time.min, UTC),
            datetime.combine(friday + timedelta(days=2), time.max, UTC),
        )
        self.assertEqual(
            unusual,
            {"2026-10-09": False, "2026-10-10": True, "2026-10-11": True},
        )

    def test_work_time_rate_search_accepts_mixed_numbers(self):
        half = self.Calendar.create(
            {"name": "Half", "tz": "UTC", "attendance_ids": _lines(8, 12)}
        )
        half.full_time_required_hours = 40
        found = self.Calendar.search(
            [
                ("work_time_rate", "in", [100, 50.0]),
                ("id", "in", (self.calendar | half).ids),
            ]
        )
        self.assertEqual(found, self.calendar | half)
        self.assertEqual(
            self.Calendar.search(
                [("work_time_rate", "<", 75), ("id", "in", (self.calendar | half).ids)]
            ),
            half,
        )

    def test_full_time_equivalent_survives_editing_the_schedule(self):
        part_time = self.Calendar.create({"name": "Part time", "tz": "UTC"})
        part_time.full_time_required_hours = 38
        part_time.attendance_ids[:1].hour_to = 11
        self.env.flush_all()
        self.assertEqual(part_time.full_time_required_hours, 38)

    def test_duration_based_schedule_has_no_breaks(self):
        calendar = self.Calendar.create({"name": "Breaks", "tz": "UTC"})
        with self.assertRaises(ValidationError):
            calendar.duration_based = True
        calendar.action_switch_duration_based()
        self.assertTrue(calendar.duration_based)
        self.assertFalse(
            calendar.attendance_ids.filtered(lambda line: line.day_period == "lunch")
        )


@tagged("post_install", "-at_install")
class TestCalendarWorkMethods(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Standard 40h", "tz": "UTC"}
        )

    def test_is_working_day_weekday(self):
        from datetime import date

        monday = date(2025, 1, 6)
        self.assertTrue(self.calendar._is_working_day(monday))

    def test_is_working_day_weekend(self):
        from datetime import date

        saturday = date(2025, 1, 11)
        self.assertFalse(self.calendar._is_working_day(saturday))

    def test_a_schedule_without_fixed_days_works_every_day(self):
        from datetime import date

        saturday = date(2025, 1, 11)
        for schedule_type in ("flexible", "fully_flexible"):
            calendar = self.env["resource.calendar"].create(
                {"name": schedule_type, "schedule_type": schedule_type}
            )
            with self.subTest(schedule_type=schedule_type):
                self.assertTrue(calendar._is_working_day(saturday))

    def test_get_hours_for_date_full_day(self):
        from datetime import date

        monday = date(2025, 1, 6)
        hour_from, hour_to = self.calendar._get_hours_for_date(monday)
        self.assertEqual(hour_from, 8.0)
        self.assertEqual(hour_to, 17.0)

    def test_get_hours_for_date_morning(self):
        from datetime import date

        monday = date(2025, 1, 6)
        hour_from, hour_to = self.calendar._get_hours_for_date(
            monday, day_period="morning"
        )
        self.assertEqual(hour_from, 8.0)
        self.assertEqual(hour_to, 12.0)

    def test_get_hours_for_date_afternoon(self):
        from datetime import date

        monday = date(2025, 1, 6)
        hour_from, hour_to = self.calendar._get_hours_for_date(
            monday, day_period="afternoon"
        )
        self.assertEqual(hour_from, 13.0)
        self.assertEqual(hour_to, 17.0)

    def test_a_fully_flexible_day_is_the_whole_day(self):
        from datetime import date

        calendar = self.env.ref("base.resource_calendar_fully_flexible")
        monday = date(2025, 1, 6)
        self.assertEqual(calendar._get_hours_for_date(monday), (0.0, 24.0))
        self.assertEqual(calendar._get_hours_for_date(monday, "morning"), (0.0, 12.0))
        self.assertEqual(
            calendar._get_hours_for_date(monday, "afternoon"), (12.0, 24.0)
        )

    def test_get_hours_for_date_no_target(self):
        with self.assertRaises(ValueError):
            self.calendar._get_hours_for_date(None)

    def test_switch_duration_based(self):
        calendar = self.calendar
        has_lunch = calendar.attendance_ids.filtered(lambda a: a.day_period == "lunch")
        self.assertTrue(has_lunch, "Standard calendar should have lunch periods")

        calendar.action_switch_duration_based()
        self.assertTrue(calendar.duration_based)
        no_lunch = calendar.attendance_ids.filtered(lambda a: a.day_period == "lunch")
        self.assertFalse(no_lunch, "Duration mode should remove lunch periods")

        calendar.action_switch_duration_based()
        self.assertFalse(calendar.duration_based)
        has_lunch_again = calendar.attendance_ids.filtered(
            lambda a: a.day_period == "lunch"
        )
        self.assertTrue(has_lunch_again, "Disabling duration mode restores lunch")


@tagged("post_install", "-at_install")
class TestDSTTransition(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Brussels Calendar", "tz": "Europe/Brussels"}
        )

    def test_work_hours_across_spring_forward(self):
        brussels = timezone("Europe/Brussels")
        start = datetime(2025, 3, 28, 6, 0).replace(tzinfo=brussels)
        end = datetime(2025, 3, 31, 20, 0).replace(tzinfo=brussels)
        hours = self.calendar.get_work_hours_count(start, end)
        self.assertEqual(hours, 16.0)

    def test_plan_hours_across_spring_forward(self):
        brussels = timezone("Europe/Brussels")
        start = datetime(2025, 3, 28, 8, 0).replace(tzinfo=brussels)
        result = self.calendar.plan_hours(16.0, start, compute_leaves=False)
        self.assertTrue(result, "plan_hours should find a result within range")
        if result.tzinfo:
            result_local = result.astimezone(brussels)
        else:
            result_local = result.replace(tzinfo=brussels)
        self.assertEqual(result_local.weekday(), 0, "Should land on Monday")


@tagged("post_install", "-at_install")
class TestWorksOnDateIgnoresNonWorkLines(TransactionCase):
    def test_two_week_calendar_section_rows_do_not_mark_monday(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "Sections Cal", "tz": "UTC"}
        )
        calendar.action_switch_two_weeks()
        calendar.attendance_ids.filtered(
            lambda a: not a.display_type and a.dayofweek != "1"
        ).unlink()

        monday_w0, monday_w1 = date(2025, 1, 6), date(2025, 1, 13)
        week_types = {week_type_of(d) for d in (monday_w0, monday_w1)}
        self.assertEqual(week_types, {"0", "1"}, "consecutive Mondays span both weeks")
        for monday in (monday_w0, monday_w1):
            self.assertFalse(
                calendar._is_working_day(monday),
                "section rows must not mark Monday as worked",
            )
            self.assertTrue(calendar._is_working_day(monday + timedelta(days=1)))

    def test_lunch_only_day_is_not_working(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "Lunch Cal", "tz": "UTC"}
        )
        calendar.attendance_ids.filtered(
            lambda a: a.dayofweek == "4" and a.day_period != "lunch"
        ).unlink()
        friday = date(2025, 1, 10)
        self.assertFalse(calendar._is_working_day(friday))
        self.assertTrue(calendar._is_working_day(date(2025, 1, 9)))


@tagged("post_install", "-at_install")
class TestPlanHoursWithResource(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Test Calendar", "tz": "UTC"}
        )
        cls.resource = cls.env["resource.resource"].create(
            {
                "name": "Worker",
                "calendar_id": cls.calendar.id,
                "tz": "UTC",
            }
        )

    def test_plan_hours_with_resource_leave(self):
        self.env["resource.schedule.exception"].create(
            {
                "name": "Sick day",
                "calendar_id": self.calendar.id,
                "resource_id": self.resource.id,
                "date_from": datetime(2025, 1, 7, 0, 0),
                "date_to": datetime(2025, 1, 7, 23, 59),
            }
        )
        start = datetime(2025, 1, 6, 8, 0).replace(tzinfo=UTC)
        result = self.calendar.plan_hours(
            16.0, start, compute_leaves=True, resource=self.resource
        )
        self.assertTrue(result)
        self.assertEqual(result.weekday(), 2)
        self.assertEqual(result.hour, 17)

    def test_plan_hours_negative(self):
        start = datetime(2025, 1, 8, 17, 0).replace(tzinfo=UTC)
        result = self.calendar.plan_hours(-8.0, start, compute_leaves=False)
        self.assertTrue(result)
        self.assertEqual(result.hour, 8)
        self.assertEqual(result.day, 8)

    def test_plan_hours_zero(self):
        start = datetime(2025, 1, 6, 10, 0).replace(tzinfo=UTC)
        self.assertEqual(
            self.calendar.plan_hours(0.0, start, compute_leaves=False), start
        )

    def test_plan_hours_zero_outside_working_time(self):
        saturday = datetime(2025, 1, 11, 10, 0).replace(tzinfo=UTC)
        monday_start = datetime(2025, 1, 13, 8, 0).replace(tzinfo=UTC)
        self.assertEqual(
            self.calendar.plan_hours(0.0, saturday, compute_leaves=False), monday_start
        )
        self.assertEqual(
            self.calendar.plan_hours(0.0002, saturday, compute_leaves=False).replace(
                microsecond=0
            ),
            monday_start,
        )


@tagged("post_install", "-at_install")
class TestListWorkTimePerDay(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Standard", "tz": "UTC"}
        )

    def test_get_unusual_days_fixed_calendar(self):
        start = datetime(2025, 1, 6, 0, 0).replace(tzinfo=UTC)
        end = datetime(2025, 1, 12, 23, 59).replace(tzinfo=UTC)
        result = self.calendar._get_unusual_days(start, end)
        self.assertTrue(result.get("2025-01-11", False), "Saturday should be unusual")
        self.assertTrue(result.get("2025-01-12", False), "Sunday should be unusual")
        self.assertFalse(result.get("2025-01-06", True), "Monday should be normal")

    def test_get_unusual_days_keeps_the_last_day_on_an_early_end_time(self):
        start = datetime(2025, 1, 6, 8, 0).replace(tzinfo=UTC)
        end = datetime(2025, 1, 8, 0, 0).replace(tzinfo=UTC)
        result = self.calendar._get_unusual_days(start, end)
        self.assertIn("2025-01-08", result)


class TestUnavailableIntervalsFlexible(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible",
                "schedule_type": "flexible",
                "hours_per_week": 40,
                "hours_per_day": 8,
                "tz": "UTC",
            }
        )
        cls.resource = cls.env["resource.resource"].create(
            {"name": "Flexible worker", "calendar_id": cls.calendar.id, "tz": "UTC"}
        )
        cls.start = datetime(2025, 3, 3).replace(tzinfo=UTC)
        cls.end = datetime(2025, 3, 8).replace(tzinfo=UTC)

    def test_batch_contains_resource_without_leaves(self):
        result = self.calendar._unavailable_intervals_batch(
            self.start, self.end, self.resource
        )
        self.assertIn(
            self.resource.id,
            result,
            "a flexible resource with no leaves must still be reported",
        )
        self.assertEqual(result[self.resource.id], [])

    def test_singular_helper_does_not_raise(self):
        self.assertEqual(
            self.calendar._unavailable_intervals(self.start, self.end, self.resource),
            [],
        )

    def test_resource_level_helper_reports_every_resource(self):
        self.assertIn(
            self.resource.id,
            self.resource._get_unavailable_intervals(self.start, self.end),
        )

    def test_leaves_are_still_reported(self):
        self.env["resource.schedule.exception"].create(
            {
                "name": "Day off",
                "calendar_id": self.calendar.id,
                "resource_id": self.resource.id,
                "date_from": datetime(2025, 3, 5),
                "date_to": datetime(2025, 3, 5, 23, 59),
            }
        )
        result = self.calendar._unavailable_intervals_batch(
            self.start, self.end, self.resource
        )
        self.assertTrue(result[self.resource.id])


class TestPlanDaysHonoursResource(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env.ref("base.resource_calendar_std")
        cls.resource = cls.env["resource.resource"].create(
            {"name": "Planned", "calendar_id": cls.calendar.id, "tz": "UTC"}
        )
        cls.env["resource.schedule.exception"].create(
            {
                "name": "Away all week",
                "calendar_id": cls.calendar.id,
                "resource_id": cls.resource.id,
                "date_from": datetime(2025, 4, 7),
                "date_to": datetime(2025, 4, 11, 23, 59),
            }
        )

    def test_resource_leave_pushes_the_plan_out(self):
        start = datetime(2025, 4, 7, 8).replace(tzinfo=UTC)
        without = self.calendar.plan_days(3, start, compute_leaves=True)
        with_resource = self.calendar.plan_days(
            3, start, compute_leaves=True, resource=self.resource
        )
        self.assertTrue(with_resource)
        self.assertGreater(
            with_resource,
            without,
            "the resource's own leave must delay the planned end",
        )
        self.assertGreaterEqual(
            with_resource.date(),
            datetime(2025, 4, 14).date(),
            "planning must skip the week the resource is on leave",
        )


@tagged("post_install", "-at_install")
class TestPlanDaysEndOfDay(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Audit 40h", "tz": "UTC"}
        )
        cls.monday = datetime(2025, 1, 6).replace(tzinfo=UTC)
        cls.friday_night = datetime(2025, 1, 10, 23, 59).replace(tzinfo=UTC)

    def test_plan_days_returns_end_of_day(self):
        for days, expected in (
            (1, datetime(2025, 1, 6, 17)),
            (2, datetime(2025, 1, 7, 17)),
            (5, datetime(2025, 1, 10, 17)),
        ):
            with self.subTest(days=days):
                self.assertEqual(
                    self.calendar.plan_days(days, self.monday),
                    expected.replace(tzinfo=UTC),
                )

    def test_plan_days_agrees_with_plan_hours(self):
        for days in (1, 2, 3, 5):
            with self.subTest(days=days):
                self.assertEqual(
                    self.calendar.plan_days(days, self.monday),
                    self.calendar.plan_hours(days * 8, self.monday),
                )

    def test_plan_days_backwards_returns_start_of_day(self):
        for days, expected in (
            (-1, datetime(2025, 1, 10, 8)),
            (-2, datetime(2025, 1, 9, 8)),
        ):
            with self.subTest(days=days):
                self.assertEqual(
                    self.calendar.plan_days(days, self.friday_night),
                    expected.replace(tzinfo=UTC),
                )

    def test_plan_days_edge_cases_preserved(self):
        self.assertEqual(self.calendar.plan_days(0, self.monday), self.monday)
        self.assertFalse(self.calendar.plan_days(3000, self.monday))
        self.assertFalse(self.calendar.plan_days(0.0002, self.monday))

    def test_plan_days_spans_multiple_scan_windows(self):
        self.assertEqual(
            self.calendar.plan_days(20, self.monday),
            self.calendar.plan_hours(20 * 8, self.monday),
        )


@tagged("post_install", "-at_install")
class TestCalendarlessIntervalApi(TransactionCase):
    def test_leave_intervals_on_empty_calendar_is_empty(self):
        start = datetime(2025, 1, 6).replace(tzinfo=UTC)
        end = datetime(2025, 1, 7).replace(tzinfo=UTC)
        self.assertEqual(
            len(
                self.env["resource.calendar"]
                .browse()
                ._leave_intervals_batch(start, end)[False]
            ),
            0,
        )

    def test_empty_calendar_does_not_sweep_other_calendars_leaves(self):
        calendar = self.env["resource.calendar"].create({"name": "Owner", "tz": "UTC"})
        self.env["resource.schedule.exception"].create(
            {
                "name": "owned leave",
                "calendar_id": calendar.id,
                "date_from": datetime(2025, 1, 6, 8),
                "date_to": datetime(2025, 1, 6, 17),
            }
        )
        start = datetime(2025, 1, 6).replace(tzinfo=UTC)
        end = datetime(2025, 1, 7).replace(tzinfo=UTC)
        got = self.env["resource.calendar"].browse()._leave_intervals_batch(start, end)
        self.assertFalse(list(got[False]))

    def test_attendance_intervals_on_empty_calendar_explains_itself(self):
        start = datetime(2025, 1, 6).replace(tzinfo=UTC)
        end = datetime(2025, 1, 7).replace(tzinfo=UTC)
        with self.assertRaises(ValueError) as caught:
            self.env["resource.calendar"].browse()._attendance_intervals_batch(
                start, end
            )
        self.assertIn("fully flexible", str(caught.exception))


@tagged("post_install", "-at_install")
class TestWorkingHoursFreshness(TransactionCase):
    SATURDAY = date(2025, 1, 11)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Freshness", "tz": "UTC"}
        )

    def test_is_working_day_reflects_added_attendance(self):
        self.assertFalse(self.calendar._is_working_day(self.SATURDAY))

        self.env["resource.calendar.attendance"].create(
            {
                "name": "Saturday shift",
                "calendar_id": self.calendar.id,
                "dayofweek": "5",
                "hour_from": 8,
                "hour_to": 12,
                "day_period": "morning",
            }
        )
        self.assertTrue(
            self.calendar._is_working_day(self.SATURDAY),
            "adding a Saturday attendance must make _is_working_day True",
        )

    def test_is_working_day_reflects_removed_attendance(self):
        monday = date(2025, 1, 6)
        self.assertTrue(self.calendar._is_working_day(monday))

        self.calendar.attendance_ids.filtered(lambda a: a.dayofweek == "0").unlink()
        self.assertFalse(
            self.calendar._is_working_day(monday),
            "removing every Monday attendance must make _is_working_day False",
        )

    def test_get_working_hours_returns_independent_mapping(self):
        first = self.calendar._get_working_days()
        _ = first["0"]["6"]
        second = self.calendar._get_working_days()
        self.assertNotIn("6", second.get("0", {}))


@tagged("post_install", "-at_install")
class TestIntervalBatchStringTz(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "String TZ", "tz": "UTC"}
        )
        cls.resource = cls.env["resource.resource"].create(
            {"name": "STZ res", "calendar_id": cls.calendar.id, "tz": "UTC"}
        )
        cls.env["resource.schedule.exception"].create(
            {
                "name": "Global off",
                "calendar_id": cls.calendar.id,
                "date_from": datetime(2025, 1, 8, 0, 0),
                "date_to": datetime(2025, 1, 8, 23, 59),
            }
        )
        cls.start = datetime(2025, 1, 6, 0, 0).replace(tzinfo=UTC)
        cls.end = datetime(2025, 1, 11, 0, 0).replace(tzinfo=UTC)
        cls.tz_str = "Europe/Brussels"
        cls.tz_obj = timezone("Europe/Brussels")

    def test_attendance_intervals_string_tz(self):
        by_str = self.calendar._attendance_intervals_batch(
            self.start, self.end, self.resource, tz=self.tz_str
        )
        by_obj = self.calendar._attendance_intervals_batch(
            self.start, self.end, self.resource, tz=self.tz_obj
        )
        self.assertEqual(list(by_str[self.resource.id]), list(by_obj[self.resource.id]))

    def test_leave_intervals_string_tz(self):
        by_str = self.calendar._leave_intervals_batch(
            self.start, self.end, self.resource, tz=self.tz_str
        )
        by_obj = self.calendar._leave_intervals_batch(
            self.start, self.end, self.resource, tz=self.tz_obj
        )
        self.assertEqual(list(by_str[self.resource.id]), list(by_obj[self.resource.id]))

    def test_work_intervals_string_tz(self):
        by_str = self.calendar._work_intervals_batch(
            self.start, self.end, self.resource, tz=self.tz_str
        )
        by_obj = self.calendar._work_intervals_batch(
            self.start, self.end, self.resource, tz=self.tz_obj
        )
        self.assertEqual(list(by_str[self.resource.id]), list(by_obj[self.resource.id]))

    def test_unavailable_intervals_string_tz(self):
        by_str = self.calendar._unavailable_intervals_batch(
            self.start, self.end, self.resource, tz=self.tz_str
        )
        by_obj = self.calendar._unavailable_intervals_batch(
            self.start, self.end, self.resource, tz=self.tz_obj
        )
        self.assertEqual(by_str[self.resource.id], by_obj[self.resource.id])


@tagged("post_install", "-at_install")
class TestBatchedResourceQueries(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Resource = cls.env["resource.resource"]
        cls.fixed = cls.env.company.resource_calendar_id
        cls.flexible = cls.env["resource.calendar"].create(
            {"name": "Flexible", "schedule_type": "flexible", "hours_per_week": 30}
        )
        cls.fixed_resources = Resource.create(
            [
                {"name": f"fixed {i}", "calendar_id": cls.fixed.id, "tz": "UTC"}
                for i in range(10)
            ]
        )
        cls.flexible_resources = Resource.create(
            [
                {"name": f"flex {i}", "calendar_id": cls.flexible.id, "tz": "UTC"}
                for i in range(10)
            ]
        )
        cls.env["resource.schedule.exception"].create(
            [
                {
                    "name": "off",
                    "resource_id": resource.id,
                    "calendar_id": resource.calendar_id.id,
                    "date_from": datetime(2026, 9, 8),
                    "date_to": datetime(2026, 9, 9),
                }
                for resource in (cls.fixed_resources | cls.flexible_resources)[::3]
            ]
        )
        cls.start = datetime(2026, 9, 7, tzinfo=UTC)
        cls.stop = datetime(2026, 9, 14, tzinfo=UTC)

    def _count(self, fn):
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        result = fn()
        return self.env.cr.sql_statement_count - before, result

    def test_unavailable_intervals_of_flexible_resources_are_batched(self):
        one, _ = self._count(
            lambda: self.flexible._unavailable_intervals_batch(
                self.start, self.stop, self.flexible_resources[0]
            )
        )
        many, result = self._count(
            lambda: self.flexible._unavailable_intervals_batch(
                self.start, self.stop, self.flexible_resources
            )
        )
        self.assertLessEqual(many, one + 2)
        self.assertEqual(len(result), len(self.flexible_resources))
        self.assertEqual(len(result[self.flexible_resources[2].id]), 1)
        self.assertEqual(result[self.flexible_resources[1].id], [])

    def test_unavailable_intervals_mixed_batch_matches_singles(self):
        resources = self.fixed_resources[:3] | self.flexible_resources[:3]
        batch = self.fixed._unavailable_intervals_batch(
            self.start, self.stop, resources
        )
        for resource in resources:
            single = self.fixed._unavailable_intervals_batch(
                self.start, self.stop, resource
            )
            self.assertEqual(batch[resource.id], single[resource.id])


@tagged("post_install", "-at_install")
class TestWorkSchedule(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Resource = cls.env["resource.resource"]
        cls.fixed_calendar = cls.env.company.resource_calendar_id
        cls.fixed_calendar.tz = "UTC"
        flexible_calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible 20h",
                "schedule_type": "flexible",
                "hours_per_week": 20,
                "hours_per_day": 4,
                "tz": "UTC",
            }
        )
        cls.fixed = Resource.create(
            {"name": "fixed", "calendar_id": cls.fixed_calendar.id, "tz": "UTC"}
        )
        cls.flexible = Resource.create(
            {"name": "flexible", "calendar_id": flexible_calendar.id, "tz": "UTC"}
        )
        cls.free = Resource.create({"name": "free", "calendar_id": False, "tz": "UTC"})
        cls.env["resource.schedule.exception"].create(
            {
                "name": "off",
                "resource_id": cls.fixed.id,
                "calendar_id": cls.fixed_calendar.id,
                "date_from": datetime(2026, 6, 2),
                "date_to": datetime(2026, 6, 3),
            }
        )
        cls.start = datetime(2026, 6, 1, tzinfo=UTC)
        cls.stop = datetime(2026, 6, 6, tzinfo=UTC)

    def test_one_call_covers_every_kind_of_resource(self):
        resources = self.fixed | self.flexible | self.free
        schedule = resources._get_work_schedule(self.start, self.stop)
        self.assertEqual(set(schedule.intervals), set(resources.ids))
        self.assertEqual(schedule.flexible_ids, {self.flexible.id, self.free.id})
        self.assertEqual(schedule.work_hours(self.fixed), 32)
        self.assertEqual(schedule.work_hours(self.flexible), 20)
        self.assertEqual(schedule.work_hours(self.free), 120)

    def test_a_resource_outside_the_schedule_reads_as_empty(self):
        schedule = self.fixed._get_work_schedule(self.start, self.stop)
        self.assertEqual(len(schedule.intervals[self.flexible.id]), 0)
        self.assertEqual(schedule.work_hours(self.flexible), 0)

    def test_schedule_agrees_with_the_two_apis_it_replaces(self):
        schedule = (self.fixed | self.flexible)._get_work_schedule(
            self.start, self.stop
        )
        fixed_intervals, _calendars = self.fixed._get_valid_work_intervals(
            self.start, self.stop
        )
        self.assertEqual(
            list(schedule.intervals[self.fixed.id]),
            list(fixed_intervals[self.fixed.id]),
        )
        intervals, per_day, per_week = (
            self.flexible._get_flexible_resource_valid_work_intervals(
                self.start, self.stop
            )
        )
        self.assertEqual(
            schedule.work_hours(self.flexible),
            self.flexible._get_flexible_resource_work_hours(
                intervals[self.flexible.id],
                per_day[self.flexible.id],
                per_week[self.flexible.id],
            ),
        )

    def test_compute_leaves_is_honoured_for_fixed_resources(self):
        with_leaves = self.fixed._get_work_schedule(self.start, self.stop)
        without = self.fixed._get_work_schedule(
            self.start, self.stop, compute_leaves=False
        )
        self.assertEqual(with_leaves.work_hours(self.fixed), 32)
        self.assertEqual(without.work_hours(self.fixed), 40)

    def test_work_hours_per_day_is_filled_for_both_kinds(self):
        schedule = (self.fixed | self.flexible)._get_work_schedule(
            self.start, self.stop
        )
        fixed_days = defaultdict(float)
        schedule.work_hours(self.fixed, work_hours_per_day=fixed_days)
        self.assertEqual(sum(fixed_days.values()), 32)
        self.assertNotIn(datetime(2026, 6, 2).date(), fixed_days)
        flexible_days = defaultdict(float)
        schedule.work_hours(self.flexible, work_hours_per_day=flexible_days)
        self.assertEqual(sum(flexible_days.values()), 20)
