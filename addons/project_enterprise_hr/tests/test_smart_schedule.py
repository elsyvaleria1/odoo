from datetime import UTC, date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo.tests import freeze_time, tagged
from odoo.tools import float_compare

from .auto_shift_dates_hr_common import AutoShiftDatesHRCommon
from odoo.addons.project_gantt.tests.test_smart_schedule_common import (
    TestSmartScheduleCommon,
)


@tagged("-at_install", "post_install")
@freeze_time("2023-01-01")
class TestSmartSchedule(TestSmartScheduleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.flexible_calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flex Calendar 8h",
                "tz": "UTC",
                "full_time_required_hours": 40.0,
                "hours_per_day": 8.0,
                "schedule_type": "flexible",
            }
        )

    def test_multi_users_tasks(self):
        self.task_project_pigs_with_planned_hours_manager.write(
            {
                "user_ids": [self.user_projectmanager.id, self.user_projectuser.id],
                "predecessor_ids": [self.task_project_pigs_with_planned_hours_user.id],
                "successor_ids": [self.task_project_pigs_no_planned_hours_user.id],
                "date_end": datetime(2023, 2, 2),
                "planned_hours": 10.0,
            }
        )

        self.task_project_pigs_no_planned_hours_user.write(
            {
                "user_ids": [self.user_projectuser.id],
            }
        )

        self.env["hr.employee"].create(
            {
                "name": self.user_projectuser.name,
                "user_id": self.user_projectuser.id,
            }
        )
        self.user_projectmanager.action_create_employee()

        self.env["resource.schedule.exception"].create(
            [
                {
                    "name": "scheduled leave",
                    "date_from": datetime(2023, 1, 3, 0),
                    "date_to": datetime(2023, 1, 6, 23),
                    "resource_id": self.user_projectuser.employee_id.resource_id.id,
                },
                {
                    "name": "scheduled leave",
                    "date_from": datetime(2023, 1, 5, 0),
                    "date_to": datetime(2023, 1, 10, 23),
                    "resource_id": self.user_projectmanager.employee_id.resource_id.id,
                },
            ]
        )

        result = (
            (
                self.task_project_pigs_with_planned_hours_user
                + self.task_project_pigs_with_planned_hours_manager
                + self.task_project_pigs_no_planned_hours_user
                + self.task_project_goats_with_planned_hours_user
            )
            .with_context(
                {
                    "last_date_view": self.end_date_view_str,
                    "gantt_scale": "week",
                    "cell_part": 2.0,
                }
            )
            .schedule_tasks(
                {
                    "date_start": self.start_date_view_str,
                    "date_end": (self.start_date_view + relativedelta(day=1)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "user_ids": self.user_projectuser.ids,
                }
            )
        )
        self.assertDictEqual(result[0], {}, "No warnings should be displayed")

        self.assertEqual(
            self.task_project_pigs_with_planned_hours_user.date_start,
            datetime(2023, 1, 2, 7),
        )
        self.assertEqual(
            self.task_project_pigs_with_planned_hours_user.date_end,
            datetime(2023, 1, 2, 16),
        )

        self.assertEqual(
            self.task_project_pigs_with_planned_hours_manager.date_start,
            datetime(2023, 1, 11, 7),
        )
        self.assertEqual(
            self.task_project_pigs_with_planned_hours_manager.date_end,
            datetime(2023, 1, 11, 13),
            "10 hours to do / 2 users = 5 hours per user from 7h to 11h + 12h to 13h",
        )

        self.assertEqual(
            self.task_project_goats_with_planned_hours_user.date_start,
            datetime(2023, 1, 9, 7),
        )
        self.assertEqual(
            self.task_project_goats_with_planned_hours_user.date_end,
            datetime(2023, 1, 10, 9),
        )

        self.assertEqual(
            self.task_project_pigs_no_planned_hours_user.date_start,
            datetime(2023, 1, 11, 13),
        )
        self.assertEqual(
            self.task_project_pigs_no_planned_hours_user.date_end,
            datetime(2023, 1, 13, 8),
            "12h to plan, 3 hours day 11, 8 hours day 12, 1 hour day 13",
        )

    def test_auto_schedule_flex_resource(self):
        self.env.user.sudo().tz = "UTC"
        self.user_projectuser.company_id.resource_calendar_id.tz = "UTC"

        self.task_project_pigs_with_planned_hours_user.planned_hours = 36
        self.user_projectuser.action_create_employee()
        self.user_projectmanager.action_create_employee()
        self.user_projectuser.employee_id.write(
            {"resource_calendar_id": self.flexible_calendar.id}
        )
        (
            self.user_projectuser.employee_id.resource_id
            | self.user_projectmanager.employee_id.resource_id
        ).write({"tz": "UTC"})

        self.task_project_goats_with_planned_hours_user.write(
            {
                "user_ids": [self.user_projectuser.id],
                "predecessor_ids": [self.task_project_pigs_with_planned_hours_user.id],
                "successor_ids": [self.task_project_pigs_no_planned_hours_user.id],
                "planned_hours": 12,
            }
        )

        self.task_project_pigs_no_planned_hours_no_user.write(
            {"user_ids": [self.user_projectuser.id], "planned_hours": 12}
        )
        self.task_project_pigs_no_planned_hours_user.write(
            {
                "user_ids": [self.user_projectuser.id, self.user_projectmanager.id],
                "successor_ids": [self.task_project_pigs_no_planned_hours_no_user.id],
                "planned_hours": 8,
            }
        )

        result = (
            (
                self.task_project_pigs_with_planned_hours_user
                | self.task_project_goats_with_planned_hours_user
                | self.task_project_pigs_no_planned_hours_user
                | self.task_project_pigs_no_planned_hours_no_user
            )
            .with_context(
                {
                    "last_date_view": self.end_date_view_str,
                    "gantt_scale": "week",
                    "cell_part": 2.0,
                }
            )
            .schedule_tasks(
                {
                    "date_start": self.start_date_view_str,
                    "date_end": (self.start_date_view + relativedelta(day=1)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "user_ids": self.user_projectuser.ids,
                }
            )
        )
        self.assertDictEqual(result[0], {}, "No warnings should be displayed")

        self.assertEqual(
            self.task_project_pigs_with_planned_hours_user.date_start,
            datetime(2023, 1, 1, 0),
            "day 1: 8h, day 2: 8h, day 3: 8h, day 4: 8h, day 5: 4h",
        )
        self.assertEqual(
            self.task_project_pigs_with_planned_hours_user.date_end,
            datetime(2023, 1, 5, 4),
            "4 hours left to work on other tasks",
        )

        self.assertEqual(
            self.task_project_goats_with_planned_hours_user.date_start,
            datetime(2023, 1, 5, 4),
            "4 hours to work from 04:00 to 08:00",
        )
        self.assertEqual(
            self.task_project_goats_with_planned_hours_user.date_end,
            datetime(2023, 1, 6, 8),
            "8h left in the week of Mon 2 are used on day 6",
        )

        self.assertEqual(
            self.task_project_pigs_no_planned_hours_user.date_start,
            datetime(2023, 1, 9, 8),
            "8 hours to do, 4 hours each user on day 9 from 08:00 to 12:00 (start from 08:00 instead of 00:00 as a regular resource is part of it)",
        )
        self.assertEqual(
            self.task_project_pigs_no_planned_hours_user.date_end,
            datetime(2023, 1, 9, 12),
        )

        self.assertEqual(
            self.task_project_pigs_no_planned_hours_no_user.date_start,
            datetime(2023, 1, 9, 12),
            "4 hours on day 9",
        )
        self.assertEqual(
            self.task_project_pigs_no_planned_hours_no_user.date_end,
            datetime(2023, 1, 10, 8),
            "8 hours on day 10",
        )

    def test_flexible_user_no_day_no_week_overload(self):
        self.env.user.sudo().tz = "UTC"
        self.user_projectuser.company_id.resource_calendar_id.tz = "UTC"

        self.user_projectuser.action_create_employee()
        self.user_projectmanager.action_create_employee()
        self.user_projectuser.employee_id.write(
            {"resource_calendar_id": self.flexible_calendar.id, "tz": "UTC"}
        )
        (
            self.user_projectuser.employee_id.resource_id
            | self.user_projectmanager.employee_id.resource_id
        ).write({"tz": "UTC"})

        self.task_project_goats_with_planned_hours_user.write(
            {
                "user_ids": [self.user_projectuser.id, self.user_projectmanager.id],
                "date_start": datetime(2023, 7, 28, 8),
                "date_end": datetime(2023, 7, 30, 16),
                "planned_hours": 24,
            }
        )

        self.task_project_pigs_with_planned_hours_user.write(
            {
                "user_ids": [self.user_projectuser.id],
                "date_start": datetime(2023, 7, 28, 22),
                "date_end": datetime(2023, 7, 29, 10),
                "planned_hours": 6,
            }
        )

        min_start, max_end = (
            datetime(2023, 7, 28).replace(tzinfo=UTC),
            datetime(2023, 7, 30, 16).replace(tzinfo=UTC),
        )
        _dummy, flex_users_hours_per_day, flex_user_work_hours_per_week = (
            self.task_project_pigs_no_planned_hours_user._scheduling_get_valid_intervals(
                min_start, max_end, self.user_projectuser | self.user_projectmanager
            )
        )

        self.assertEqual(
            float_compare(
                flex_users_hours_per_day[self.user_projectuser.id][date(2023, 7, 28)],
                3.57,
                precision_digits=2,
            ),
            0,
            "8 - 4.42",
        )
        self.assertEqual(
            float_compare(
                flex_users_hours_per_day[self.user_projectuser.id][date(2023, 7, 29)],
                -2.14,
                precision_digits=2,
            ),
            0,
            "8 - 10.14",
        )
        self.assertEqual(
            float_compare(
                flex_users_hours_per_day[self.user_projectuser.id][date(2023, 7, 30)],
                4.57,
                precision_digits=2,
            ),
            0,
            "8 - 3.42",
        )
        self.assertTrue(
            self.user_projectmanager.id not in flex_users_hours_per_day,
            "only users with flexible resources",
        )
        self.assertEqual(
            self.task_project_pigs_with_planned_hours_user.planning_overlap,
            Markup("<p>Armande ProjectUser has 1 tasks at the same time.</p>"),
        )

        self.assertEqual(
            float_compare(
                flex_user_work_hours_per_week[self.user_projectuser.id][
                    date(2023, 7, 24)
                ],
                22.0,
                precision_digits=2,
            ),
            0,
            "days 28, 29 and 30 (a Sunday) belong to the week starting Monday 24: "
            "40 - (4.42 + 10.14 + 3.42) = 22.0",
        )
        self.assertNotIn(
            date(2023, 7, 31),
            flex_user_work_hours_per_week[self.user_projectuser.id],
            "a week runs from the company's first day, Monday: no day of the period "
            "is in the next one",
        )
        self.assertTrue(
            self.user_projectmanager.id not in flex_user_work_hours_per_week,
            "only users with flexible resources",
        )

        self.task_project_pigs_no_planned_hours_no_user.write(
            {"user_ids": [self.user_projectuser.id], "planned_hours": 12}
        )
        self.task_project_pigs_no_planned_hours_user.write(
            {
                "user_ids": [self.user_projectuser.id, self.user_projectmanager.id],
                "planned_hours": 12,
            }
        )

        result = (
            (
                self.task_project_pigs_no_planned_hours_no_user
                | self.task_project_pigs_no_planned_hours_user
            )
            .with_context(
                {
                    "last_date_view": (min_start + relativedelta(months=1)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "gantt_scale": "week",
                    "cell_part": 2.0,
                }
            )
            .schedule_tasks(
                {
                    "date_start": min_start.strftime("%Y-%m-%d %H:%M:%S"),
                    "date_end": (min_start + relativedelta(day=1)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                }
            )
        )

        self.assertDictEqual(result[0], {}, "No warnings should be displayed")

        self.assertEqual(
            self.task_project_pigs_no_planned_hours_no_user.date_start,
            datetime(2023, 7, 28, 0),
        )
        self.assertAlmostEqual(
            self.task_project_pigs_no_planned_hours_no_user.date_end,
            datetime(2023, 7, 31, 3, 51, 25, 714285),
            delta=timedelta(milliseconds=1),
            msg="""
            allocated hours = 12 planned:
                - 3.57 hours: datetime(2023, 7, 28, 0, 0) -> datetime(2023, 7, 28, 3, 34, 17, 142858)
                - 0 hours: day 29, already overloaded
                - 4.57 hours: datetime(2023, 7, 30, 16, 0 -> datetime(2023, 7, 30, 20, 34, 17, 142857)
                - 3.87 hours: datetime(2023, 7, 31, 0, 0) -> datetime(2023, 7, 31, 3, 51, 25, 714285)
            """,
        )

        self.assertEqual(
            self.task_project_pigs_no_planned_hours_user.date_start,
            datetime(2023, 7, 31, 8),
        )
        self.assertAlmostEqual(
            self.task_project_pigs_no_planned_hours_user.date_end,
            datetime(2023, 8, 1, 9, 51, 25, 714285),
            delta=timedelta(milliseconds=1),
            msg="""
            allocated hours = 12 planned and assigned to 2 users (only one is flex, attendances should be the intersection), each user have 6 hours to do:
                - 4 hours: 31 morning - datetime(2023, 7, 31, 8) -> datetime(2023, 7, 31, 12)
                - ~0.13 hours = (8 - 3.87 - 4) =~ 8 minutes: datetime(2023, 7, 31, 13) -> datetime(2023, 7, 31, 13, 8, 34, 285715)
                - 1.87 hours: datetime(2023, 8, 1, 8, 0) -> datetime(2023, 8, 1, 9, 51, 25, 714285)
            """,
        )

        self.task_project_pigs_with_planned_hours_user.planned_hours = 0
        self.assertFalse(
            self.task_project_pigs_with_planned_hours_user.planning_overlap,
            "24 hours done in 3 days, no overload",
        )

    def test_auto_schedule_fully_flex_resource(self):
        self.env.user.sudo().tz = "UTC"
        self.user_projectuser.company_id.resource_calendar_id.tz = "UTC"

        self.task_project_pigs_with_planned_hours_user.planned_hours = 36
        self.user_projectuser.action_create_employee()
        self.user_projectmanager.action_create_employee()
        self.user_projectuser.employee_id.write({"resource_calendar_id": False})
        (
            self.user_projectuser.employee_id.resource_id
            | self.user_projectmanager.employee_id.resource_id
        ).write({"tz": "UTC"})

        self.task_project_goats_with_planned_hours_user.write(
            {
                "user_ids": [self.user_projectuser.id],
                "predecessor_ids": [self.task_project_pigs_with_planned_hours_user.id],
                "successor_ids": [self.task_project_pigs_no_planned_hours_user.id],
                "planned_hours": 12,
            }
        )

        self.task_project_pigs_no_planned_hours_no_user.write(
            {"user_ids": [self.user_projectuser.id], "planned_hours": 12}
        )
        self.task_project_pigs_no_planned_hours_user.write(
            {
                "user_ids": [self.user_projectuser.id, self.user_projectmanager.id],
                "successor_ids": [self.task_project_pigs_no_planned_hours_no_user.id],
                "planned_hours": 8,
            }
        )

        result = (
            (
                self.task_project_pigs_with_planned_hours_user
                | self.task_project_goats_with_planned_hours_user
                | self.task_project_pigs_no_planned_hours_user
                | self.task_project_pigs_no_planned_hours_no_user
            )
            .with_context(
                {
                    "last_date_view": self.end_date_view_str,
                    "gantt_scale": "week",
                    "cell_part": 2.0,
                }
            )
            .schedule_tasks(
                {
                    "date_start": self.start_date_view_str,
                    "date_end": (self.start_date_view + relativedelta(day=1)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "user_ids": self.user_projectuser.ids,
                }
            )
        )
        self.assertDictEqual(result[0], {}, "No warnings should be displayed")

        self.assertEqual(
            self.task_project_pigs_with_planned_hours_user.date_start,
            datetime(2023, 1, 1, 0),
            "day 1: 24h, no daily limit",
        )
        self.assertEqual(
            self.task_project_pigs_with_planned_hours_user.date_end,
            datetime(2023, 1, 2, 12),
            "day 2: 12h, no daily limit",
        )

        self.assertEqual(
            self.task_project_goats_with_planned_hours_user.date_start,
            datetime(2023, 1, 2, 12),
            "day 2, 12 hours, no daily limit",
        )
        self.assertEqual(
            self.task_project_goats_with_planned_hours_user.date_end,
            datetime(2023, 1, 3, 0),
        )

        self.assertEqual(
            self.task_project_pigs_no_planned_hours_user.date_start,
            datetime(2023, 1, 3, 8),
            "8 hours to do, 4 hours each user on day 9 from 08:00 to 12:00 (start from 08:00 instead of 00:00 as a regular resource is part of it)",
        )
        self.assertEqual(
            self.task_project_pigs_no_planned_hours_user.date_end,
            datetime(2023, 1, 3, 12),
        )

        self.assertEqual(
            self.task_project_pigs_no_planned_hours_no_user.date_start,
            datetime(2023, 1, 3, 12),
            "12 hours on day 3",
        )
        self.assertEqual(
            self.task_project_pigs_no_planned_hours_no_user.date_end,
            datetime(2023, 1, 4, 0),
        )


class ProjectEnterpriseHrTestSmartScheduleWithVersion(AutoShiftDatesHRCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.armande_employee.version_id.write(
            {
                "date_version": datetime(2023, 1, 1),
                "contract_date_start": datetime(2023, 1, 1),
                "contract_date_end": datetime(2023, 8, 10),
                "name": "CDD Contract for Armande ProjectUser",
                "resource_calendar_id": cls.calendar_morning.id,
                "wage": 5000.0,
            }
        )
        cls.contract = cls.armande_employee.version_id

    def test_auto_plan_with_expired_contract(self):
        self.task_1.write(
            {
                "date_start": False,
                "date_end": False,
            }
        )

        res = self.task_1.with_context(
            {
                "last_date_view": "2023-10-31 22:00:00",
                "cell_part": 2.0,
            }
        ).schedule_tasks(
            {
                "date_start": "2023-08-15 22:00:00",
                "date_end": "2023-10-16 21:59:59",
                "user_ids": self.armande_employee.user_id.ids,
            }
        )

        self.assertEqual(next(iter(res[0].keys())), "no_intervals")
        self.assertEqual(res[1], {}, "no pills planned")
        self.assertFalse(self.task_1.date_start)
        self.assertFalse(self.task_1.date_end)
