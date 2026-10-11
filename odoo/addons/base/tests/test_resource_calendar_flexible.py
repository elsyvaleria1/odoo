from datetime import date, datetime, timedelta
from unittest.mock import patch

from odoo.libs.datetime import timezone
from odoo.tests import TransactionCase, tagged

from .common import ResourceCase

UTC = timezone("UTC")


class TestFlexibleResourceCalendar(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.flex_calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible 40h/week",
                "tz": "UTC",
                "hours_per_day": 8.0,
                "schedule_type": "flexible",
            }
        )

        cls.fully_flex_resource, cls.flex_resource = cls.env[
            "resource.resource"
        ].create(
            [
                {
                    "name": "Wade Wilson",
                    "calendar_id": False,
                    "tz": "UTC",
                },
                {
                    "name": "Wade Wilson",
                    "calendar_id": cls.flex_calendar.id,
                    "tz": "UTC",
                },
            ]
        )

        cls.env["resource.schedule.exception"].create(
            [
                {
                    "resource_id": cls.flex_resource.id,
                    "date_from": datetime(2025, 7, 29, 8),
                    "date_to": datetime(2025, 7, 29, 17),
                },
                {
                    "resource_id": cls.flex_resource.id,
                    "date_from": datetime(2025, 7, 31, 8),
                    "date_to": datetime(2025, 8, 1, 17),
                },
                {
                    "resource_id": cls.fully_flex_resource.id,
                    "date_from": datetime(2025, 7, 29, 8),
                    "date_to": datetime(2025, 7, 29, 17),
                },
                {
                    "resource_id": cls.fully_flex_resource.id,
                    "date_from": datetime(2025, 7, 31, 8),
                    "date_to": datetime(2025, 8, 1, 17),
                },
                {
                    "calendar_id": cls.flex_calendar.id,
                    "date_from": datetime(2025, 8, 4, 8),
                    "date_to": datetime(2025, 8, 4, 17),
                },
                {
                    "calendar_id": False,
                    "date_from": datetime(2025, 8, 5, 8),
                    "date_to": datetime(2025, 8, 5, 17),
                },
            ]
        )

        cls.resources = cls.flex_resource | cls.fully_flex_resource

    def test_flexible_resource_work_intervals(self):
        start_dt = datetime(2025, 7, 28).astimezone(UTC)
        end_dt = datetime(2025, 8, 3, 17, 0).astimezone(UTC)

        work_intervals, hours_per_day, hours_per_week = (
            self.resources._get_flexible_resource_valid_work_intervals(start_dt, end_dt)
        )

        self.maxDiff = None
        for resource in self.resources:
            self.assertEqual(
                work_intervals[resource.id]._items,
                [
                    (
                        datetime(2025, 7, 28, 0, 0, tzinfo=UTC),
                        datetime(2025, 7, 29, tzinfo=UTC),
                        self.env["resource.calendar.attendance"],
                    ),
                    (
                        datetime(2025, 7, 30, 0, 0, tzinfo=UTC),
                        datetime(2025, 7, 31, tzinfo=UTC),
                        self.env["resource.calendar.attendance"],
                    ),
                    (
                        datetime(2025, 8, 2, 0, 0, tzinfo=UTC),
                        datetime(2025, 8, 3, 17, tzinfo=UTC),
                        self.env["resource.calendar.attendance"],
                    ),
                ],
                "resource not available on 29, 31 and 01, for other days, resource can do his hours at any moment of the day (from 00:00 to the next midnight)",
            )

        self.assertDictEqual(
            hours_per_day[self.flex_resource.id],
            {
                date(2025, 7, 28): 8.0,
                date(2025, 7, 29): 0.0,
                date(2025, 7, 30): 8.0,
                date(2025, 7, 31): 0.0,
                date(2025, 8, 1): 0.0,
                date(2025, 8, 2): 8.0,
                date(2025, 8, 3): 8.0,
            },
            "0 hours when the resource is not available, hours_per_day from the calendar for working days",
        )
        self.assertDictEqual(
            hours_per_week[self.flex_resource.id],
            {date(2025, 7, 28): 16.0},
            "40h weekly budget minus the 24h of time off inside the week",
        )

        self.assertTrue(
            self.fully_flex_resource.id not in hours_per_day
            and self.fully_flex_resource not in hours_per_week,
            "no daily and weekly limit",
        )

        start_dt = datetime(2025, 8, 4).astimezone(UTC)
        end_dt = datetime(2025, 8, 5, 17, 0).astimezone(UTC)

        work_intervals, hours_per_day, hours_per_week = (
            self.resources._get_flexible_resource_valid_work_intervals(start_dt, end_dt)
        )

        self.assertEqual(
            work_intervals[self.flex_resource.id]._items,
            [],
            "flex calendar have a public holidays on day 4, and there's a public holiday on day 5 for all calendars",
        )

        self.assertEqual(
            work_intervals[self.fully_flex_resource.id]._items,
            [
                (
                    datetime(2025, 8, 4, 0, 0, tzinfo=UTC),
                    datetime(2025, 8, 5, tzinfo=UTC),
                    self.env["resource.calendar.attendance"],
                ),
            ],
            "fully flex resource doesn't have a calendar, he should not follow the flex calendar public holiday, he follows holidays without a calendar",
        )

    def test_hours_per_week_for_different_years(self):
        start_dt = datetime(2025, 12, 26).astimezone(UTC)
        end_dt = datetime(2026, 1, 1, 17).astimezone(UTC)

        _, _, hours_per_week = (
            self.resources._get_flexible_resource_valid_work_intervals(start_dt, end_dt)
        )
        self.assertDictEqual(
            hours_per_week[self.flex_resource.id],
            {
                date(2025, 12, 22): 40.0,
                date(2025, 12, 29): 40.0,
            },
            "a week is keyed by its first day, across a new year too",
        )


@tagged("post_install", "-at_install")
class TestFlexibleCalendarUnusualDays(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible 35h",
                "tz": "UTC",
                "schedule_type": "flexible",
            }
        )

    def test_unusual_days_no_leaves(self):
        start = datetime(2025, 1, 6, 0, 0).replace(tzinfo=UTC)
        end = datetime(2025, 1, 10, 23, 59).replace(tzinfo=UTC)
        result = self.calendar._get_unusual_days(start, end)
        self.assertTrue(all(not v for v in result.values()))

    def test_unusual_days_with_leave(self):
        self.env["resource.schedule.exception"].create(
            {
                "name": "Holiday",
                "calendar_id": self.calendar.id,
                "date_from": datetime(2025, 1, 8, 0, 0),
                "date_to": datetime(2025, 1, 8, 23, 59),
            }
        )
        start = datetime(2025, 1, 6, 0, 0).replace(tzinfo=UTC)
        end = datetime(2025, 1, 10, 23, 59).replace(tzinfo=UTC)
        result = self.calendar._get_unusual_days(start, end)
        self.assertTrue(result.get("2025-01-08", False))
        self.assertFalse(result.get("2025-01-06", True))


@tagged("post_install", "-at_install")
class TestFlexibleWeeklyBudgetFallback(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible 3h/day, 21h/week",
                "tz": "UTC",
                "schedule_type": "flexible",
                "full_time_required_hours": 21,
                "hours_per_day": 3,
            }
        )

    def test_flexible_weekly_budget_falls_back_to_ftrh(self):
        self.assertEqual(self.calendar.hours_per_week, 0.0)
        self.assertEqual(self.calendar._get_flexible_hours_per_week(), 21.0)

    def test_flexible_intervals_generated_without_hours_per_week(self):
        start = datetime(2025, 9, 1, 0, 0).replace(tzinfo=UTC)
        end = datetime(2025, 9, 14, 23, 59).replace(tzinfo=UTC)
        intervals = list(self.calendar._attendance_intervals_batch(start, end)[False])
        self.assertEqual(len(intervals), 14, "every day must get a work block")
        for interval_start, interval_end, _meta in intervals:
            hours = (interval_end - interval_start).total_seconds() / 3600
            self.assertAlmostEqual(hours, 3.0, places=6)

    def test_explicit_hours_per_week_takes_precedence(self):
        self.calendar.hours_per_week = 10.0
        self.assertEqual(self.calendar._get_flexible_hours_per_week(), 10.0)


class TestFlexibleAttendanceSynthesis(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible 40h",
                "schedule_type": "flexible",
                "hours_per_week": 40,
                "hours_per_day": 8,
                "tz": "UTC",
            }
        )

    def _hours(self, start, end):
        return self.calendar.get_work_hours_count(
            start.replace(tzinfo=UTC), end.replace(tzinfo=UTC), compute_leaves=False
        )

    def test_seven_day_window_yields_the_weekly_budget(self):
        for offset in range(7):
            start = datetime(2025, 3, 3) + timedelta(days=offset)
            with self.subTest(start=start.date()):
                self.assertAlmostEqual(
                    self._hours(start, start + timedelta(days=7)), 40.0, places=2
                )

    def test_a_week_fills_from_its_first_day(self):
        tuesday, sunday = datetime(2025, 3, 4), datetime(2025, 3, 9)
        self.assertAlmostEqual(
            self._hours(tuesday, sunday),
            32.0,
            places=2,
            msg="Monday's eight hours are Monday's, whether or not it is read",
        )

    def test_splitting_a_window_keeps_its_total(self):
        monday, thursday = datetime(2025, 3, 3), datetime(2025, 3, 6)
        wednesday = datetime(2025, 3, 12)
        whole = self._hours(monday, wednesday)
        parts = self._hours(monday, thursday) + self._hours(thursday, wednesday)
        self.assertAlmostEqual(whole, 56.0, places=2)
        self.assertAlmostEqual(parts, whole, places=2)

    def test_the_week_starts_on_the_companys_day(self):
        saturday, next_saturday = datetime(2025, 3, 8), datetime(2025, 3, 15)
        self.assertAlmostEqual(self._hours(saturday, next_saturday), 40.0, places=2)
        self.env.company.resource_week_start = "5"
        self.assertAlmostEqual(
            self._hours(saturday, saturday + timedelta(days=2)),
            16.0,
            places=2,
            msg="a week starting on Saturday puts its first hours on the weekend",
        )

    def test_a_leave_day_takes_its_hours_from_the_week_once(self):
        resource = self.env["resource.resource"].create(
            {"name": "Flexible worker", "calendar_id": self.calendar.id, "tz": "UTC"}
        )
        monday = datetime(2025, 3, 3)
        for name in ("Sick", "Also recorded"):
            self.env["resource.schedule.exception"].create(
                {
                    "name": name,
                    "resource_id": resource.id,
                    "calendar_id": self.calendar.id,
                    "date_from": monday,
                    "date_to": monday + timedelta(days=1),
                }
            )
        work = self.calendar._work_intervals_batch(
            monday.replace(tzinfo=UTC),
            (monday + timedelta(days=7)).replace(tzinfo=UTC),
            resources=resource,
        )[resource.id]
        self.assertAlmostEqual(
            sum((stop - start).total_seconds() for start, stop, _m in work) / 3600,
            32.0,
            places=2,
            msg="two records of one sick Monday cost the week eight hours, not 16",
        )

    def test_dst_transition_keeps_one_block_per_day(self):
        brussels = timezone("Europe/Brussels")
        calendar = self.env["resource.calendar"].create(
            {
                "name": "Flexible Brussels",
                "schedule_type": "flexible",
                "hours_per_week": 40,
                "hours_per_day": 8,
                "tz": "Europe/Brussels",
            }
        )
        start = datetime(2025, 3, 24).replace(tzinfo=brussels)
        end = datetime(2025, 4, 7).replace(tzinfo=brussels)
        intervals = calendar._get_flexible_intervals(start, end, brussels)
        days = [interval[0].date() for interval in intervals]
        self.assertEqual(
            len(days), len(set(days)), "a day was allocated twice across the DST switch"
        )


class TestFlexibleWeekKeyIsDeterministic(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible 40h",
                "schedule_type": "flexible",
                "hours_per_week": 40,
                "hours_per_day": 8,
                "tz": "UTC",
            }
        )
        cls.resource = cls.env["resource.resource"].create(
            {"name": "Flexible worker", "calendar_id": cls.calendar.id, "tz": "UTC"}
        )
        cls.lang = cls.env["res.lang"].search(
            [("code", "=", cls.env.user.lang or "en_US")], limit=1
        )

    def _allocated_hours_with_week_start(self, week_start):
        self.lang.week_start = week_start
        self.env.invalidate_all()
        return (
            self.env["resource.reservation"]
            .create(
                {
                    "name": f"booking-{week_start}",
                    "resource_id": self.resource.copy().id,
                    "date_start": datetime(2025, 3, 3),
                    "date_end": datetime(2025, 3, 10),
                }
            )
            .allocated_hours
        )

    def test_allocated_hours_ignores_week_start(self):
        sunday_start = self._allocated_hours_with_week_start("7")
        monday_start = self._allocated_hours_with_week_start("1")
        self.assertEqual(
            sunday_start,
            monday_start,
            "allocated_hours must not depend on res.lang.week_start",
        )

    def test_the_week_is_the_companys_not_the_languages(self):
        sunday = date(2025, 3, 9)
        self.assertEqual(self.resource._get_week_of(sunday), date(2025, 3, 3))
        self.assertEqual(
            self.resource._get_week_of(sunday + timedelta(days=1)),
            sunday + timedelta(days=1),
        )
        for week_start in ("1", "7"):
            self.lang.week_start = week_start
            self.env.invalidate_all()
            with self.subTest(week_start=week_start):
                self.assertEqual(self.resource._get_week_of(sunday), date(2025, 3, 3))
        self.resource.company_id.resource_week_start = "6"
        self.assertEqual(self.resource._get_week_of(sunday), sunday)

    def test_valid_work_intervals_budget_ignores_week_start(self):
        start, end = (
            datetime(2025, 3, 3).replace(tzinfo=UTC),
            datetime(2025, 3, 10).replace(tzinfo=UTC),
        )
        results = []
        for week_start in ("7", "1"):
            self.lang.week_start = week_start
            self.env.invalidate_all()
            intervals, per_day, per_week = (
                self.resource._get_flexible_resource_valid_work_intervals(start, end)
            )
            results.append(
                self.resource._get_flexible_resource_work_hours(
                    intervals[self.resource.id],
                    per_day[self.resource.id],
                    per_week[self.resource.id],
                )
            )
        self.assertEqual(results[0], results[1])


@tagged("post_install", "-at_install")
class TestAFlexibleScheduleIsNeverSilentlyEmpty(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Calendar = cls.env["resource.calendar"]
        cls.start = datetime(2026, 6, 1, tzinfo=UTC)
        cls.stop = datetime(2026, 6, 8, tzinfo=UTC)

    def test_created_flexible_with_a_weekly_total_yields_that_total(self):
        calendar = self.Calendar.create(
            {"name": "Consultants", "schedule_type": "flexible", "hours_per_week": 40}
        )
        self.env.flush_all()
        self.assertEqual(calendar.schedule_type, "flexible")
        self.assertGreater(
            calendar.get_work_hours_count(self.start, self.stop),
            0.0,
            "a flexible schedule declaring 40 hours a week allocated none, because"
            " hours_per_day was never computed and gates the weekly budget",
        )

    def test_clearing_the_daily_average_does_not_empty_the_schedule(self):
        calendar = self.Calendar.create({"name": "Consultants 2"})
        self.env.flush_all()
        calendar.write({"schedule_type": "flexible", "hours_per_day": 0.0})
        self.env.flush_all()
        self.assertGreater(
            calendar.get_work_hours_count(self.start, self.stop),
            0.0,
            "clearing the editable, non-required Avg field emptied the schedule",
        )


@tagged("post_install", "-at_install")
class TestReservationsShareTheWeeklyBudget(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible 40h",
                "schedule_type": "flexible",
                "hours_per_week": 40,
                "hours_per_day": 8,
                "tz": "UTC",
            }
        )
        cls.resource = cls.env["resource.resource"].create(
            {"name": "Flexy", "calendar_id": cls.calendar.id, "tz": "UTC"}
        )
        cls.monday = datetime(2026, 6, 1)
        cls.wednesday = datetime(2026, 6, 3)

    def _book(self, start, stop, **values):
        return self.env["resource.reservation"].create(
            {
                "name": "Booking",
                "resource_id": self.resource.id,
                "date_start": start,
                "date_end": stop,
                **values,
            }
        )

    def _hours(self, *reservations):
        self.env.flush_all()
        return [reservation.allocated_hours for reservation in reservations]

    def test_a_lone_booking_takes_the_week_from_its_start(self):
        booking = self._book(self.wednesday, self.wednesday + timedelta(days=7))
        self.assertEqual(self._hours(booking), [56.0])

    def test_a_saturday_in_an_empty_week_holds_a_day(self):
        saturday = self.monday + timedelta(days=5)
        booking = self._book(saturday, saturday + timedelta(days=1))
        self.assertEqual(self._hours(booking), [8.0])

    def test_an_earlier_booking_is_served_first(self):
        first = self._book(self.monday, self.wednesday)
        later = self._book(self.wednesday, self.wednesday + timedelta(days=7))
        self.assertEqual(self._hours(first, later), [16.0, 40.0])

    def test_the_order_is_the_dates_not_the_creation(self):
        later = self._book(self.wednesday, self.wednesday + timedelta(days=7))
        self.assertEqual(self._hours(later), [56.0])
        first = self._book(self.monday, self.wednesday)
        self.assertEqual(self._hours(first, later), [16.0, 40.0])

    def test_one_batch_reads_as_its_parts(self):
        Reservation = self.env["resource.reservation"]
        first, later = Reservation.create(
            [
                {
                    "name": "Later",
                    "resource_id": self.resource.id,
                    "date_start": self.wednesday,
                    "date_end": self.wednesday + timedelta(days=7),
                },
                {
                    "name": "First",
                    "resource_id": self.resource.id,
                    "date_start": self.monday,
                    "date_end": self.wednesday,
                },
            ]
        )[::-1]
        self.assertEqual(self._hours(first, later), [16.0, 40.0])

    def test_a_partial_booking_draws_its_share(self):
        first = self._book(self.monday, self.wednesday, allocated_percentage=50)
        later = self._book(self.wednesday, self.wednesday + timedelta(days=7))
        self.assertEqual(self._hours(first, later), [8.0, 48.0])

    def test_parallel_shares_split_the_week(self):
        friday = self.monday + timedelta(days=5)
        first = self._book(self.monday, friday, allocated_percentage=50)
        second = self._book(self.monday, friday, allocated_percentage=50)
        self.assertEqual(self._hours(first, second), [20.0, 20.0])

    def test_a_share_is_of_each_week_not_of_each_day(self):
        booking = self._book(
            self.monday, self.monday + timedelta(days=12), allocated_percentage=50
        )
        self.assertEqual(self._hours(booking), [40.0])

    def test_a_released_booking_gives_its_hours_back(self):
        first = self._book(self.monday, self.wednesday)
        later = self._book(self.wednesday, self.wednesday + timedelta(days=7))
        first.active = False
        self.assertEqual(self._hours(later), [56.0])
        first.active = True
        self.assertEqual(self._hours(later), [40.0])
        first.unlink()
        self.assertEqual(self._hours(later), [56.0])

    def test_moving_a_booking_moves_the_budget(self):
        first = self._book(self.monday, self.wednesday)
        later = self._book(self.wednesday, self.wednesday + timedelta(days=7))
        first.write(
            {
                "date_start": self.monday + timedelta(days=14),
                "date_end": self.wednesday + timedelta(days=14),
            }
        )
        self.assertEqual(self._hours(first, later), [16.0, 56.0])

    def test_the_hours_never_exceed_the_schedule(self):
        bookings = [
            self._book(
                self.monday + timedelta(days=day), self.monday + timedelta(days=day + 1)
            )
            for day in range(7)
        ]
        self.assertEqual(sum(self._hours(*bookings)), 40.0)

    def test_a_fixed_schedule_reads_its_lines(self):
        fixed = self.env["resource.calendar"].create({"name": "Fixed", "tz": "UTC"})
        self.resource.calendar_id = fixed
        stop = self.wednesday + timedelta(days=7)
        booking = self._book(self.wednesday, stop)
        self.assertAlmostEqual(
            self._hours(booking)[0],
            fixed.get_work_hours_count(
                self.wednesday.replace(tzinfo=UTC), stop.replace(tzinfo=UTC)
            ),
            places=2,
        )


class TestFullyFlexibleDays(ResourceCase):
    def test_fully_flexible_five_days_counts_five_days(self):
        resource = self._resource(name="Fully flexible", calendar_id=False)
        data = resource.calendar_id._get_duration_data(
            resource.calendar_id._attendance_intervals_batch(
                datetime(2026, 3, 2, 8, 0).replace(tzinfo=UTC),
                datetime(2026, 3, 6, 17, 0).replace(tzinfo=UTC),
                resource,
            )[resource.id]
        )
        self.assertEqual(
            data["days"],
            5.0,
            "a fully flexible resource absent Mon-Fri is absent five days, not"
            " the wall-clock fraction 4.375",
        )

    def test_fully_flexible_availability_is_unchanged(self):
        resource = self._resource(name="Still free", calendar_id=False)
        start = datetime(2026, 3, 2, 0, 0).replace(tzinfo=UTC)
        end = datetime(2026, 3, 7, 0, 0).replace(tzinfo=UTC)
        intervals = resource.calendar_id._attendance_intervals_batch(
            start, end, resource
        )[resource.id]
        covered = sum(
            (stop - begin).total_seconds() for begin, stop, _meta in intervals
        )
        self.assertEqual(
            covered,
            (end - start).total_seconds(),
            "every instant of the window must still be available",
        )

    def test_fully_flexible_partial_day_is_a_fraction_of_a_working_day(self):
        resource = self._resource(name="Part day", calendar_id=False)
        data = resource.calendar_id._get_duration_data(
            resource.calendar_id._attendance_intervals_batch(
                datetime(2026, 3, 2, 9, 0).replace(tzinfo=UTC),
                datetime(2026, 3, 2, 13, 0).replace(tzinfo=UTC),
                resource,
            )[resource.id]
        )
        self.assertEqual(data["days"], 0.5)

    def test_fully_flexible_long_day_is_capped_at_one_day(self):
        resource = self._resource(name="Long day", calendar_id=False)
        data = resource.calendar_id._get_duration_data(
            resource.calendar_id._attendance_intervals_batch(
                datetime(2026, 3, 2, 8, 0).replace(tzinfo=UTC),
                datetime(2026, 3, 3, 0, 0).replace(tzinfo=UTC),
                resource,
            )[resource.id]
        )
        self.assertEqual(data["days"], 1.0)

    def test_fully_flexible_day_count_survives_dst(self):
        resource = self._resource(name="DST", calendar_id=False, tz="Europe/Brussels")
        brussels = timezone("Europe/Brussels")
        start = datetime(2026, 3, 28, 0, 0).replace(tzinfo=brussels)
        end = datetime(2026, 3, 31, 0, 0).replace(tzinfo=brussels)
        data = resource.calendar_id._get_duration_data(
            resource.calendar_id._attendance_intervals_batch(start, end, resource)[
                resource.id
            ]
        )
        self.assertEqual(data["days"], 3.0)


class TestTheScheduleReadDecides(ResourceCase):
    def setUp(self):
        super().setUp()
        self.monday = datetime(2026, 3, 2, tzinfo=UTC)
        self.tuesday = self.monday + timedelta(days=1)

    def test_a_fixed_schedule_reads_a_fully_flexible_resource_by_its_hours(self):
        resource = self._resource(name="Anytime", calendar_id=False)
        own = resource.calendar_id._unavailable_intervals_batch(
            self.monday, self.tuesday, resource
        )[resource.id]
        imposed = self.calendar._unavailable_intervals_batch(
            self.monday, self.tuesday, resource
        )[resource.id]
        self.assertFalse(own)
        self.assertIn((self.monday, self.monday.replace(hour=8)), imposed)

    def test_a_flexible_schedule_widens_a_part_day_absence(self):
        resource = self._resource(name="Fixed hours")
        self.env["resource.schedule.exception"].create(
            {
                "name": "Two hours",
                "resource_id": resource.id,
                "date_from": datetime(2026, 3, 2, 9, 0),
                "date_to": datetime(2026, 3, 2, 11, 0),
            }
        )
        flexible = self.env["resource.calendar"].create(
            {"name": "Flexible", "schedule_type": "flexible", "tz": "UTC"}
        )

        def absence(calendar):
            return [
                (start.astimezone(UTC), stop.astimezone(UTC))
                for start, stop, _leave in calendar._leave_intervals_batch(
                    self.monday, self.tuesday, resource
                )[resource.id]
            ]

        self.assertEqual(
            absence(self.calendar),
            [(self.monday.replace(hour=9), self.monday.replace(hour=11))],
        )
        self.assertEqual(absence(flexible)[0][0], self.monday)


class TestFlexibleHoursFollowTheWindow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible 40h",
                "schedule_type": "flexible",
                "hours_per_week": 40,
                "hours_per_day": 8,
                "tz": "UTC",
            }
        )
        cls.resource = cls.env["resource.resource"].create(
            {
                "name": "Flexy",
                "type": "material",
                "calendar_id": cls.calendar.id,
                "tz": "UTC",
            }
        )
        cls.monday = datetime(2026, 6, 1, tzinfo=UTC)

    def test_an_evening_counts_as_the_resource_reads_it(self):
        start, stop = (
            self.monday + timedelta(hours=18),
            self.monday + timedelta(hours=22),
        )
        self.assertEqual(
            self.calendar.get_work_hours_count(start, stop, compute_leaves=False), 4.0
        )
        schedule = self.resource._get_work_schedule(start, stop)
        self.assertEqual(schedule.work_hours(self.resource), 4.0)

    def test_a_plan_starts_where_it_is_asked_to(self):
        self.assertEqual(
            self.calendar.plan_hours(
                4,
                (self.monday + timedelta(hours=18)).replace(tzinfo=None),
                compute_leaves=False,
            ),
            (self.monday + timedelta(hours=22)).replace(tzinfo=None),
        )

    def test_a_whole_day_is_still_drawn_around_noon(self):
        blocks = self.calendar._attendance_intervals_batch(
            self.monday, self.monday + timedelta(days=1)
        )[False]
        self.assertEqual(
            [(start.hour, stop.hour) for start, stop, _meta in blocks], [(8, 16)]
        )

    def test_a_cut_day_holds_no_more_than_its_hours(self):
        start = self.monday + timedelta(hours=2)
        self.assertEqual(
            self.calendar.get_work_hours_count(
                start, self.monday + timedelta(days=1), compute_leaves=False
            ),
            8.0,
        )


@tagged("post_install", "-at_install")
class TestPlanningDoesNotDependOnTheSearchWindow(TransactionCase):
    def test_flexible_planning_matches_one_unsplit_window(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "Flexible plan",
                "tz": "Europe/Brussels",
                "schedule_type": "flexible",
                "full_time_required_hours": 40,
                "hours_per_day": 8,
            }
        )
        start = datetime(2026, 11, 2, 10, 0, tzinfo=timezone("Europe/Brussels"))
        hours = (8, 40, 88, 90, 150, -30, -90)
        planned = [calendar.plan_hours(h, start) for h in hours]
        with patch(
            "odoo.addons.base.models.resource_calendar._PLAN_WINDOW",
            timedelta(days=400),
        ):
            unsplit = [calendar.plan_hours(h, start) for h in hours]
        self.assertEqual(planned, unsplit)
