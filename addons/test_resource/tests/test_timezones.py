from datetime import UTC, date, datetime

from freezegun import freeze_time

from odoo.addons.test_resource.tests.common import TestResourceCommon


class TestTimezones(TestResourceCommon):
    def setUp(self):
        super().setUp()

        self.tz1 = "Etc/GMT+6"
        self.tz2 = "Europe/Brussels"
        self.tz3 = "Etc/GMT-10"
        self.tz4 = "Etc/GMT+10"

    def test_work_hours_count(self):
        count = self.calendar_jean.get_work_hours_count(
            self.datetime_tz(2018, 4, 10, 8, 0, 0),
            self.datetime_tz(2018, 4, 10, 12, 0, 0),
        )
        self.assertEqual(count, 4)

        count = self.calendar_jean.get_work_hours_count(
            self.datetime_tz(2018, 4, 10, 8, 0, 0, tzinfo=self.tz1),
            self.datetime_tz(2018, 4, 10, 12, 0, 0, tzinfo=self.tz1),
        )
        self.assertEqual(count, 0)

        count = self.calendar_jean.get_work_hours_count(
            self.datetime_tz(2018, 4, 10, 8, 0, 0, tzinfo=self.tz2),
            self.datetime_tz(2018, 4, 10, 12, 0, 0, tzinfo=self.tz3),
        )
        self.assertEqual(count, 0)

        count = self.calendar_jean.get_work_hours_count(
            self.datetime_tz(2018, 4, 10, 8, 0, 0, tzinfo=self.tz2),
            self.datetime_tz(2018, 4, 10, 12, 0, 0, tzinfo=self.tz4),
        )
        self.assertEqual(count, 8)

    def test_plan_hours(self):
        dt = self.calendar_jean.plan_hours(10, self.datetime_tz(2018, 4, 10, 8, 0, 0))
        self.assertEqual(dt, self.datetime_tz(2018, 4, 11, 10, 0, 0))

        dt = self.calendar_jean.plan_hours(
            10, self.datetime_tz(2018, 4, 10, 8, 0, 0, tzinfo=self.tz4)
        )
        self.assertEqual(dt, self.datetime_tz(2018, 4, 11, 22, 0, 0, tzinfo=self.tz4))

    def test_plan_days(self):
        dt = self.calendar_jean.plan_days(2, self.datetime_tz(2018, 4, 10, 8, 0, 0))
        self.assertEqual(dt, self.datetime_tz(2018, 4, 11, 14, 0, 0))

        dt = self.calendar_jean.plan_days(
            2, self.datetime_tz(2018, 4, 10, 8, 0, 0, tzinfo=self.tz4)
        )
        self.assertEqual(dt, self.datetime_tz(2018, 4, 12, 4, 0, 0, tzinfo=self.tz4))

    def test_work_data(self):
        data = self.jean._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 9, 8, 0, 0),
            self.datetime_tz(2018, 4, 13, 16, 0, 0),
        )[self.jean.id]
        self.assertEqual(data, {"days": 4.75, "hours": 38})

        data = self.jean._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz3),
            self.datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz3),
        )[self.jean.id]
        self.assertEqual(data, {"days": 4, "hours": 32})

        data = self.jean._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz2),
            self.datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz4),
        )[self.jean.id]
        self.assertEqual(data, {"days": 5, "hours": 40})

        data = self.jules._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jules.tz),
            self.datetime_tz(2018, 4, 6, 23, 59, 59, tzinfo=self.jules.tz),
        )[self.jules.id]
        self.assertEqual(data, {"days": 4, "hours": 30})

        data = self.jules._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jules.tz),
            self.datetime_tz(2018, 4, 14, 23, 59, 59, tzinfo=self.jules.tz),
        )[self.jules.id]
        self.assertEqual(data, {"days": 6, "hours": 46})

        data = self.jules._get_work_duration_data_batch(
            self.datetime_tz(2014, 12, 29, 0, 0, 0, tzinfo=self.jules.tz),
            self.datetime_tz(2019, 12, 27, 23, 59, 59, tzinfo=self.jules.tz),
        )[self.jules.id]
        self.assertEqual(data, {"days": 784, "hours": 6010})

    def test_leave_data(self):
        self.env["resource.schedule.exception"].create(
            {
                "name": "",
                "calendar_id": self.jean.resource_calendar_id.id,
                "resource_id": self.jean.resource_id.id,
                "date_from": self.datetime_str(2018, 4, 9, 8, 0, 0, tzinfo=self.tz2),
                "date_to": self.datetime_str(2018, 4, 9, 14, 0, 0, tzinfo=self.tz2),
            }
        )

        data = self.jean._get_leave_duration_data_batch(
            self.datetime_tz(2018, 4, 9, 8, 0, 0),
            self.datetime_tz(2018, 4, 13, 16, 0, 0),
        )[self.jean.id]
        self.assertEqual(data, {"days": 0.5, "hours": 4})

        data = self.jean._get_leave_duration_data_batch(
            self.datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz3),
            self.datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz3),
        )[self.jean.id]
        self.assertEqual(data, {"days": 0.75, "hours": 6})

        data = self.jean._get_leave_duration_data_batch(
            self.datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz2),
            self.datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz4),
        )[self.jean.id]
        self.assertEqual(data, {"days": 0.75, "hours": 6})

    def test_works(self):
        work = self.jean._get_work_time_per_day(
            self.datetime_tz(2018, 4, 9, 8, 0, 0),
            self.datetime_tz(2018, 4, 13, 16, 0, 0),
        )[self.jean.id]
        self.assertEqual(
            work,
            [
                (date(2018, 4, 9), 6),
                (date(2018, 4, 10), 8),
                (date(2018, 4, 11), 8),
                (date(2018, 4, 12), 8),
                (date(2018, 4, 13), 8),
            ],
        )

        work = self.jean._get_work_time_per_day(
            self.datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz3),
            self.datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz3),
        )[self.jean.id]
        self.assertEqual(len(work), 4)
        self.assertEqual(
            work,
            [
                (date(2018, 4, 9), 8),
                (date(2018, 4, 10), 8),
                (date(2018, 4, 11), 8),
                (date(2018, 4, 12), 8),
            ],
        )

        work = self.jean._get_work_time_per_day(
            self.datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz2),
            self.datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz4),
        )[self.jean.id]
        self.assertEqual(
            work,
            [
                (date(2018, 4, 9), 8),
                (date(2018, 4, 10), 8),
                (date(2018, 4, 11), 8),
                (date(2018, 4, 12), 8),
                (date(2018, 4, 13), 8),
            ],
        )

    @freeze_time("2022-09-21 15:30:00", tz_offset=-10)
    def test_unavailable_intervals(self):
        resource = self.env["resource.resource"].create(
            {
                "name": "resource",
                "tz": self.tz3,
            }
        )
        intervals = resource._get_unavailable_intervals(
            datetime(2022, 9, 21), datetime(2022, 9, 22)
        )
        self.assertEqual(
            intervals[resource.id],
            [
                (
                    datetime(2022, 9, 21, 2, 0, tzinfo=UTC),
                    datetime(2022, 9, 21, 3, 0, tzinfo=UTC),
                ),
                (
                    datetime(2022, 9, 21, 7, 0, tzinfo=UTC),
                    datetime(2022, 9, 21, 22, 0, tzinfo=UTC),
                ),
            ],
        )

    @freeze_time("2022-09-21 15:30:00", tz_offset=-10)
    def test_unavailable_intervals_of_a_resource_without_a_zone(self):
        resource = self.env["resource.resource"].create({"name": "resource"})
        intervals = resource._get_unavailable_intervals(
            datetime(2022, 9, 21), datetime(2022, 9, 22)
        )
        self.assertEqual(
            intervals[resource.id],
            [
                (
                    datetime(2022, 9, 21, 0, 0, tzinfo=UTC),
                    datetime(2022, 9, 21, 6, 0, tzinfo=UTC),
                ),
                (
                    datetime(2022, 9, 21, 10, 0, tzinfo=UTC),
                    datetime(2022, 9, 21, 11, 0, tzinfo=UTC),
                ),
                (
                    datetime(2022, 9, 21, 15, 0, tzinfo=UTC),
                    datetime(2022, 9, 22, 0, 0, tzinfo=UTC),
                ),
            ],
        )

    def test_flexible_resource_leave_interval(self):

        flexible_calendar = self.env["resource.calendar"].create(
            {
                "name": "Flex Calendar",
                "tz": "UTC",
                "schedule_type": "flexible",
                "full_time_required_hours": 40,
                "hours_per_day": 8,
            }
        )
        flex_resource = self.env["resource.resource"].create(
            {
                "name": "Test FlexResource",
                "calendar_id": flexible_calendar.id,
            }
        )
        self.env["resource.schedule.exception"].create(
            {
                "name": "Standard Time Off",
                "calendar_id": flexible_calendar.id,
                "resource_id": flex_resource.id,
                "date_from": "2025-03-07 08:00:00",
                "date_to": "2025-03-07 17:00:00",
            }
        )

        start_dt = datetime(2025, 3, 7, 8, 0, 0, tzinfo=UTC)
        end_dt = datetime(2025, 3, 7, 16, 00, 00, 00, tzinfo=UTC)

        intervals = flexible_calendar._leave_intervals_batch(
            start_dt, end_dt, [flex_resource]
        )
        intervals_list = list(intervals[flex_resource.id])
        self.assertEqual(len(intervals_list), 1, "There should be one leave interval")
        interval = intervals_list[0]
        self.assertEqual(
            interval[0], start_dt, "The start of the interval should be 08:00:00"
        )
        self.assertEqual(
            interval[1], end_dt, "The end of the interval should be 16:00:00"
        )
