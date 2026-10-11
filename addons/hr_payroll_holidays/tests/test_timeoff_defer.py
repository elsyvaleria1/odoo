from ast import literal_eval
from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo.exceptions import UserError
from odoo.fields import Datetime
from odoo.tests.common import tagged

from odoo.addons.hr_payroll_holidays.tests.common import TestPayrollHolidaysBase


@tagged("post_install", "-at_install")
class TestTimeoffDefer(TestPayrollHolidaysBase):
    def test_no_defer(self):
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Donald Payslip",
                "employee_id": self.emp.id,
            }
        )

        payslip.compute_sheet()

        leave = self.env["hr.leave"].create(
            {
                "name": "Golf time",
                "holiday_status_id": self.leave_type.id,
                "employee_id": self.emp.id,
                "request_date_from": (date.today() + relativedelta(day=13)),
                "request_date_to": (date.today() + relativedelta(day=16)),
            }
        )
        leave.action_approve()

        self.assertNotEqual(
            leave.payslip_state, "blocked", "Leave should not be to defer"
        )

    def test_to_defer(self):
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Donald Payslip",
                "employee_id": self.emp.id,
            }
        )

        payslip.compute_sheet()
        payslip.action_payslip_done()

        leave = self.env["hr.leave"].create(
            {
                "name": "Golf time",
                "holiday_status_id": self.leave_type.id,
                "employee_id": self.emp.id,
                "request_date_from": (date.today() + relativedelta(day=13)),
                "request_date_to": (date.today() + relativedelta(day=16)),
            }
        )
        leave.action_approve()
        self.assertEqual(leave.payslip_state, "blocked", "Leave should be to defer")

    def test_multi_payslip_defer(self):

        waiting_payslip = self.env["hr.payslip"].create(
            {
                "name": "Donald Payslip draft",
                "employee_id": self.emp.id,
            }
        )
        done_payslip = self.env["hr.payslip"].create(
            {
                "name": "Donald Payslip done",
                "employee_id": self.emp.id,
            }
        )

        waiting_payslip.compute_sheet()
        done_payslip.compute_sheet()
        done_payslip.action_payslip_done()

        leave = self.env["hr.leave"].create(
            {
                "name": "Golf time",
                "holiday_status_id": self.leave_type.id,
                "employee_id": self.emp.id,
                "request_date_from": (date.today() + relativedelta(day=13)),
                "request_date_to": (date.today() + relativedelta(day=16)),
            }
        )
        leave.action_approve()

        self.assertNotEqual(
            leave.payslip_state, "blocked", "Leave should not be to defer"
        )

    def test_payslip_paid_past(self):
        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2022-01-01",
                "date_to": "2022-01-31",
            }
        )

        payslip.compute_sheet()
        self.assertEqual(payslip.state, "draft")
        self.assertTrue(payslip.line_ids)

        leave_1 = (
            self.env["hr.leave"]
            .with_user(self.vlad)
            .create(
                {
                    "name": "Tennis",
                    "holiday_status_id": self.leave_type.id,
                    "employee_id": self.emp.id,
                    "request_date_from": "2022-01-12",
                    "request_date_to": "2022-01-12",
                }
            )
        )
        payslip.action_payslip_done()
        self.assertEqual(payslip.state, "validated")

        leave_1.sudo().action_approve()
        self.assertEqual(leave_1.payslip_state, "blocked", "Leave should be to defer")

        leave_2 = (
            self.env["hr.leave"]
            .with_user(self.vlad)
            .create(
                {
                    "name": "Tennis",
                    "holiday_status_id": self.leave_type.id,
                    "employee_id": self.emp.id,
                    "request_date_from": "2022-01-19",
                    "request_date_to": "2022-01-19",
                }
            )
        )
        leave_2.sudo().action_approve()
        self.assertEqual(leave_2.payslip_state, "blocked", "Leave should be to defer")

        leave_3 = (
            self.env["hr.leave"]
            .with_user(self.vlad)
            .create(
                {
                    "name": "Tennis",
                    "holiday_status_id": self.leave_type.id,
                    "employee_id": self.emp.id,
                    "request_date_from": "2022-01-31",
                    "request_date_to": "2022-02-01",
                }
            )
        )
        leave_3.sudo().action_approve()
        self.assertEqual(leave_3.payslip_state, "blocked", "Leave should be to defer")

        leave_4 = (
            self.env["hr.leave"]
            .with_user(self.vlad)
            .create(
                {
                    "name": "Tennis",
                    "holiday_status_id": self.leave_type.id,
                    "employee_id": self.emp.id,
                    "request_date_from": "2021-01-31",
                    "request_date_to": "2022-01-03",
                }
            )
        )
        leave_4.sudo().action_approve()
        self.assertEqual(leave_4.payslip_state, "blocked", "Leave should be to defer")

    def test_report_to_next_month(self):
        self.emp.version_ids.generate_work_entries(date(2022, 1, 1), date(2022, 2, 28))
        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2022-01-01",
                "date_to": "2022-01-31",
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()
        self.assertEqual(payslip.state, "validated")

        leave = self.env["hr.leave"].new(
            {
                "name": "Tennis",
                "employee_id": self.emp.id,
                "holiday_status_id": self.leave_type.id,
                "request_date_from": date(2022, 1, 31),
                "request_date_to": date(2022, 1, 31),
                "request_hour_from": 7,
                "request_hour_to": 18,
            }
        )
        leave._compute_date_from_to()
        leave = self.env["hr.leave"].create(leave._convert_to_write(leave._cache))
        leave.action_approve()
        self.assertEqual(leave.payslip_state, "blocked", "Leave should be to defer")

        leave.action_report_to_next_month()
        reported_work_entries = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.emp.id),
                ("company_id", "=", self.env.company.id),
                ("state", "=", "draft"),
                ("work_entry_type_id", "=", self.leave_type.work_entry_type_id.id),
                ("date", ">=", Datetime.to_datetime("2022-02-01")),
                (
                    "date",
                    "<=",
                    datetime.combine(
                        Datetime.to_datetime("2022-02-28"), datetime.max.time()
                    ),
                ),
            ]
        )
        self.assertEqual(reported_work_entries[0].date, date(2022, 2, 1))
        self.assertEqual(reported_work_entries[0].duration, 8)

    def test_report_to_next_month_overlap(self):
        self.emp.version_ids.generate_work_entries(date(2022, 1, 1), date(2022, 2, 28))
        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2022-01-01",
                "date_to": "2022-01-31",
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()
        self.assertEqual(payslip.state, "validated")

        leave = self.env["hr.leave"].new(
            {
                "name": "Tennis",
                "employee_id": self.emp.id,
                "holiday_status_id": self.leave_type.id,
                "request_date_from": date(2022, 1, 31),
                "request_date_to": date(2022, 2, 2),
                "request_hour_from": 7,
                "request_hour_to": 18,
            }
        )
        leave._compute_date_from_to()
        leave = self.env["hr.leave"].create(leave._convert_to_write(leave._cache))
        leave.action_approve()
        self.assertEqual(leave.payslip_state, "blocked", "Leave should be to defer")

        leave.action_report_to_next_month()
        reported_work_entries = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.emp.id),
                ("company_id", "=", self.env.company.id),
                ("state", "=", "draft"),
                ("work_entry_type_id", "=", self.leave_type.work_entry_type_id.id),
                ("date", ">=", Datetime.to_datetime("2022-02-01")),
                (
                    "date",
                    "<=",
                    datetime.combine(
                        Datetime.to_datetime("2022-02-28"), datetime.max.time()
                    ),
                ),
            ]
        )
        self.assertEqual(len(reported_work_entries), 3)
        self.assertEqual(list({we.date.day for we in reported_work_entries}), [1, 2, 3])
        self.assertEqual(reported_work_entries[0].date, date(2022, 2, 1))
        self.assertEqual(reported_work_entries[0].duration, 8)

    def test_report_to_next_month_not_enough_days(self):
        self.emp.version_ids.generate_work_entries(date(2022, 1, 1), date(2022, 2, 28))
        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2022-01-01",
                "date_to": "2022-01-31",
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()
        self.assertEqual(payslip.state, "validated")

        leave = self.env["hr.leave"].new(
            {
                "name": "Tennis",
                "employee_id": self.emp.id,
                "holiday_status_id": self.leave_type.id,
                "request_date_from": date(2022, 1, 1),
                "request_date_to": date(2022, 1, 31),
                "request_hour_from": 7,
                "request_hour_to": 18,
            }
        )
        leave._compute_date_from_to()
        leave = self.env["hr.leave"].create(leave._convert_to_write(leave._cache))
        leave.action_approve()
        self.assertEqual(leave.payslip_state, "blocked", "Leave should be to defer")

        with self.assertRaises(UserError):
            leave.action_report_to_next_month()

    def test_report_to_next_month_long_time_off(self):
        self.emp.version_ids.generate_work_entries(date(2022, 1, 1), date(2022, 2, 28))
        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2022-01-01",
                "date_to": "2022-01-31",
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()
        self.assertEqual(payslip.state, "validated")

        leave = self.env["hr.leave"].new(
            {
                "name": "Tennis",
                "employee_id": self.emp.id,
                "holiday_status_id": self.leave_type.id,
                "request_date_from": date(2022, 1, 1),
                "request_date_to": date(2022, 3, 10),
                "request_hour_from": 7,
                "request_hour_to": 18,
            }
        )
        leave._compute_date_from_to()
        leave = self.env["hr.leave"].create(leave._convert_to_write(leave._cache))
        leave.action_approve()
        self.assertEqual(leave.payslip_state, "blocked", "Leave should be to defer")

        with self.assertRaises(UserError):
            leave.action_report_to_next_month()

    def test_report_to_next_month_2_months_time_off(self):
        self.emp.version_ids.generate_work_entries(date(2026, 2, 1), date(2026, 2, 28))
        resource_calendar = self.env["resource.calendar"].create(
            {
                "name": "Test Two Week Calendar No Breaks",
                "hours_per_day": 7.6,
                "hours_per_week": 38,
                "full_time_required_hours": 38,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Monday",
                            "dayofweek": "0",
                            "hour_from": 8,
                            "hour_to": 15.6,
                            "day_period": "full_day",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Tuesday",
                            "dayofweek": "1",
                            "hour_from": 8,
                            "hour_to": 15.6,
                            "day_period": "full_day",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Wednesday",
                            "dayofweek": "2",
                            "hour_from": 8,
                            "hour_to": 15.6,
                            "day_period": "full_day",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Thursday",
                            "dayofweek": "3",
                            "hour_from": 8,
                            "hour_to": 15.6,
                            "day_period": "full_day",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Friday",
                            "dayofweek": "4",
                            "hour_from": 8,
                            "hour_to": 15.6,
                            "day_period": "full_day",
                        },
                    ),
                ],
            }
        )
        self.emp.resource_calendar_id = resource_calendar
        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2026-02-01",
                "date_to": "2026-02-28",
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()
        self.assertEqual(payslip.state, "validated")

        leave = self.env["hr.leave"].create(
            [
                {
                    "name": "Tennis",
                    "employee_id": self.emp.id,
                    "holiday_status_id": self.leave_type.id,
                    "request_date_from": date(2026, 2, 27),
                    "request_date_to": date(2026, 3, 5),
                }
            ]
        )
        leave.action_approve()
        self.emp.version_ids.generate_work_entries(date(2026, 3, 1), date(2026, 3, 31))
        self.assertEqual(leave.payslip_state, "blocked", "Leave should be to defer")
        leave.action_report_to_next_month()
        defered_work_entry = self.env["hr.work.entry"].search(
            [
                ("date", "=", date(2026, 3, 6)),
                ("version_id", "in", self.emp.version_ids.ids),
            ]
        )
        self.assertEqual(defered_work_entry.work_entry_type_id.code, "LEAVETEST300")

    def test_report_to_next_month_half_days(self):
        self.leave_type.request_unit = "half_day"
        self.emp.version_ids.generate_work_entries(date(2022, 1, 1), date(2022, 2, 28))
        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2022-01-01",
                "date_to": "2022-01-31",
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()
        self.assertEqual(payslip.state, "validated")

        leave = self.env["hr.leave"].new(
            {
                "name": "Tennis",
                "holiday_status_id": self.leave_type.id,
                "employee_id": self.emp.id,
                "request_date_from": date(2022, 1, 31),
                "request_date_to": date(2022, 1, 31),
                "request_date_from_period": "am",
                "request_date_to_period": "am",
            }
        )
        leave._compute_date_from_to()
        leave = self.env["hr.leave"].create(leave._convert_to_write(leave._cache))

        leave.action_approve()
        self.assertEqual(leave.payslip_state, "blocked", "Leave should be to defer")

        leave.action_report_to_next_month()
        reported_work_entries = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.emp.id),
                ("company_id", "=", self.env.company.id),
                ("state", "=", "draft"),
                ("work_entry_type_id", "=", self.leave_type.work_entry_type_id.id),
                ("date", ">=", Datetime.to_datetime("2022-02-01")),
                (
                    "date",
                    "<=",
                    datetime.combine(
                        Datetime.to_datetime("2022-02-28"), datetime.max.time()
                    ),
                ),
            ]
        )
        self.assertEqual(len(reported_work_entries), 1)
        self.assertEqual(reported_work_entries[0].date, date(2022, 2, 1))
        self.assertEqual(reported_work_entries[0].duration, 4)

        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2022-02-01",
                "date_to": "2022-02-28",
            }
        )
        payslip.compute_sheet()
        self.assertEqual(2, len(payslip.worked_days_line_ids))
        self.assertTrue(
            any(
                wd.work_entry_type_id == self.leave_type.work_entry_type_id
                for wd in payslip.worked_days_line_ids
            )
        )
        leave_worked_day_line = payslip.worked_days_line_ids.filtered(
            lambda wd: wd.work_entry_type_id == self.leave_type.work_entry_type_id
        )
        self.assertEqual(0.5, leave_worked_day_line.number_of_days)
        self.assertEqual(4, leave_worked_day_line.number_of_hours)

    def test_report_to_next_month_hourly(self):
        self.leave_type.request_unit = "hour"
        self.emp.version_ids.generate_work_entries(date(2022, 1, 1), date(2022, 2, 28))
        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2022-01-01",
                "date_to": "2022-01-31",
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()
        self.assertEqual(payslip.state, "validated")
        leave = self.env["hr.leave"].new(
            {
                "name": "Tennis",
                "holiday_status_id": self.leave_type.id,
                "employee_id": self.emp.id,
                "request_date_from": date(2022, 1, 31),
                "request_date_to": date(2022, 1, 31),
                "request_hour_from": 10.0,
                "request_hour_to": 12.0,
            }
        )
        leave._compute_date_from_to()
        leave = self.env["hr.leave"].create(leave._convert_to_write(leave._cache))

        leave.action_approve()
        self.assertEqual(leave.payslip_state, "blocked", "Leave should be to defer")

        leave.action_report_to_next_month()
        reported_work_entries = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.emp.id),
                ("company_id", "=", self.env.company.id),
                ("state", "=", "draft"),
                ("work_entry_type_id", "=", self.leave_type.work_entry_type_id.id),
                ("date", ">=", Datetime.to_datetime("2022-02-01")),
                (
                    "date",
                    "<=",
                    datetime.combine(
                        Datetime.to_datetime("2022-02-28"), datetime.max.time()
                    ),
                ),
            ]
        )
        self.assertEqual(len(reported_work_entries), 1)
        self.assertEqual(reported_work_entries[0].date, date(2022, 2, 1))
        self.assertEqual(reported_work_entries[0].duration, 2)

        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2022-02-01",
                "date_to": "2022-02-28",
            }
        )
        payslip.compute_sheet()
        self.assertEqual(2, len(payslip.worked_days_line_ids))
        self.assertTrue(
            any(
                wd.work_entry_type_id == self.leave_type.work_entry_type_id
                for wd in payslip.worked_days_line_ids
            )
        )
        leave_worked_day_line = payslip.worked_days_line_ids.filtered(
            lambda wd: wd.work_entry_type_id == self.leave_type.work_entry_type_id
        )
        self.assertEqual(2, leave_worked_day_line.number_of_hours)

    def test_defer_next_month_double_time_off(self):
        self.emp.version_ids._generate_work_entries(
            datetime(2023, 6, 1), datetime(2023, 7, 31)
        )
        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2023-06-01",
                "date_to": "2023-06-30",
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()
        self.assertEqual(payslip.state, "validated")

        leave_data = [
            {
                "name": "Paid Time Off",
                "employee_id": self.emp.id,
                "holiday_status_id": self.leave_type.id,
                "request_date_from": "2023-06-26 00:00:00",
                "request_date_to": "2023-06-30 23:59:59",
            },
            {
                "name": "Paid Time Off",
                "employee_id": self.emp.id,
                "holiday_status_id": self.leave_type.id,
                "request_date_from": "2023-07-03 00:00:00",
                "request_date_to": "2023-07-05 23:59:59",
            },
        ]
        leaves = self.env["hr.leave"].create(leave_data)
        leaves.action_approve()
        leaves[0].action_report_to_next_month()
        july_work_entries = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.emp.id),
                ("company_id", "=", self.env.company.id),
                ("state", "=", "draft"),
                ("work_entry_type_id", "=", self.leave_type.work_entry_type_id.id),
                ("date", ">=", Datetime.to_datetime("2023-07-01")),
                (
                    "date",
                    "<=",
                    datetime.combine(
                        Datetime.to_datetime("2023-07-31"), datetime.max.time()
                    ),
                ),
            ],
            order="date",
        )
        self.assertEqual(len(july_work_entries), 8)
        self.assertEqual(
            list({we.date.day for we in july_work_entries}), [3, 4, 5, 6, 7, 10, 11, 12]
        )
        self.assertEqual(july_work_entries[0].date, date(2023, 7, 3))
        self.assertEqual(july_work_entries[0].duration, 8)

    def test_leave_overlaping_over_2_month(self):
        may_work_entries = self.emp.version_ids._generate_work_entries(
            datetime.fromisoformat("2025-05-01"), datetime.fromisoformat("2025-05-31")
        )
        june_work_entries = self.emp.version_ids._generate_work_entries(
            datetime.fromisoformat("2025-06-01"), datetime.fromisoformat("2025-06-30")
        )
        self.assertRecordValues(
            (may_work_entries + june_work_entries).work_entry_type_id,
            [{"code": "WORK100"}],
        )
        self.assertEqual(set(may_work_entries.mapped("state")), {"draft"})

        may_payslip_batch = self.env["hr.payslip.run"].create(
            {
                "name": "May 2025 payslip batch",
                "date_start": "2025-05-01",
                "date_end": "2025-05-31",
                "company_id": self.emp.company_id.id,
            }
        )
        may_payslip_batch.generate_payslips(employee_ids=self.emp.ids)
        may_payslip_batch.action_validate()
        self.assertEqual(set(may_work_entries.mapped("state")), {"validated"})

        overlapping_work_entry_type = self.env["hr.work.entry.type"].create(
            {
                "name": "Annoying overlaping work entry type",
                "is_leave": True,
                "code": "OVERLAPING101",
            }
        )
        overlapping_leave_type = self.env["hr.leave.type"].create(
            {
                "name": "Annoying overlaping leave type",
                "work_entry_type_id": overlapping_work_entry_type.id,
                "requires_allocation": False,
            }
        )
        overlapping_leave = self.env["hr.leave"].create(
            {
                "name": "Annoying overlaping leave",
                "holiday_status_id": overlapping_leave_type.id,
                "employee_id": self.emp.id,
                "date_from": "2025-05-26 00:00:01",
                "date_to": "2025-06-06 23:59:59",
                "request_date_from": "2025-05-26 00:00:01",
                "request_date_to": "2025-06-06 23:59:59",
            }
        )
        overlapping_leave.action_approve()
        self.assertEqual(
            overlapping_leave.payslip_state, "blocked", "Leave should be to defer"
        )

        overlapping_leave.action_report_to_next_month()

        self.assertEqual(
            len(
                june_work_entries.filtered(
                    lambda we: we.work_entry_type_id.code == "OVERLAPING101"
                )
            ),
            10,
            "There should only have 10 OVERLAPING101 work entry deferred (1 Work entry per leave day)",
        )

        june_payslip_batch = self.env["hr.payslip.run"].create(
            {
                "name": "June 2025 payslip batch",
                "date_start": "2025-06-01",
                "date_end": "2025-06-30",
            }
        )
        june_payslip_batch.generate_payslips(employee_ids=self.emp.ids)
        june_payslip_batch.action_validate()
        payslip = june_payslip_batch.slip_ids
        self.assertEqual(
            set(payslip.worked_days_line_ids.mapped("number_of_days")),
            {10, 11},
            "There should be 10 timeoff (5 from may and 5 from june) and 11 Attendances (21 - 10) on the payslip",
        )

    def test_timeoff_overlaping_with_a_public_holiday_shouldnt_be_deferred(self):
        self.env["resource.schedule.exception"].create(
            {
                "name": "Supreme leader party you can't miss",
                "date_from": Datetime.from_string("2025-05-29 00:00:00"),
                "date_to": Datetime.from_string("2025-05-29 23:59:59"),
                "work_entry_type_id": self.env["hr.work.entry.type"]
                .create(
                    {
                        "name": "Public holiday leaves that can't be missed",
                        "code": "LEAVECANTMISS3000",
                        "is_leave": True,
                    }
                )
                .id,
            }
        )

        may_work_entries = self.emp.version_ids._generate_work_entries(
            datetime.fromisoformat("2025-05-01"), datetime.fromisoformat("2025-05-31")
        )
        june_work_entries = self.emp.version_ids._generate_work_entries(
            datetime.fromisoformat("2025-06-01"), datetime.fromisoformat("2025-06-30")
        )

        self.assertRecordValues(
            may_work_entries.work_entry_type_id,
            [{"code": "WORK100"}, {"code": "LEAVECANTMISS3000"}],
        )
        self.assertRecordValues(
            june_work_entries.work_entry_type_id, [{"code": "WORK100"}]
        )

        may_payslip_batch = self.env["hr.payslip.run"].create(
            {
                "name": "May 2025 payslip batch",
                "date_start": "2025-05-01",
                "date_end": "2025-05-31",
                "company_id": self.emp.company_id.id,
            }
        )
        may_payslip_batch.generate_payslips(employee_ids=self.emp.ids)
        may_payslip_batch.action_validate()

        overlapping_work_entry_type = self.env["hr.work.entry.type"].create(
            {
                "name": "Annoying overlaping work entry type",
                "is_leave": True,
                "code": "OVERLAPING101",
            }
        )
        overlapping_leave_type = self.env["hr.leave.type"].create(
            {
                "name": "Annoying overlaping leave type",
                "work_entry_type_id": overlapping_work_entry_type.id,
                "requires_allocation": False,
            }
        )
        overlapping_leave = self.env["hr.leave"].create(
            {
                "name": "Annoying overlaping leave",
                "holiday_status_id": overlapping_leave_type.id,
                "employee_id": self.emp.id,
                "date_from": "2025-05-26 00:00:01",
                "date_to": "2025-06-06 23:59:59",
                "request_date_from": "2025-05-26 00:00:01",
                "request_date_to": "2025-06-06 23:59:59",
            }
        )
        overlapping_leave.action_approve()
        self.assertEqual(
            overlapping_leave.payslip_state, "blocked", "Leave should be to defer"
        )

        overlapping_leave.action_report_to_next_month()

        self.assertEqual(
            set(may_work_entries.work_entry_type_id.mapped("code")),
            {"WORK100", "LEAVECANTMISS3000"},
            "Nothing should have changed regarding May work entries",
        )
        self.assertEqual(
            set(june_work_entries.work_entry_type_id.mapped("code")),
            {"WORK100", "OVERLAPING101"},
            "June work entries should contain the deferred work entries from May",
        )
        self.assertEqual(
            len(
                june_work_entries.filtered(
                    lambda we: we.work_entry_type_id.code == "OVERLAPING101"
                )
            ),
            9,
            "There should only have 9 OVERLAPING101 work entry deferred (1 Work entry per leave day)",
        )

        june_payslip_batch = self.env["hr.payslip.run"].create(
            {
                "name": "June 2025 payslip batch",
                "date_start": "2025-06-01",
                "date_end": "2025-06-30",
            }
        )
        june_payslip_batch.generate_payslips(employee_ids=self.emp.ids)
        june_payslip_batch.action_validate()
        payslip = june_payslip_batch.slip_ids
        self.assertEqual(
            set(payslip.worked_days_line_ids.mapped("number_of_days")),
            {9, 12},
            "There should be 9 timeoff and 12 Attendances on the payslip",
        )

    def test_report_to_next_month_skips_a_paid_month(self):
        self.emp.version_ids.generate_work_entries(date(2022, 1, 1), date(2022, 2, 28))
        for date_from, date_to in [
            ("2022-01-01", "2022-01-31"),
            ("2022-02-01", "2022-02-28"),
        ]:
            payslip = self.env["hr.payslip"].create(
                {
                    "name": "toto payslip %s" % date_from,
                    "employee_id": self.emp.id,
                    "date_from": date_from,
                    "date_to": date_to,
                }
            )
            payslip.compute_sheet()
            payslip.action_payslip_done()
            self.assertEqual(payslip.state, "validated")

        february_entries = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.emp.id),
                ("date", ">=", date(2022, 2, 1)),
                ("date", "<=", date(2022, 2, 28)),
            ]
        )
        self.assertTrue(february_entries)
        self.assertFalse(
            february_entries.filtered(lambda we: we.state == "draft"),
            "February is paid, so none of its work entries can be edited",
        )
        self.env["hr.work.entry"].search(
            [("employee_id", "=", self.emp.id), ("date", ">=", date(2022, 3, 1))]
        ).unlink()

        leave = self.env["hr.leave"].new(
            {
                "name": "Tennis",
                "employee_id": self.emp.id,
                "holiday_status_id": self.leave_type.id,
                "request_date_from": date(2022, 1, 31),
                "request_date_to": date(2022, 1, 31),
                "request_hour_from": 7,
                "request_hour_to": 18,
            }
        )
        leave._compute_date_from_to()
        leave = self.env["hr.leave"].create(leave._convert_to_write(leave._cache))
        leave.action_approve()
        self.assertEqual(leave.payslip_state, "blocked", "Leave should be to defer")

        leave.action_report_to_next_month()

        reported_work_entries = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.emp.id),
                ("company_id", "=", self.env.company.id),
                ("work_entry_type_id", "=", self.leave_type.work_entry_type_id.id),
                ("date", ">=", date(2022, 3, 1)),
                ("date", "<=", date(2022, 3, 31)),
            ]
        )
        self.assertEqual(len(reported_work_entries), 1)
        self.assertEqual(reported_work_entries.date, date(2022, 3, 1))
        self.assertEqual(reported_work_entries.duration, 8)
        self.assertEqual(leave.payslip_state, "done")

    def test_to_defer_filter_excludes_refused_leaves(self):
        self.emp.version_ids.generate_work_entries(date(2022, 1, 1), date(2022, 1, 31))
        payslip = self.env["hr.payslip"].create(
            {
                "name": "toto payslip",
                "employee_id": self.emp.id,
                "date_from": "2022-01-01",
                "date_to": "2022-01-31",
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()

        leave = self.env["hr.leave"].new(
            {
                "name": "Tennis",
                "employee_id": self.emp.id,
                "holiday_status_id": self.leave_type.id,
                "request_date_from": date(2022, 1, 31),
                "request_date_to": date(2022, 1, 31),
                "request_hour_from": 7,
                "request_hour_to": 18,
            }
        )
        leave._compute_date_from_to()
        leave = self.env["hr.leave"].create(leave._convert_to_write(leave._cache))
        leave.action_approve()
        self.assertEqual(leave.payslip_state, "blocked", "Leave should be to defer")

        leave.sudo().action_refuse()
        self.assertEqual(leave.state, "refuse")
        self.assertEqual(
            leave.payslip_state,
            "blocked",
            "Refusing does not clear the payslip state, which is the whole point",
        )

        filter_node = etree.fromstring(
            self.env.ref("hr_payroll_holidays.hr_leave_view_search").arch
        ).xpath("//filter[@name='to_defer']")[0]
        listed = self.env["hr.leave"].search(literal_eval(filter_node.get("domain")))
        self.assertNotIn(leave, listed)
