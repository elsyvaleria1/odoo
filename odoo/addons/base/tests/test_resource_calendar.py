from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.datetime import timezone
from odoo.tests import TransactionCase, tagged

from .common import ResourceCase
from odoo.addons.base.models.resource_utils import week_type_of


class TestResourceCalendar(TransactionCase):
    def test_fully_flexible_attendance_interval_duration(self):
        resource = self.env["resource.resource"].create(
            {
                "name": "Wade Wilson",
                "calendar_id": False,
                "tz": "America/New_York",
            }
        )
        calendar = resource.calendar_id
        self.assertEqual(calendar.schedule_type, "fully_flexible")
        UTC = timezone("UTC")
        start_dt = datetime(2025, 6, 4, 18, 0, 0).astimezone(UTC)
        end_dt = datetime(2025, 6, 4, 21, 0, 0).astimezone(UTC)
        result_per_resource_id = calendar._attendance_intervals_batch(
            start_dt, end_dt, resource
        )
        start, end, attendance = result_per_resource_id[resource.id]._items[0]
        self.assertEqual(
            start, start_dt, "Output start time should match the input start time"
        )
        self.assertEqual(end, end_dt, "Output end time should match the input end time")
        self.assertEqual(
            attendance.duration_hours, 3.0, "Attendance duration should be 3 hours"
        )
        self.assertAlmostEqual(
            attendance.duration_days,
            3.0 / calendar.hours_per_day,
            places=6,
            msg="3 hours is 3/hours_per_day of a working day. This asserted a flat"
            " 0.125 -- 3/24 -- back when a fully-flexible day was modelled as 24"
            " wall-clock hours, which is the same modelling that made a Mon-Fri"
            " absence measure 4.375 days instead of 5.",
        )

    def test_flexible_calendar_attendance_interval_duration(self):
        flexible_calendar = self.env["resource.calendar"].create(
            {
                "name": "Flexible Calendar",
                "hours_per_day": 7.0,
                "hours_per_week": 30,
                "full_time_required_hours": 30,
                "schedule_type": "flexible",
                "tz": "UTC",
            }
        )

        expected_hours = [7, 7, 7, 7, 2]

        start_dt = datetime(2025, 6, 2, 0, 0, 0).astimezone(UTC)
        end_dt = datetime(2025, 6, 7, 23, 59, 59).astimezone(UTC)
        result_per_resource_id = flexible_calendar._attendance_intervals_batch(
            start_dt, end_dt
        )
        self.assertEqual(
            expected_hours,
            [
                (end - start).total_seconds() / 3600
                for start, end, dummy_attendance in result_per_resource_id[0]._items
            ],
        )
        self.assertEqual(
            expected_hours,
            [
                dummy_attendance.duration_hours
                for start, end, dummy_attendance in result_per_resource_id[0]._items
            ],
        )

        start_dt = datetime(2025, 6, 2, 11, 0, 0).astimezone(UTC)
        end_dt = datetime(2025, 6, 7, 13, 0, 0).astimezone(UTC)
        result_per_resource_id = flexible_calendar._attendance_intervals_batch(
            start_dt, end_dt
        )

        self.assertTrue(
            start_dt <= result_per_resource_id[0]._items[0][0],
            "First attendance interval should not start before start_dt",
        )
        self.assertTrue(
            end_dt >= result_per_resource_id[0]._items[4][1],
            "Last attendance interval should not end after end_dt",
        )

    def test_flexible_calendar_days_data_without_hours_per_day(self):
        bare = self.env["resource.calendar"].create(
            {
                "name": "Bare Flexible Calendar",
                "schedule_type": "flexible",
                "tz": "UTC",
            }
        )
        self.assertEqual(bare.hours_per_day, 0.0)

        start_dt = datetime(2025, 6, 2, 0, 0, 0).astimezone(UTC)
        end_dt = datetime(2025, 6, 6, 23, 59, 59).astimezone(UTC)
        intervals = bare._attendance_intervals_batch(start_dt, end_dt)[0]
        data = bare._get_duration_data(intervals)
        self.assertGreater(data["hours"], 0.0)
        self.assertGreater(data["days"], 0.0)

    def test_domain_filters_the_records_the_path_reads(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "9-to-5",
                "tz": "UTC",
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Morning",
                            "dayofweek": str(i),
                            "hour_from": 8,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    )
                    for i in range(5)
                ]
                + [
                    (
                        0,
                        0,
                        {
                            "name": "Afternoon",
                            "dayofweek": str(i),
                            "hour_from": 13,
                            "hour_to": 17,
                            "day_period": "afternoon",
                        },
                    )
                    for i in range(5)
                ],
            }
        )
        start_dt = datetime(2026, 6, 1, 0, 0, 0).astimezone(UTC)
        end_dt = datetime(2026, 6, 5, 23, 59, 59).astimezone(UTC)
        without_domain = calendar.get_work_hours_count(
            start_dt, end_dt, compute_leaves=False
        )
        with_domain = calendar.get_work_hours_count(
            start_dt,
            end_dt,
            compute_leaves=False,
            domain=[("day_period", "=", "morning")],
        )
        self.assertEqual(
            without_domain,
            with_domain,
            "the domain chooses exceptions, so without them it has nothing to filter",
        )
        self.assertEqual(
            calendar.get_work_duration_data(
                start_dt,
                end_dt,
                compute_leaves=False,
                domain=[("day_period", "=", "morning")],
            )["hours"],
            without_domain,
            "one meaning for the domain of every work reader; lines are filtered "
            "through get_attendance_duration_data, hr_payroll's own path",
        )

    def test_attendance_duration_data_filters_the_attendances(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "9-to-5",
                "tz": "UTC",
                "attendance_ids": [
                    Command.create(
                        {
                            "name": period.capitalize(),
                            "dayofweek": str(day),
                            "hour_from": hour_from,
                            "hour_to": hour_from + 4,
                            "day_period": period,
                        }
                    )
                    for day in range(5)
                    for period, hour_from in (("morning", 8), ("afternoon", 13))
                ],
            }
        )
        start_dt = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
        end_dt = datetime(2026, 6, 5, 23, 59, 59, tzinfo=UTC)

        everything = calendar.get_attendance_duration_data(start_dt, end_dt)
        mornings = calendar.get_attendance_duration_data(
            start_dt, end_dt, domain=[("day_period", "=", "morning")]
        )

        self.assertEqual(everything["hours"], 40.0)
        self.assertEqual(mornings["hours"], 20.0)

    def test_the_calendar_read_decides_not_the_resource_own(self):
        fixed = self.env["resource.calendar"].create(
            {
                "name": "9-to-5 with lunch",
                "tz": "UTC",
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": f"{period}",
                            "dayofweek": str(i),
                            "hour_from": hour_from,
                            "hour_to": hour_to,
                            "day_period": period,
                        },
                    )
                    for i in range(5)
                    for period, hour_from, hour_to in (
                        ("morning", 9, 12),
                        ("lunch", 12, 13),
                        ("afternoon", 13, 17),
                    )
                ],
            }
        )
        resource = self.env["resource.resource"].create(
            {"name": "On fixed calendar", "calendar_id": fixed.id, "tz": "UTC"}
        )
        flexible_self = self.env["resource.calendar"].create(
            {
                "name": "Flexible fallback",
                "schedule_type": "flexible",
                "hours_per_day": 8.0,
                "full_time_required_hours": 40.0,
                "tz": "UTC",
            }
        )
        start_dt = datetime(2026, 6, 1, 0, 0, 0).astimezone(UTC)
        end_dt = datetime(2026, 6, 6, 23, 59, 59).astimezone(UTC)

        via_own_calendar = fixed._attendance_intervals_batch(
            start_dt, end_dt, resource
        )[resource.id]
        via_flexible_self = flexible_self._attendance_intervals_batch(
            start_dt, end_dt, resource
        )[resource.id]
        self.assertEqual(len(via_own_calendar), 10)
        self.assertEqual(
            [stop - start for start, stop, _meta in via_flexible_self],
            [timedelta(hours=8)] * 5,
        )

        lunch_via_own_calendar = fixed._attendance_intervals_batch(
            start_dt, end_dt, resource, lunch=True
        )[resource.id]
        lunch_via_flexible_self = flexible_self._attendance_intervals_batch(
            start_dt, end_dt, resource, lunch=True
        )[resource.id]
        self.assertEqual(len(lunch_via_own_calendar), 5)
        self.assertFalse(lunch_via_flexible_self)

    def test_flexible_partial_day_is_a_fraction_not_a_whole_day(self):
        fixed = self.env["resource.calendar"].create(
            {
                "name": "9-to-5 (measuring calendar)",
                "tz": "UTC",
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Morning",
                            "dayofweek": str(i),
                            "hour_from": 9,
                            "hour_to": 17,
                            "day_period": "morning",
                        },
                    )
                    for i in range(5)
                ],
            }
        )
        flexible = self.env["resource.calendar"].create(
            {
                "name": "Flexible, tight weekly cap",
                "schedule_type": "flexible",
                "hours_per_day": 8.0,
                "full_time_required_hours": 10,
                "tz": "UTC",
            }
        )
        resource = self.env["resource.resource"].create(
            {"name": "On flexible calendar", "calendar_id": flexible.id, "tz": "UTC"}
        )
        start_dt = datetime(2026, 6, 1, 0, 0, 0).astimezone(UTC)
        end_dt = datetime(2026, 6, 3, 23, 59, 59).astimezone(UTC)
        intervals = flexible._attendance_intervals_batch(start_dt, end_dt, resource)[
            resource.id
        ]
        data = flexible._get_duration_data(intervals)
        self.assertEqual(data["hours"], 10.0)
        self.assertEqual(data["days"], 1.25)
        measured = fixed._get_duration_data(
            fixed._attendance_intervals_batch(start_dt, end_dt, resource)[resource.id]
        )
        self.assertEqual((measured["hours"], measured["days"]), (24.0, 3.0))

    def test_public_holiday_calendar_no_company(self):
        self.env["resource.schedule.exception"].create(
            [
                {
                    "name": "Public Holiday for company",
                    "company_id": self.env.company.id,
                    "date_from": datetime(2019, 5, 29, 0, 0, 0),
                    "date_to": datetime(2019, 5, 30, 0, 0, 0),
                    "resource_id": False,
                }
            ]
        )
        calendar = self.env["resource.calendar"].create(
            {
                "name": "40 hours/week",
                "hours_per_day": 8,
                "full_time_required_hours": 40,
            }
        )
        calendar.company_id = False
        date_from = datetime(2019, 5, 27, 0, 0, 0).astimezone(UTC)
        date_to = datetime(2019, 5, 31, 23, 59, 59).astimezone(UTC)
        days = calendar._get_unusual_days(date_from, date_to, self.env.company)
        expected_res = {
            "2019-05-27": False,
            "2019-05-28": False,
            "2019-05-29": True,
            "2019-05-30": False,
            "2019-05-31": False,
        }
        self.assertEqual(days, expected_res)

    def test_public_holidays_domain_scopes_by_window_company_and_calendar(self):
        company_a, company_b = self.env["res.company"].create(
            [{"name": "Holidays A"}, {"name": "Holidays B"}]
        )
        calendar_a, calendar_other = self.env["resource.calendar"].create(
            [
                {"name": "A", "company_id": company_a.id},
                {"name": "Other", "company_id": company_a.id},
            ]
        )
        resource = self.env["resource.resource"].create(
            {"name": "Someone", "company_id": company_a.id}
        )
        Leaves = self.env["resource.schedule.exception"]

        def holiday(company, day, **vals):
            return Leaves.with_company(company).create(
                {
                    "name": f"{company.name} {day} {vals}",
                    "date_from": datetime(2030, 5, day, 8),
                    "date_to": datetime(2030, 5, day, 17),
                    **vals,
                }
            )

        every_calendar = holiday(company_a, 1)
        own_calendar = holiday(company_a, 2, calendar_id=calendar_a.id)
        other_calendar = holiday(company_a, 3, calendar_id=calendar_other.id)
        other_company = holiday(company_b, 1)
        personal = holiday(company_a, 1, resource_id=resource.id)
        fixtures = (
            every_calendar | own_calendar | other_calendar | other_company | personal
        )

        def found(date_from, date_to, **scope):
            return Leaves.search(
                Leaves._get_domain_public_holidays(date_from, date_to, **scope)
                & Domain("id", "in", fixtures.ids)
            )

        window = (datetime(2030, 5, 1), datetime(2030, 5, 4))
        self.assertEqual(
            found(*window, companies=company_a, calendars=calendar_a),
            every_calendar | own_calendar,
        )
        self.assertEqual(
            found(*window, companies=company_a),
            every_calendar | own_calendar | other_calendar,
        )
        self.assertEqual(
            found(*window),
            every_calendar | own_calendar | other_calendar | other_company,
        )
        self.assertFalse(
            found(
                datetime(2030, 5, 1, 17), datetime(2030, 5, 2, 8), companies=company_a
            ),
            "a window touching a holiday's edges shares no instant with it",
        )
        self.assertEqual(
            found(
                datetime(2030, 5, 1, 16, 59, 59),
                datetime(2030, 5, 2, 8, 0, 1),
                companies=company_a,
            ),
            every_calendar | own_calendar,
        )
        self.assertEqual(
            found(date(2030, 4, 30), date(2030, 5, 1), companies=company_a),
            every_calendar,
            "a date bound covers its whole day",
        )


@tagged("post_install", "-at_install")
class TestSearchWorkTimeRate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar_full = cls.env["resource.calendar"].create(
            {"name": "Full Time 40h", "tz": "UTC"}
        )
        cls.calendar_part = cls.env["resource.calendar"].create(
            {"name": "Part Time 20h", "tz": "UTC"}
        )
        cls.calendar_part.attendance_ids.unlink()
        for day in range(5):
            cls.env["resource.calendar.attendance"].create(
                {
                    "name": f"Day {day}",
                    "calendar_id": cls.calendar_part.id,
                    "dayofweek": str(day),
                    "hour_from": 8,
                    "hour_to": 12,
                    "day_period": "morning",
                }
            )

    def test_search_rate_greater_than(self):
        results = self.env["resource.calendar"].search([("work_time_rate", ">", 80)])
        self.assertIn(self.calendar_full, results)
        self.assertNotIn(self.calendar_part, results)

    def test_search_rate_less_than(self):
        results = self.env["resource.calendar"].search([("work_time_rate", "<", 60)])
        self.assertIn(self.calendar_part, results)
        self.assertNotIn(self.calendar_full, results)

    def test_search_rate_in(self):
        rate = round(self.calendar_part.work_time_rate)
        results = self.env["resource.calendar"].search(
            [("work_time_rate", "in", [rate, 100])]
        )
        self.assertIn(self.calendar_full, results)


@tagged("post_install", "-at_install")
class TestTwoWeekCalendarEdgeCases(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Standard Calendar", "tz": "UTC"}
        )

    def test_switch_to_two_weeks_and_back(self):
        original_count = len(
            self.calendar.attendance_ids.filtered(lambda a: not a.display_type)
        )
        self.assertFalse(self.calendar.two_weeks_calendar)

        self.calendar.action_switch_two_weeks()
        self.assertTrue(self.calendar.two_weeks_calendar)
        two_week_non_sections = self.calendar.attendance_ids.filtered(
            lambda a: not a.display_type
        )
        self.assertEqual(len(two_week_non_sections), original_count * 2)

        self.calendar.action_switch_two_weeks()
        self.assertFalse(self.calendar.two_weeks_calendar)

    def test_compute_two_weeks_attendance_non_two_week(self):
        self.assertFalse(self.calendar.two_weeks_calendar)
        self.assertFalse(self.calendar.attendance_ids_1st_week)
        self.assertFalse(self.calendar.attendance_ids_2nd_week)

    def test_switch_to_two_weeks_large_calendar_keeps_weeks_ordered(self):
        big = self.env["resource.calendar"].create(
            {
                "name": "Big Calendar",
                "tz": "UTC",
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": f"D{day}S{slot}",
                            "dayofweek": str(day),
                            "hour_from": 8 + slot,
                            "hour_to": 9 + slot,
                            "day_period": "morning",
                        },
                    )
                    for day in range(7)
                    for slot in range(4)
                ],
            }
        )
        self.assertEqual(len(big.attendance_ids), 28)
        big.action_switch_two_weeks()

        lines = big.attendance_ids
        sections = lines.filtered("display_type").sorted("sequence")
        self.assertEqual(len(sections), 2)
        first_week = lines.filtered(lambda a: not a.display_type and a.week_type == "0")
        second_week = lines.filtered(
            lambda a: not a.display_type and a.week_type == "1"
        )
        self.assertEqual(len(first_week), 28)
        self.assertEqual(len(second_week), 28)
        self.assertLess(
            max(first_week.mapped("sequence")),
            sections[1].sequence,
            "every first-week line must sort before the second-week section",
        )
        self.assertLess(
            sections[1].sequence,
            min(second_week.mapped("sequence")),
            "every second-week line must sort after its section",
        )

    def test_is_working_day_two_week_calendar(self):
        from datetime import date

        self.calendar.action_switch_two_weeks()
        week1_monday = self.calendar.attendance_ids.filtered(
            lambda a: a.week_type == "1" and a.dayofweek == "0" and not a.display_type
        )
        week1_monday.unlink()

        test_date = date(2025, 1, 6)
        if week_type_of(test_date) == "1":
            self.assertFalse(self.calendar._is_working_day(test_date))
        else:
            self.assertTrue(self.calendar._is_working_day(test_date))


@tagged("post_install", "-at_install")
class TestSwitchBasedOnDuration(TransactionCase):
    def _counts(self, calendar):
        lines = calendar.attendance_ids.filtered(lambda a: not a.display_type)
        return {
            "lines": len(lines),
            "sections": len(calendar.attendance_ids) - len(lines),
            "week_less": len(lines.filtered(lambda a: not a.week_type)),
        }

    def test_duration_round_trip_on_a_two_weeks_calendar(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "Round trip", "tz": "UTC"}
        )
        calendar.action_switch_two_weeks()
        self.env.flush_all()
        before = self._counts(calendar)
        self.assertEqual(before["week_less"], 0)
        hours_before = calendar.hours_per_week

        calendar.action_switch_duration_based()
        self.env.flush_all()
        calendar.action_switch_duration_based()
        self.env.flush_all()

        after = self._counts(calendar)
        self.assertEqual(after["week_less"], 0, "lines belonging to neither week")
        self.assertEqual(after["lines"], before["lines"])
        self.assertEqual(after["sections"], before["sections"])
        self.assertEqual(calendar.hours_per_week, hours_before)

    def test_duration_round_trip_on_a_single_week_calendar(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "Single week", "tz": "UTC"}
        )
        self.env.flush_all()
        before = self._counts(calendar)
        hours_before = calendar.hours_per_week

        calendar.action_switch_duration_based()
        self.env.flush_all()
        calendar.action_switch_duration_based()
        self.env.flush_all()

        self.assertEqual(self._counts(calendar), before)
        self.assertEqual(calendar.hours_per_week, hours_before)

    def test_switch_two_weeks_round_trip_unaffected(self):
        calendar = self.env["resource.calendar"].create({"name": "Type", "tz": "UTC"})
        self.env.flush_all()
        before = self._counts(calendar)
        calendar.action_switch_two_weeks()
        self.env.flush_all()
        self.assertEqual(self._counts(calendar)["lines"], before["lines"] * 2)
        calendar.action_switch_two_weeks()
        self.env.flush_all()
        self.assertEqual(self._counts(calendar), before)


@tagged("post_install", "-at_install")
class TestSearchWorkTimeRateFreshness(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Calendar = cls.env["resource.calendar"]
        cls.calendar = cls.Calendar.create({"name": "Part time", "tz": "UTC"})
        cls.calendar.attendance_ids.unlink()
        cls.env["resource.calendar.attendance"].create(
            [
                {
                    "name": f"AM {d}",
                    "calendar_id": cls.calendar.id,
                    "dayofweek": str(d),
                    "hour_from": 8,
                    "hour_to": 12,
                    "day_period": "morning",
                }
                for d in range(5)
            ]
        )

    def test_search_reflects_pending_rate_change(self):
        self.env.flush_all()
        self.assertLess(self.calendar.work_time_rate, 60)

        self.env["resource.calendar.attendance"].create(
            [
                {
                    "name": f"PM {d}",
                    "calendar_id": self.calendar.id,
                    "dayofweek": str(d),
                    "hour_from": 13,
                    "hour_to": 17,
                    "day_period": "afternoon",
                }
                for d in range(5)
            ]
        )
        results = self.Calendar.search([("work_time_rate", ">", 80)])
        self.assertIn(
            self.calendar,
            results,
            "search must see the pending full-time rate, not the stale DB value",
        )


@tagged("post_install", "-at_install")
class TestCalendarIntegrity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Calendar = cls.env["resource.calendar"]
        cls.Attendance = cls.env["resource.calendar.attendance"]

    def _line(self, calendar, dayofweek):
        return calendar.attendance_ids.filtered(
            lambda a: a.dayofweek == dayofweek and a.day_period == "morning"
        )

    def test_copying_a_flexible_calendar_keeps_its_weekly_total(self):
        flexible = self.Calendar.create(
            {
                "name": "Flexible",
                "schedule_type": "flexible",
                "hours_per_week": 30,
                "hours_per_day": 6,
            }
        )
        copy = flexible.copy()
        self.assertEqual(copy.hours_per_week, 30)
        self.assertEqual(copy.hours_per_day, 6)

    def test_copying_with_new_lines_recomputes_the_totals(self):
        source = self.Calendar.create({"name": "Full time"})
        self.assertEqual(source.hours_per_week, 40)
        half = source.copy(
            {
                "attendance_ids": [
                    Command.create(
                        {
                            "name": f"Day {day}",
                            "dayofweek": day,
                            "hour_from": 8,
                            "hour_to": 12,
                            "day_period": "morning",
                        }
                    )
                    for day in "01234"
                ]
            }
        )
        self.assertEqual(half.hours_per_week, 20)
        self.assertEqual(half.hours_per_day, 4)
        self.assertEqual(set(half.attendance_ids.mapped("duration_days")), {1.0})

    def test_overlap_is_rejected_when_a_line_is_written_directly(self):
        calendar = self.Calendar.create({"name": "Fixed"})
        with self.assertRaises(ValidationError):
            self._line(calendar, "0").write({"hour_to": 16})

    def test_overlap_is_rejected_when_a_line_is_created_directly(self):
        calendar = self.Calendar.create({"name": "Fixed"})
        with self.assertRaises(ValidationError):
            self.Attendance.create(
                {
                    "calendar_id": calendar.id,
                    "name": "Clash",
                    "dayofweek": "1",
                    "hour_from": 9,
                    "hour_to": 11,
                    "day_period": "morning",
                }
            )

    def test_overlap_is_rejected_when_a_line_moves_to_another_day(self):
        calendar = self.Calendar.create({"name": "Fixed"})
        saturday = self.Attendance.create(
            {
                "calendar_id": calendar.id,
                "name": "Saturday",
                "dayofweek": "5",
                "hour_from": 8,
                "hour_to": 12,
                "day_period": "morning",
            }
        )
        with self.assertRaises(ValidationError):
            saturday.dayofweek = "0"

    def test_weekly_totals_follow_a_period_change(self):
        calendar = self.Calendar.create({"name": "Fixed"})
        self.assertEqual(calendar.hours_per_week, 40)
        lunch = calendar.attendance_ids.filtered(lambda a: a.day_period == "lunch")[0]
        lunch.write({"day_period": "morning", "hour_from": 7, "hour_to": 8})
        self.assertEqual(calendar.hours_per_week, 41)
        self.assertEqual(calendar.hours_per_day, 8.2)

    def test_weekly_totals_follow_a_section_change(self):
        calendar = self.Calendar.create({"name": "Fixed"})
        self._line(calendar, "0").display_type = "line_section"
        self.assertEqual(calendar.hours_per_week, 36)

    def test_weekly_totals_follow_duration_based_switch(self):
        calendar = self.Calendar.create({"name": "Fixed"})
        calendar.action_switch_duration_based()
        calendar.attendance_ids[0].duration_hours = 2
        self.assertEqual(calendar.hours_per_week, 38)

    def test_two_weeks_flag_requires_week_type_on_every_line(self):
        calendar = self.Calendar.create({"name": "Fixed"})
        with self.assertRaises(ValidationError):
            calendar.two_weeks_calendar = True

    def test_switching_back_to_one_week_under_a_two_weeks_company_default(self):
        company_calendar = self.env.company.resource_calendar_id
        company_calendar.action_switch_two_weeks()
        calendar = self.Calendar.create({"name": "Follower"})
        self.assertTrue(calendar.two_weeks_calendar)
        calendar.action_switch_two_weeks()
        self.assertFalse(calendar.two_weeks_calendar)
        self.assertFalse(calendar.attendance_ids.filtered("display_type"))
        self.assertEqual(set(calendar.attendance_ids.mapped("week_type")), {False})
        self.assertEqual(calendar.hours_per_week, 40)

    def test_duration_switch_under_a_two_weeks_company_default(self):
        company_calendar = self.env.company.resource_calendar_id
        company_calendar.action_switch_two_weeks()
        calendar = self.Calendar.create({"name": "Follower"})
        calendar.action_switch_duration_based()
        calendar.action_switch_duration_based()
        lines = calendar.attendance_ids.filtered(lambda a: not a.display_type)
        self.assertEqual(len(lines), 30)
        self.assertEqual(set(lines.mapped("week_type")), {"0", "1"})
        self.assertEqual(calendar.hours_per_week, 40)

    def test_break_on_duration_based_calendar_is_a_validation_error(self):
        calendar = self.Calendar.create({"name": "Duration"})
        calendar.action_switch_duration_based()
        with self.assertRaises(ValidationError):
            self.Attendance.create(
                {
                    "calendar_id": calendar.id,
                    "name": "Break",
                    "dayofweek": "5",
                    "hour_from": 12,
                    "hour_to": 13,
                    "day_period": "lunch",
                }
            )

    def test_two_weeks_split_views_follow_line_edits(self):
        calendar = self.Calendar.create({"name": "Fixed"})
        calendar.action_switch_two_weeks()
        first_before = len(calendar.attendance_ids_1st_week)
        line = self.Attendance.create(
            {
                "calendar_id": calendar.id,
                "name": "Saturday",
                "dayofweek": "5",
                "hour_from": 8,
                "hour_to": 12,
                "day_period": "morning",
                "week_type": "1",
            }
        )
        self.assertEqual(len(calendar.attendance_ids_1st_week), first_before)
        line.week_type = "0"
        self.assertEqual(len(calendar.attendance_ids_1st_week), first_before + 1)


@tagged("post_install", "-at_install")
class TestCompanyCalendarCreation(TransactionCase):
    def test_a_shared_calendar_chosen_as_default_stays_shared(self):
        shared = self.env["resource.calendar"].create(
            {"name": "Shared", "company_id": False}
        )
        company = self.env["res.company"].create(
            {"name": "Newco", "resource_calendar_id": shared.id}
        )
        self.assertEqual(company.resource_calendar_id, shared)
        self.assertFalse(shared.company_id)

    def test_a_company_without_a_default_gets_its_own(self):
        company = self.env["res.company"].create({"name": "Newco"})
        self.assertEqual(company.resource_calendar_id.company_id, company)


class TestCalendarDisplayFields(ResourceCase):
    def test_work_resources_count_reacts_to_new_resources(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "counted", "company_id": self.company.id, "tz": "UTC"}
        )
        self.assertEqual(calendar.work_resources_count, 0)
        self._resource(name="Counted", calendar_id=calendar.id)
        self.assertEqual(calendar.work_resources_count, 1)

    def test_two_weeks_explanation_agrees_with_the_section_labels(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "explained", "company_id": self.company.id, "tz": "UTC"}
        )
        for tz_name in ("Pacific/Kiritimati", "Pacific/Midway"):
            scoped = calendar.with_context(tz=tz_name)
            scoped.invalidate_recordset(["two_weeks_explanation"])
            local_today = fields.Date.context_today(scoped)
            expected = "the second" if week_type_of(local_today) == "1" else "the first"
            self.assertIn(
                expected,
                scoped.two_weeks_explanation,
                f"explanation disagrees with the week the labels show in {tz_name}",
            )

    def test_calendar_tz_default_survives_a_missing_admin_xmlid(self):
        self.env.user.tz = False
        calendar_model = self.env["resource.calendar"].with_context(tz=False)

        real_ref = type(self.env).ref

        def ref_without_admin(env_self, xmlid, raise_if_not_found=True):
            if xmlid == "base.user_admin":
                if raise_if_not_found:
                    raise ValueError(xmlid)
                return None
            return real_ref(env_self, xmlid, raise_if_not_found=raise_if_not_found)

        self.patch(type(self.env), "ref", ref_without_admin)
        self.assertEqual(calendar_model._default_tz(), "UTC")
        self.assertTrue(
            calendar_model.create({"name": "no admin", "company_id": self.company.id})
        )


@tagged("post_install", "-at_install")
class TestCalendarDefinitions(TransactionCase):
    def test_the_fully_flexible_schedule_stays_shared(self):
        shared = self.env.ref("base.resource_calendar_fully_flexible")
        for vals in (
            {"schedule_type": "flexible"},
            {"tz": "Europe/Brussels"},
            {"company_id": self.env.company.id},
            {"active": False},
        ):
            with self.subTest(vals=vals), self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    shared.write(vals)
                    self.env.flush_all()

    def test_a_schedule_without_fixed_hours_keeps_no_line(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "becomes flexible", "tz": "UTC"}
        )
        self.assertTrue(calendar.attendance_ids)
        calendar.schedule_type = "flexible"
        self.assertFalse(calendar.attendance_ids)
        with self.assertRaises(ValidationError):
            calendar.write(
                {
                    "attendance_ids": [
                        Command.create(
                            {
                                "name": "Monday",
                                "dayofweek": "0",
                                "hour_from": 8,
                                "hour_to": 12,
                            }
                        )
                    ]
                }
            )
        calendar.schedule_type = "fully_fixed"
        self.assertTrue(calendar.attendance_ids, "fixed hours again: the company's")

    def test_renaming_a_line_recomputes_no_booking(self):
        calendar = self.env["resource.calendar"].create({"name": "lines", "tz": "UTC"})
        Reservation = self.env.registry["resource.reservation"]
        with patch.object(
            Reservation, "_recompute_allocated_hours", autospec=True
        ) as recompute:
            calendar.attendance_ids[:1].name = "Renamed"
            calendar.attendance_ids[:1].sequence = 99
            self.assertFalse(recompute.called)
            calendar.attendance_ids[:1].hour_to -= 1
            self.assertEqual(recompute.call_count, 1)

    def test_editing_the_company_schedule_keeps_another_full_time(self):
        company_calendar = self.env["resource.calendar"].create(
            {"name": "company", "tz": "UTC"}
        )
        self.env.company.resource_calendar_id = company_calendar
        other = self.env["resource.calendar"].create({"name": "other", "tz": "UTC"})
        other.full_time_required_hours = 38
        company_calendar.attendance_ids[:1].unlink()
        self.env.flush_all()
        self.assertEqual(other.full_time_required_hours, 38)

    def test_hours_per_day_follow_a_line_moved_to_another_day(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "two days",
                "tz": "UTC",
                "attendance_ids": [Command.clear()]
                + [
                    Command.create(
                        {"name": "mon", "dayofweek": "0", "hour_from": 8, "hour_to": 12}
                    ),
                    Command.create(
                        {
                            "name": "tue",
                            "dayofweek": "1",
                            "hour_from": 13,
                            "hour_to": 17,
                        }
                    ),
                ],
            }
        )
        self.assertEqual(calendar.hours_per_day, 4)
        calendar.attendance_ids.filtered(lambda a: a.dayofweek == "1").dayofweek = "0"
        self.assertEqual(calendar.hours_per_day, 8)

    def test_a_copy_keeps_the_name_it_is_given(self):
        calendar = self.env["resource.calendar"].create({"name": "A", "tz": "UTC"})
        self.assertEqual(calendar.copy({"name": "B"}).name, "B")
        self.assertEqual(calendar.copy().name, "A (copy)")

    def test_the_fully_flexible_schedule_reads_days_in_the_readers_zone(self):
        flexible = self.env.ref("base.resource_calendar_fully_flexible")
        data = flexible.with_context(tz="America/Mexico_City").get_work_duration_data(
            datetime(2026, 10, 5, 6, tzinfo=UTC), datetime(2026, 10, 6, 6, tzinfo=UTC)
        )
        self.assertEqual(
            data,
            {"days": 1.0, "hours": 24.0},
            "one Mexico City day, held around the clock; read in UTC days it is "
            "18 hours of one and 6 of the next",
        )
