from datetime import date, datetime

from odoo import Command
from odoo.tests.common import TransactionCase, new_test_user


class TestHrAttendanceGanttData(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Monday 8h",
                "tz": "UTC",
                "hours_per_day": 8.0,
                "attendance_ids": [
                    Command.create(
                        {
                            "name": "Monday Morning",
                            "dayofweek": "0",
                            "hour_from": 9,
                            "hour_to": 12,
                            "day_period": "morning",
                        }
                    ),
                    Command.create(
                        {
                            "name": "Monday Afternoon",
                            "dayofweek": "0",
                            "hour_from": 12,
                            "hour_to": 17,
                            "day_period": "afternoon",
                        }
                    ),
                ],
            }
        )
        cls.flexible_calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible 8h",
                "tz": "UTC",
                "hours_per_day": 8.0,
                "full_time_required_hours": 8.0,
                "schedule_type": "flexible",
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Gantt Employee",
                "resource_calendar_id": cls.calendar.id,
                "date_version": date(2024, 1, 1),
                "contract_date_start": date(2024, 1, 1),
                "wage": 10,
            }
        )
        cls.flexible_employee = cls.env["hr.employee"].create(
            {
                "name": "Gantt Flexible",
                "resource_calendar_id": cls.flexible_calendar.id,
                "date_version": date(2024, 1, 1),
                "contract_date_start": date(2024, 1, 1),
                "wage": 10,
            }
        )

    def test_progress_bar_requires_internal_user(self):
        """Check that non-internal users get an empty progress bar payload."""
        portal_user = new_test_user(
            self.env, login="gantt_portal", groups="base.group_portal"
        )
        result = (
            self.env["hr.attendance"]
            .with_user(portal_user)
            ._gantt_progress_bar(
                "employee_id",
                [self.employee.id],
                datetime(2024, 1, 8),
                datetime(2024, 1, 14),
            )
        )
        self.assertEqual(result, {})

    def test_progress_bar_unsupported_field(self):
        """Check that a progress bar on any field other than employee_id is
        rejected."""
        with self.assertRaises(NotImplementedError):
            self.env["hr.attendance"]._gantt_progress_bar(
                "department_id",
                [self.employee.id],
                datetime(2024, 1, 8),
                datetime(2024, 1, 14),
            )

    def test_overtime_progress_zero_worked_hours(self):
        """Check that an attendance without worked hours reports 100% progress."""
        attendance = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2024, 1, 8, 9, 0),
                "check_out": datetime(2024, 1, 8, 9, 0),
            }
        )
        self.assertEqual(attendance.overtime_progress, 100)

    def test_gantt_data_includes_previously_active_employees(self):
        """Check that employees with attendances only before the gantt window
        (within the 60-day lookback) are appended as extra groups without
        record ids."""
        past_employee = self.env["hr.employee"].create(
            {
                "name": "Gantt Past",
                "resource_calendar_id": self.calendar.id,
            }
        )
        self.env["hr.attendance"].create(
            [
                {
                    "employee_id": self.employee.id,
                    "check_in": datetime(2024, 3, 4, 9, 0),
                    "check_out": datetime(2024, 3, 4, 17, 0),
                },
                {
                    "employee_id": past_employee.id,
                    "check_in": datetime(2024, 2, 5, 9, 0),
                    "check_out": datetime(2024, 2, 5, 17, 0),
                },
            ]
        )
        employee_ids = [self.employee.id, past_employee.id]
        gantt_data = (
            self.env["hr.attendance"]
            .with_context(
                gantt_start_date="2024-03-04 00:00:00",
                user_domain=[("employee_id", "in", employee_ids)],
            )
            .get_gantt_data(
                [
                    ("employee_id", "in", employee_ids),
                    ("check_in", ">=", "2024-03-04 00:00:00"),
                    ("check_out", "<=", "2024-03-10 23:59:59"),
                ],
                ["employee_id"],
                {"display_name": {}},
                start_date="2024-03-04 00:00:00",
                stop_date="2024-03-10 23:59:59",
                scale="week",
            )
        )
        grouped_ids = [group["employee_id"][0] for group in gantt_data["groups"]]
        self.assertIn(self.employee.id, grouped_ids)
        self.assertIn(past_employee.id, grouped_ids)
        past_group = next(
            g for g in gantt_data["groups"] if g["employee_id"][0] == past_employee.id
        )
        self.assertNotIn("__record_ids", past_group)
        self.assertEqual(gantt_data["length"], 2)

    def test_gantt_unavailability_standard_vs_flexible(self):
        """Check that a standard-calendar employee gets unavailability intervals
        while a flexible-hours employee is available for the whole window."""
        result = self.env["hr.attendance"]._gantt_unavailability(
            "employee_id",
            [self.employee.id, self.flexible_employee.id],
            datetime(2024, 1, 8),
            datetime(2024, 1, 14),
            "week",
        )
        self.assertEqual(result[self.flexible_employee.id], [])
        standard_intervals = result[self.employee.id]
        self.assertGreaterEqual(
            len(standard_intervals),
            1,
            "a Monday-only calendar must yield unavailability in a full week",
        )
        first_interval = standard_intervals[0]
        self.assertLess(first_interval["start"], first_interval["stop"])
