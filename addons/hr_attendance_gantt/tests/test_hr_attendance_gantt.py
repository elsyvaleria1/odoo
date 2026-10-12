from datetime import date, datetime

from odoo.tests.common import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestHrAttendanceGantt(TransactionCase):
    def test_gantt_progress_bar(self):
        calendar_8 = self.env["resource.calendar"].create(
            {
                "name": "Calendar 8h",
                "tz": "UTC",
                "hours_per_day": 8.0,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Monday Morning",
                            "dayofweek": "0",
                            "hour_from": 9,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Monday Afternoon",
                            "dayofweek": "0",
                            "hour_from": 12,
                            "hour_to": 17,
                            "day_period": "afternoon",
                        },
                    ),
                ],
            }
        )

        calendar_10 = self.env["resource.calendar"].create(
            {
                "name": "Calendar 10h",
                "tz": "UTC",
                "hours_per_day": 10.0,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Monday Morning",
                            "dayofweek": "0",
                            "hour_from": 9,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Monday Afternoon",
                            "dayofweek": "0",
                            "hour_from": 12,
                            "hour_to": 19,
                            "day_period": "afternoon",
                        },
                    ),
                ],
            }
        )

        calendar_12 = self.env["resource.calendar"].create(
            {
                "name": "Calendar 12h",
                "tz": "UTC",
                "hours_per_day": 12.0,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Monday Morning",
                            "dayofweek": "0",
                            "hour_from": 9,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Monday Afternoon",
                            "dayofweek": "0",
                            "hour_from": 12,
                            "hour_to": 21,
                            "day_period": "afternoon",
                        },
                    ),
                ],
            }
        )

        contract_emp = self.env["hr.employee"].create(
            {
                "name": "Johhny Contract",
                "date_version": date(2024, 1, 1),
                "contract_date_start": date(2024, 1, 1),
                "wage": 10,
                "resource_calendar_id": calendar_8.id,
            }
        )

        contract_emp.create_version(
            {
                "date_version": date(2024, 2, 1),
                "resource_calendar_id": calendar_10.id,
                "wage": 10,
            }
        )
        contract_emp.create_version(
            {
                "date_version": date(2024, 3, 1),
                "resource_calendar_id": calendar_12.id,
                "wage": 10,
            }
        )

        contract_emp1 = self.env["hr.employee"].create(
            {
                "name": "John Contract",
                "date_version": date(2024, 2, 1),
                "contract_date_start": date(2024, 1, 1),
                "wage": 10,
                "resource_calendar_id": calendar_8.id,
            }
        )

        contract_emp1.create_version(
            {
                "date_version": date(2024, 3, 1),
                "resource_calendar_id": calendar_10.id,
                "wage": 10,
            }
        )
        contract_emp1.create_version(
            {
                "date_version": date(2024, 4, 1),
                "resource_calendar_id": calendar_12.id,
                "wage": 10,
            }
        )

        interval_1 = self.env["hr.attendance"]._gantt_progress_bar(
            "employee_id",
            [contract_emp.id],
            datetime(2024, 1, 8),
            datetime(2024, 1, 14),
        )

        self.assertEqual(interval_1[contract_emp.id]["max_value"], 8)

        interval_1 = self.env["hr.attendance"]._gantt_progress_bar(
            "employee_id",
            [contract_emp.id],
            datetime(2024, 2, 8),
            datetime(2024, 2, 14),
        )

        self.assertEqual(interval_1[contract_emp.id]["max_value"], 10)

        interval_2 = self.env["hr.attendance"]._gantt_progress_bar(
            "employee_id",
            [contract_emp.id],
            datetime(2024, 3, 4),
            datetime(2024, 3, 10),
        )

        self.assertEqual(interval_2[contract_emp.id]["max_value"], 12)

        interval_1 = self.env["hr.attendance"]._gantt_progress_bar(
            "employee_id",
            [contract_emp1.id],
            datetime(2024, 1, 8),
            datetime(2024, 1, 14),
        )

        self.assertEqual(interval_1[contract_emp1.id]["max_value"], 8)

        interval_2 = self.env["hr.attendance"]._gantt_progress_bar(
            "employee_id",
            [contract_emp1.id],
            datetime(2024, 1, 29),
            datetime(2024, 2, 5),
        )

        self.assertEqual(interval_1[contract_emp1.id]["max_value"], 8)

        interval_3 = self.env["hr.attendance"]._gantt_progress_bar(
            "employee_id",
            [contract_emp1.id],
            datetime(2024, 3, 8),
            datetime(2024, 3, 14),
        )

        self.assertEqual(interval_3[contract_emp1.id]["max_value"], 10)

        interval_4 = self.env["hr.attendance"]._gantt_progress_bar(
            "employee_id",
            [contract_emp1.id],
            datetime(2024, 4, 4),
            datetime(2024, 4, 10),
        )

        self.assertEqual(interval_4[contract_emp1.id]["max_value"], 12)

    def test_gantt_progress_with_flexible_employees(self):
        flexible_calendar, calendar = self.env["resource.calendar"].create(
            [
                {
                    "name": "Calendar 8h",
                    "tz": "UTC",
                    "company_id": False,
                    "full_time_required_hours": 8.0,
                    "hours_per_week": 8.0,
                    "hours_per_day": 8.0,
                    "schedule_type": "flexible",
                },
                {
                    "name": "Calendar 8h",
                    "tz": "UTC",
                    "company_id": False,
                    "full_time_required_hours": 8.0,
                    "hours_per_day": 8.0,
                    "attendance_ids": [
                        (
                            0,
                            0,
                            {
                                "name": "Monday Morning",
                                "dayofweek": "0",
                                "hour_from": 9,
                                "hour_to": 12,
                                "day_period": "morning",
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": "Monday Afternoon",
                                "dayofweek": "0",
                                "hour_from": 12,
                                "hour_to": 17,
                                "day_period": "afternoon",
                            },
                        ),
                    ],
                },
            ]
        )

        emp1, emp2 = self.env["hr.employee"].create(
            [
                {
                    "name": "freelance1",
                    "employee_type": "freelance",
                    "resource_calendar_id": flexible_calendar.id,
                },
                {
                    "name": "freelance2",
                    "employee_type": "freelance",
                    "resource_calendar_id": calendar.id,
                },
            ]
        )
        self.assertTrue(emp1.resource_id._is_flexible())
        self.assertFalse(emp2.resource_id._is_flexible())
        calendar.schedule_type = "flexible"

        interval = self.env["hr.attendance"]._gantt_progress_bar(
            "employee_id",
            [emp1.id, emp2.id],
            datetime(2024, 1, 8),
            datetime(2024, 1, 15),
        )

        self.assertEqual(interval[emp1.id]["max_value"], 8)
        self.assertEqual(interval[emp2.id]["max_value"], 8)
