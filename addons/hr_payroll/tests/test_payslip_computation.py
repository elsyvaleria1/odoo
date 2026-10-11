from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from dateutil.rrule import DAILY, rrule

from odoo.fields import Command, Date
from odoo.tests import Form, tagged

from odoo.addons.hr_payroll.tests.common import TestPayslipContractBase


@tagged("payslip_computation")
class TestPayslipComputation(TestPayslipContractBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env.user.group_ids |= cls.env.ref("hr_payroll.group_hr_payroll_manager")
        cls.richard_payslip = cls.env[
            "hr.payslip"
        ].create(
            {
                "name": "Payslip of Richard",
                "employee_id": cls.richard_emp.id,
                "version_id": cls.contract_cdi.id,
                "struct_id": cls.developer_pay_structure.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )
        cls.richard_emp.resource_calendar_id = cls.contract_cdi.resource_calendar_id

        cls.richard_payslip_quarter = cls.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard Quarter",
                "employee_id": cls.richard_emp.id,
                "version_id": cls.contract_cdi.id,
                "struct_id": cls.developer_pay_structure.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 3, 31),
            }
        )
        worked_days = (
            cls.richard_payslip + cls.richard_payslip_quarter
        ).worked_days_line_ids
        worked_days._compute_is_paid()
        worked_days.flush_model(["is_paid"])

    def _reset_work_entries(self, contract):
        self.env["hr.work.entry"].search(
            [("employee_id", "=", contract.employee_id.id)]
        ).unlink()
        now = datetime(2016, 1, 1, 0, 0, 0)
        contract.write(
            {
                "date_generated_from": now,
                "date_generated_to": now,
            }
        )

    def test_unpaid_amount(self):
        self.assertAlmostEqual(
            self.richard_payslip._get_unpaid_amount(),
            0,
            places=2,
            msg="It should be paid the full wage",
        )

        self._reset_work_entries(self.richard_payslip.version_id)
        self.env["resource.schedule.exception"].create(
            {
                "name": "Doctor Appointment",
                "date_from": datetime.strptime(
                    "2016-01-11 07:00:00", "%Y-%m-%d %H:%M:%S"
                ),
                "date_to": datetime.strptime(
                    "2016-01-11 18:00:00", "%Y-%m-%d %H:%M:%S"
                ),
                "resource_id": self.richard_emp.resource_id.id,
                "calendar_id": self.richard_emp.resource_calendar_id.id,
                "work_entry_type_id": self.work_entry_type_unpaid.id,
            }
        )

        self.richard_emp.version_ids.generate_work_entries(
            date(2016, 1, 1), date(2016, 2, 1)
        )
        self.richard_payslip._compute_worked_days_line_ids()
        self.assertAlmostEqual(
            self.richard_payslip._get_unpaid_amount(),
            238.11,
            delta=0.01,
            msg="It should be paid 238.11 less",
        )

    def test_worked_days_amount_with_unpaid(self):
        self.env["resource.schedule.exception"].create(
            {
                "name": "Doctor Appointment",
                "date_from": datetime.strptime(
                    "2016-01-11 07:00:00", "%Y-%m-%d %H:%M:%S"
                ),
                "date_to": datetime.strptime(
                    "2016-01-11 18:00:00", "%Y-%m-%d %H:%M:%S"
                ),
                "resource_id": self.richard_emp.resource_id.id,
                "calendar_id": self.richard_emp.resource_calendar_id.id,
                "work_entry_type_id": self.work_entry_type_leave.id,
            }
        )

        self.env["resource.schedule.exception"].create(
            {
                "name": "Unpaid Doctor Appointment",
                "date_from": datetime.strptime(
                    "2016-01-21 07:00:00", "%Y-%m-%d %H:%M:%S"
                ),
                "date_to": datetime.strptime(
                    "2016-01-21 18:00:00", "%Y-%m-%d %H:%M:%S"
                ),
                "resource_id": self.richard_emp.resource_id.id,
                "calendar_id": self.richard_emp.resource_calendar_id.id,
                "work_entry_type_id": self.work_entry_type_unpaid.id,
            }
        )

        self._reset_work_entries(self.richard_payslip.version_id)
        work_entries = self.richard_emp.version_ids.generate_work_entries(
            date(2016, 1, 1), date(2016, 2, 1)
        )
        work_entries.action_validate()

        self.richard_payslip._compute_worked_days_line_ids()
        work_days = self.richard_payslip.worked_days_line_ids

        self.assertAlmostEqual(
            sum(work_days.mapped("amount")),
            self.contract_cdi.wage - self.richard_payslip._get_unpaid_amount(),
        )

        leave_line = work_days.filtered(
            lambda l: l.code == self.work_entry_type_leave.code
        )
        self.assertAlmostEqual(
            leave_line.amount,
            238.11,
            delta=0.01,
            msg="His paid time off must be paid 238.11",
        )

        extra_attendance_line = work_days.filtered(
            lambda l: l.code == self.work_entry_type_unpaid.code
        )
        self.assertAlmostEqual(
            extra_attendance_line.amount,
            0.0,
            places=2,
            msg="His unpaid time off must be paid 0.",
        )

        attendance_line = work_days.filtered(
            lambda l: (
                l.code == self.env.ref("hr_work_entry.work_entry_type_attendance").code
            )
        )
        self.assertAlmostEqual(
            attendance_line.amount,
            4524.11,
            delta=0.01,
            msg="His attendance must be paid 4524.11",
        )

    def test_worked_days_with_unpaid(self):
        self.contract_cdi.resource_calendar_id = self.calendar_38h
        self.richard_emp.resource_calendar_id = self.calendar_38h

        for day in rrule(
            freq=DAILY,
            byweekday=[0, 1, 2, 3, 4],
            count=10,
            dtstart=datetime(2016, 2, 8),
        ):
            start = day + timedelta(hours=13.6)
            end = day + timedelta(hours=15.6)
            self.env["resource.schedule.exception"].create(
                {
                    "name": "Unpaid Leave",
                    "date_from": start,
                    "date_to": end,
                    "resource_id": self.richard_emp.resource_id.id,
                    "calendar_id": self.richard_emp.resource_calendar_id.id,
                    "work_entry_type_id": self.work_entry_type_unpaid.id,
                }
            )

        self._reset_work_entries(self.richard_payslip_quarter.version_id)
        work_entries = self.richard_emp.version_ids.generate_work_entries(
            date(2016, 1, 1), date(2016, 3, 31)
        )
        work_entries.action_validate()

        self.richard_payslip_quarter._compute_worked_days_line_ids()
        work_days = self.richard_payslip_quarter.worked_days_line_ids

        leave_line = work_days.filtered(
            lambda l: (
                l.code == self.env.ref("hr_work_entry.work_entry_type_attendance").code
            )
        )
        self.assertAlmostEqual(leave_line.number_of_days, 62.5, places=2)

        extra_attendance_line = work_days.filtered(
            lambda l: l.code == self.work_entry_type_unpaid.code
        )
        self.assertAlmostEqual(extra_attendance_line.number_of_days, 2.5, places=2)

    def test_worked_days_16h_with_unpaid(self):
        self.contract_cdi.resource_calendar_id = self.calendar_16h
        self.richard_emp.resource_calendar_id = self.calendar_16h

        for day in rrule(
            freq=DAILY, byweekday=3, count=5, dtstart=datetime(2016, 2, 4)
        ):
            start = day + timedelta(hours=12.5)
            end = day + timedelta(hours=14.5)
            self.env["resource.schedule.exception"].create(
                {
                    "name": "Unpaid Leave",
                    "date_from": start,
                    "date_to": end,
                    "resource_id": self.richard_emp.resource_id.id,
                    "calendar_id": self.richard_emp.resource_calendar_id.id,
                    "work_entry_type_id": self.work_entry_type_unpaid.id,
                }
            )
        self._reset_work_entries(self.richard_payslip_quarter.version_id)

        work_entries = self.richard_emp.version_ids.generate_work_entries(
            date(2016, 1, 1), date(2016, 3, 31)
        )
        work_entries.action_validate()

        self.richard_payslip_quarter._compute_worked_days_line_ids()
        work_days = self.richard_payslip_quarter.worked_days_line_ids

        leave_line = work_days.filtered(
            lambda l: (
                l.code == self.env.ref("hr_work_entry.work_entry_type_attendance").code
            )
        )
        self.assertAlmostEqual(leave_line.number_of_days, 49.5, places=2)

        extra_attendance_line = work_days.filtered(
            lambda l: l.code == self.work_entry_type_unpaid.code
        )
        self.assertAlmostEqual(extra_attendance_line.number_of_days, 2.5, places=2)

    def test_worked_days_38h_friday_with_unpaid(self):
        self.contract_cdi.resource_calendar_id = self.calendar_38h_friday_light
        self.richard_emp.resource_calendar_id = self.calendar_38h_friday_light

        for day in rrule(
            freq=DAILY, byweekday=4, count=5, dtstart=datetime(2016, 2, 4)
        ):
            start = day + timedelta(hours=7)
            end = day + timedelta(hours=11)
            self.env["resource.schedule.exception"].create(
                {
                    "name": "Unpaid Leave",
                    "date_from": start,
                    "date_to": end,
                    "resource_id": self.richard_emp.resource_id.id,
                    "calendar_id": self.richard_emp.resource_calendar_id.id,
                    "work_entry_type_id": self.work_entry_type_unpaid.id,
                }
            )

        self._reset_work_entries(self.richard_payslip_quarter.version_id)
        work_entries = self.richard_emp.version_ids.generate_work_entries(
            date(2016, 1, 1), date(2016, 3, 31)
        )
        work_entries.action_validate()

        self.richard_payslip_quarter._compute_worked_days_line_ids()
        work_days = self.richard_payslip_quarter.worked_days_line_ids

        leave_line = work_days.filtered(
            lambda l: (
                l.code == self.env.ref("hr_work_entry.work_entry_type_attendance").code
            )
        )
        self.assertAlmostEqual(leave_line.number_of_days, 62.5, places=2)

        extra_attendance_line = work_days.filtered(
            lambda l: l.code == self.work_entry_type_unpaid.code
        )
        self.assertAlmostEqual(extra_attendance_line.number_of_days, 2.5, places=2)

    def test_sum_category(self):
        self.richard_payslip.compute_sheet()
        self.richard_payslip.action_payslip_done()

        self.richard_payslip2 = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "struct_id": self.developer_pay_structure.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )
        self.richard_payslip2.compute_sheet()
        self.assertEqual(
            3010.13,
            self.richard_payslip2.line_ids.filtered(lambda x: x.code == "SUMALW").total,
        )

    def test_payslip_generation_with_extra_work(self):
        start = datetime(2015, 11, 1, 10, 0, 0)
        end = datetime(2015, 11, 1, 17, 0, 0)
        work_entries = self.contract_cdd.generate_work_entries(
            start.date(), (end + relativedelta(days=2)).date()
        )
        work_entries.action_validate()

        work_entry = self.env["hr.work.entry"].create(
            {
                "name": "Extra",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdd.id,
                "work_entry_type_id": self.work_entry_type.id,
                "date": start.date(),
                "duration": 7,
            }
        )
        work_entry.action_validate()
        payslip_run = self.env["hr.payslip.run"].create(
            {
                "date_start": Date.to_string(start),
                "date_end": Date.to_string(end + relativedelta(days=1)),
            }
        )

        payslip_run.generate_payslips(employee_ids=[self.richard_emp.id])

        payslip = self.env["hr.payslip"].search(
            [
                ("employee_id", "=", self.richard_emp.id),
                ("payslip_run_id", "=", payslip_run.id),
            ]
        )
        work_line = payslip.worked_days_line_ids.filtered(
            lambda l: (
                l.work_entry_type_id
                == self.env.ref("hr_work_entry.work_entry_type_attendance")
            )
        )
        extra_work_line = payslip.worked_days_line_ids.filtered(
            lambda l: l.work_entry_type_id == self.work_entry_type
        )

        self.assertTrue(work_line, "It should have a work line in the payslip")
        self.assertTrue(
            extra_work_line, "It should have an extra work line in the payslip"
        )
        self.assertEqual(
            work_line.number_of_hours, 8.0, "It should have 8 hours of work"
        )
        self.assertEqual(
            extra_work_line.number_of_hours, 7.0, "It should have 7 hours of extra work"
        )

    def test_payslip_generation_with_overtime_work_rate(self):
        self.env["hr.work.entry"].create(
            self.env["hr.version"]._generate_work_entries_postprocess(
                [
                    {
                        "name": "Overtime Work",
                        "employee_id": self.richard_emp.id,
                        "version_id": self.contract_cdi.id,
                        "work_entry_type_id": self.work_entry_type_overtime_duty.id,
                        "date_start": datetime(2024, 12, 16, 18, 0, 0),
                        "date_stop": datetime(2024, 12, 16, 22, 0, 0),
                    }
                ]
            )
        )
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "date_from": date(2024, 12, 1),
                "date_to": date(2024, 12, 31),
            }
        )
        payslip.compute_sheet()
        overtime_line = payslip.worked_days_line_ids.filtered(
            lambda l: l.work_entry_type_id == self.work_entry_type_overtime_duty
        )
        expected_hours = 4.0
        expected_amount = 64.93
        self.assertEqual(
            overtime_line.number_of_hours, expected_hours, "Overtime hours mismatch"
        )
        self.assertAlmostEqual(
            overtime_line.amount,
            expected_amount,
            delta=0.01,
            msg="Overtime amount calculation mismatch",
        )

    def test_work_data_with_exceeding_interval(self):
        entry_exceeding_lower_bound = self.env["hr.work.entry"].create(
            self.env["hr.version"]._generate_work_entries_postprocess(
                [
                    {
                        "name": "Attendance",
                        "employee_id": self.richard_emp.id,
                        "version_id": self.contract_cdd.id,
                        "work_entry_type_id": self.env.ref(
                            "hr_work_entry.work_entry_type_attendance"
                        ).id,
                        "date_start": datetime(2015, 12, 12, 18, 0),
                        "date_stop": datetime(2015, 12, 13, 2, 0),
                    }
                ]
            )
        )
        entry_exceeding_lower_bound.action_validate()
        self.contract_cdd.generate_work_entries(date(2015, 12, 13), date(2015, 12, 13))
        hours = self.contract_cdd.get_work_hours(date(2015, 12, 13), date(2015, 12, 13))
        sum_hours = sum(
            v
            for k, v in hours.items()
            if k in self.env.ref("hr_work_entry.work_entry_type_attendance").ids
        )
        self.assertAlmostEqual(
            sum_hours, 3, delta=0.01, msg="It should count 3 attendance hours"
        )
        entry_exceeding_upper_bound = self.env["hr.work.entry"].create(
            self.env["hr.version"]._generate_work_entries_postprocess(
                [
                    {
                        "name": "Attendance",
                        "employee_id": self.richard_emp.id,
                        "version_id": self.contract_cdd.id,
                        "work_entry_type_id": self.env.ref(
                            "hr_work_entry.work_entry_type_attendance"
                        ).id,
                        "date_start": datetime(2015, 12, 14, 18, 0),
                        "date_stop": datetime(2015, 12, 15, 2, 0),
                    }
                ]
            )
        )
        entry_exceeding_upper_bound.action_validate()
        self.contract_cdd.generate_work_entries(date(2015, 12, 14), date(2015, 12, 14))
        hours = self.contract_cdd.get_work_hours(date(2015, 12, 14), date(2015, 12, 14))
        sum_hours = sum(
            v
            for k, v in hours.items()
            if k in self.env.ref("hr_work_entry.work_entry_type_attendance").ids
        )
        self.assertAlmostEqual(
            sum_hours, 5, delta=0.01, msg="It should count 5 attendance hours"
        )

    def test_payslip_without_contract(self):
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "date_from": date(2015, 11, 1),
                "date_to": date(2015, 11, 30),
            }
        )
        self.assertTrue(payslip.version_id)
        payslip.version_id = False
        self.assertEqual(
            payslip._get_contract_wage(), 0, "It should have a default wage of 0"
        )
        self.assertEqual(payslip.basic_wage, 0, "It should have a default wage of 0")
        self.assertEqual(payslip.gross_wage, 0, "It should have a default wage of 0")
        self.assertEqual(payslip.net_wage, 0, "It should have a default wage of 0")

    def test_payslip_with_salary_attachment(self):
        self.env["hr.salary.attachment"].create(
            [
                {
                    "employee_ids": [(4, self.richard_emp.id)],
                    "monthly_amount": 150,
                    "other_input_type_id": self.env.ref(
                        "hr_payroll.input_child_support"
                    ).id,
                    "date_start": date(2016, 1, 1),
                    "description": "Child Support",
                },
                {
                    "employee_ids": [(4, self.richard_emp.id)],
                    "monthly_amount": 400,
                    "total_amount": 1000,
                    "paid_amount": 1000,
                    "other_input_type_id": self.env.ref(
                        "hr_payroll.input_assignment_salary"
                    ).id,
                    "date_start": date(2015, 1, 1),
                    "date_end": date(2015, 4, 1),
                    "description": "Unpaid fine",
                    "state": "close",
                },
            ]
        )

        car_accident = self.env["hr.salary.attachment"].create(
            {
                "employee_ids": [(4, self.richard_emp.id)],
                "monthly_amount": 250,
                "paid_amount": 1450,
                "total_amount": 1500,
                "other_input_type_id": self.env.ref(
                    "hr_payroll.input_attachment_salary"
                ).id,
                "date_start": date(2016, 1, 1),
                "description": "Car accident",
            }
        )

        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )
        input_lines = payslip.input_line_ids
        self.assertTrue(
            input_lines.filtered(lambda r: r.code == "CHILD_SUPPORT"),
            "There should be an input line for child support.",
        )
        self.assertTrue(
            input_lines.filtered(lambda r: r.code == "ATTACH_SALARY"),
            "There should be an input line for the car accident.",
        )
        self.assertTrue(
            input_lines.filtered(lambda r: r.code == "ATTACH_SALARY").amount <= 50,
            "The amount for the car accident input line should be 50 or less.",
        )
        self.assertFalse(
            input_lines.filtered(lambda r: r.code == "ASSIG_SALARY"),
            "There should not be an input line for the unpaid fine.",
        )
        payslip.compute_sheet()
        lines = payslip.line_ids
        self.assertTrue(
            lines.filtered(lambda r: r.code == "CHILD_SUPPORT"),
            "There should be a salary line for child support.",
        )
        self.assertTrue(
            lines.filtered(lambda r: r.code == "ATTACH_SALARY"),
            "There should be a salary line for car accident.",
        )
        payslip.action_payslip_done()
        payslip.action_payslip_paid()
        self.assertEqual(
            car_accident.state, "close", "The salary adjustment should be completed."
        )

    def test_payslip_with_multiple_input_same_type(self):
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )
        self.env["hr.payslip.input"].create(
            [
                {
                    "payslip_id": payslip.id,
                    "sequence": 1,
                    "input_type_id": self.env.ref("hr_payroll.BASIC").id,
                    "amount": 100,
                    "version_id": self.contract_cdi.id,
                },
                {
                    "payslip_id": payslip.id,
                    "sequence": 2,
                    "input_type_id": self.env.ref("hr_payroll.BASIC").id,
                    "amount": 200,
                    "version_id": self.contract_cdi.id,
                },
            ]
        )
        payslip.compute_sheet()
        lines = payslip.line_ids
        self.assertEqual(len(lines.filtered(lambda r: r.code == "BASIC")), 1)

    def test_payslip_with_multiple_input_same_type_aggregations(self):
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )
        self.env["hr.payslip.input"].create(
            [
                {
                    "payslip_id": payslip.id,
                    "sequence": 1,
                    "input_type_id": self.env.ref("hr_payroll.BASIC").id,
                    "amount": 300,
                    "version_id": self.contract_cdi.id,
                    "code": "DED",
                },
                {
                    "payslip_id": payslip.id,
                    "sequence": 1,
                    "input_type_id": self.env.ref("hr_payroll.BASIC").id,
                    "amount": 200,
                    "version_id": self.contract_cdi.id,
                    "code": "DED",
                },
            ]
        )
        self.developer_pay_structure.write(
            {
                "rule_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Test 1",
                            "sequence": 1000000,
                            "code": "TEST1",
                            "category_id": self.env.ref("hr_payroll.ALW").id,
                            "amount_select": "code",
                            "amount_python_compute": 'result = inputs["DEDUCTION"].amount',
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Test 2",
                            "sequence": 1000000,
                            "code": "TEST2",
                            "category_id": self.env.ref("hr_payroll.ALW").id,
                            "amount_select": "code",
                            "amount_python_compute": 'result = inputs["DEDUCTION"][0].amount + inputs["DEDUCTION"][1].amount',
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Test 3",
                            "sequence": 1000000,
                            "code": "TEST3",
                            "category_id": self.env.ref("hr_payroll.ALW").id,
                            "amount_select": "code",
                            "amount_python_compute": 'result = inputs["DEDUCTION"][0].amount',
                        },
                    ),
                ]
            }
        )
        payslip.compute_sheet()
        assert payslip.line_ids.filtered(lambda r: r.code == "TEST1").total == 500.00
        assert payslip.line_ids.filtered(lambda r: r.code == "TEST2").total == 500.00
        assert payslip.line_ids.filtered(lambda r: r.code == "TEST3").total == 300.00

    def test_payslip_with_multiple_input_same_type_no_matching_rule_aggregations(self):
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )
        input_type = self.env["hr.payslip.input.type"].create(
            {"name": "ABCD", "code": "ABCD"}
        )
        self.env["hr.payslip.input"].create(
            [
                {
                    "payslip_id": payslip.id,
                    "sequence": 1,
                    "input_type_id": input_type.id,
                    "amount": 300,
                    "version_id": self.contract_cdi.id,
                },
                {
                    "payslip_id": payslip.id,
                    "sequence": 2,
                    "input_type_id": input_type.id,
                    "amount": 200,
                    "version_id": self.contract_cdi.id,
                },
            ]
        )
        self.developer_pay_structure.write(
            {
                "rule_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Non matching code rule",
                            "sequence": 5,
                            "code": "EFGH",
                            "category_id": self.env.ref("hr_payroll.COMP").id,
                            "amount_select": "code",
                            "amount_python_compute": 'result = inputs["ABCD"].amount',
                        },
                    )
                ]
            }
        )
        payslip.compute_sheet()
        self.assertEqual(
            payslip.line_ids.filtered(lambda r: r.code == "EFGH").total, 500.00
        )

    def test_payslip_multiple_inputs_and_attachments_same_type(self):
        self.env["hr.salary.attachment"].create(
            [
                {
                    "employee_ids": [self.richard_emp.id],
                    "monthly_amount": 100,
                    "paid_amount": 0,
                    "total_amount": 100,
                    "other_input_type_id": self.env.ref(
                        "hr_payroll.default_attachment_of_salary_rule"
                    ).id,
                    "date_start": date(2016, 1, 1),
                    "description": "Some attachment",
                },
                {
                    "employee_ids": [self.richard_emp.id],
                    "monthly_amount": 200,
                    "paid_amount": 0,
                    "total_amount": 200,
                    "other_input_type_id": self.env.ref(
                        "hr_payroll.default_attachment_of_salary_rule"
                    ).id,
                    "date_start": date(2016, 1, 1),
                    "description": "Another attachment",
                },
            ]
        )

        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )

        with Form(payslip) as payslip_form:
            payslip_form.input_line_ids.remove(
                0
            )
            with payslip_form.input_line_ids.new() as line:
                line.input_type_id = self.env.ref("hr_payroll.input_assignment_salary")
                line.amount = 100
            with payslip_form.input_line_ids.new() as line:
                line.input_type_id = self.env.ref("hr_payroll.input_assignment_salary")
                line.amount = 200

        payslip.compute_sheet()
        payslip.action_payslip_done()
        payslip.action_payslip_paid()

        self.assertEqual(
            sum(s.paid_amount for s in payslip.salary_attachment_ids), 100 + 200
        )

    def test_defaultdict_get(self):
        self.developer_pay_structure.rule_ids.filtered(
            lambda r: r.code == "NET"
        ).amount_python_compute = "result = categories['BASIC'] + categories['ALW'] + categories['DED'] + categories.get('TEST')"
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "date_from": date(2015, 11, 1),
                "date_to": date(2015, 11, 30),
            }
        )
        payslip.compute_sheet()

    def test_payslip_warning_message_without_duration_dates(self):
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "date_from": date(2016, 1, 15),
                "date_to": date(2016, 1, 31),
            }
        )
        inaccurate = "The duration of the payslip is not accurate according to the structure type."
        self.assertIn(
            inaccurate, [issue["message"] for issue in payslip.issues.values()]
        )

        payslip_form = Form(payslip)
        payslip_form.date_from = date(
            2016, 1, 16
        )
        self.assertNotIn(
            inaccurate,
            [issue["message"] for issue in (payslip_form.issues or {}).values()],
        )

    def test_payslip_state_effect_on_work_entries(self):
        richard_work_entry = self.env["hr.work.entry"].create(
            {
                "name": "Extra",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdd.id,
                "work_entry_type_id": self.work_entry_type.id,
                "date": date(2016, 1, 1),
                "duration": 1,
            }
        )
        self.assertEqual(richard_work_entry.state, "draft")
        self.assertFalse(richard_work_entry.has_payslip, False)
        self.richard_payslip.action_payslip_done()
        self.assertEqual(richard_work_entry.state, "validated")
        self.assertEqual(richard_work_entry.has_payslip, True)
        richard_work_entry.write({"state": "draft"})
        self.assertEqual(
            richard_work_entry.state,
            "conflict",
            "Taken out of the payslip on its own, the entry shares its day with "
            "entries that are still validated, so it cannot be validated again "
            "until they are also reset; re-checking it on the way to draft says "
            "so immediately instead of at the next validation attempt.",
        )
        self.richard_payslip.action_payslip_cancel()
        self.assertEqual(richard_work_entry.state, "draft")

    def test_duplicate_payslips_cancellation(self):
        work_entries = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.richard_emp.id),
                ("date", ">=", self.richard_payslip.date_from),
                ("date", "<=", self.richard_payslip.date_to),
            ]
        )
        self.richard_payslip.action_payslip_done()
        self.assertTrue(all(entry.state == "validated" for entry in work_entries))

        dup_payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "struct_id": self.developer_pay_structure.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )
        dup_payslip.action_payslip_done()
        self.assertTrue(all(entry.state == "validated" for entry in work_entries))

        self.richard_payslip.action_payslip_cancel()
        self.assertTrue(all(entry.state == "validated" for entry in work_entries))

        dup_payslip.action_payslip_cancel()
        self.assertTrue(all(entry.state == "draft" for entry in work_entries))
        self.assertTrue(all(not entry.has_payslip for entry in work_entries))

    def test_out_of_contract_worked_days(self):
        self.contract_cdi.write(
            {
                "contract_date_start": datetime.strptime("2025-06-15", "%Y-%m-%d"),
                "contract_date_end": datetime.strptime("2025-07-15", "%Y-%m-%d"),
            }
        )
        payslips = self.env["hr.payslip"].create(
            [
                {
                    "name": "February",
                    "employee_id": self.richard_emp.id,
                    "version_id": self.contract_cdi.id,
                    "struct_id": self.developer_pay_structure.id,
                    "date_from": date(2025, 2, 1),
                    "date_to": date(2025, 2, 28),
                },
                {
                    "name": "June",
                    "employee_id": self.richard_emp.id,
                    "version_id": self.contract_cdi.id,
                    "struct_id": self.developer_pay_structure.id,
                    "date_from": date(2025, 6, 1),
                    "date_to": date(2025, 6, 30),
                },
                {
                    "name": "November",
                    "employee_id": self.richard_emp.id,
                    "version_id": self.contract_cdi.id,
                    "struct_id": self.developer_pay_structure.id,
                    "date_from": date(2025, 11, 1),
                    "date_to": date(2025, 11, 30),
                },
            ]
        )
        payslips._compute_worked_days_line_ids()
        expectations = {
            "February": (20.0, 140.0),
            "June": (10.0, 70.0),
            "November": (20.0, 140.0),
        }
        out_of_contract_code = self.env.ref(
            "hr_work_entry.hr_work_entry_type_out_of_contract"
        ).code
        for payslip in payslips:
            line = payslip.worked_days_line_ids.filtered(
                lambda l: l.code == out_of_contract_code
            )
            exp_days, exp_hours = expectations[payslip.name]
            self.assertAlmostEqual(
                line.number_of_days,
                exp_days,
                places=2,
                msg=f"Wrong days for {payslip.name}",
            )
            self.assertAlmostEqual(
                line.number_of_hours,
                exp_hours,
                places=2,
                msg=f"Wrong hours for {payslip.name}",
            )

    def test_out_of_contract_days_leave_out_attendances_typed_as_leave(self):
        calendar = self.contract_cdi.resource_calendar_id
        calendar.attendance_ids.filtered(lambda a: a.dayofweek == "4").write(
            {
                "work_entry_type_id": self.env.ref(
                    "hr_work_entry.work_entry_type_leave"
                ).id
            }
        )
        self.contract_cdi.write(
            {
                "contract_date_start": date(2025, 6, 15),
                "contract_date_end": date(2025, 7, 15),
            }
        )
        payslip = self.env["hr.payslip"].create(
            {
                "name": "June",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "struct_id": self.developer_pay_structure.id,
                "date_from": date(2025, 6, 1),
                "date_to": date(2025, 6, 30),
            }
        )
        payslip._compute_worked_days_line_ids()

        out_line = payslip.worked_days_line_ids.filtered(lambda l: l.code == "OUT")
        self.assertAlmostEqual(out_line.number_of_days, 8.0, places=2)
        self.assertAlmostEqual(out_line.number_of_hours, 56.0, places=2)

    def test_worked_days_name_with_detached_lines(self):
        payslip = self.env["hr.payslip"].new(
            {
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "struct_id": self.developer_pay_structure.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )
        detached = payslip.worked_days_line_ids
        self.assertTrue(detached, "The new payslip should have worked days lines")

        payslip.date_to = date(2016, 1, 15)
        lines = payslip.worked_days_line_ids
        self.assertTrue(lines, "Changing a dependency should rebuild the lines")
        self.assertFalse(
            detached & lines, "The previous lines should have been replaced"
        )
        self.assertFalse(detached.payslip_id, "The previous lines should be detached")

        self.assertTrue(all(lines.mapped("name")))
        self.assertEqual(
            detached.mapped("name"),
            detached.mapped("work_entry_type_id.name"),
            "A detached line has no calendar, so it falls back to its work entry type name",
        )

    def test_rule_without_category(self):
        bonus_rule = self.env["hr.salary.rule"].create(
            {
                "name": "Special Bonus",
                "sequence": 200,
                "amount_select": "fix",
                "amount_fix": 500.0,
                "code": "BONUS",
                "struct_id": self.developer_pay_structure.id,
            }
        )
        self.assertFalse(bonus_rule.category_id)

        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip with an uncategorised rule",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "struct_id": self.developer_pay_structure.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )
        payslip.compute_sheet()

        bonus_line = payslip.line_ids.filtered(lambda line: line.code == "BONUS")
        self.assertTrue(bonus_line, "The uncategorised rule should produce a line")
        self.assertEqual(bonus_line.total, 500.0)
        self.assertFalse(bonus_line.category_id)

    def test_rule_without_category_with_several_inputs_of_one_type(self):
        input_type = self.env["hr.payslip.input.type"].create(
            {"name": "Uncategorised Bonus", "code": "UNCAT"}
        )
        self.developer_pay_structure.input_line_type_ids = [Command.link(input_type.id)]
        rule = self.env["hr.salary.rule"].create(
            {
                "name": "Uncategorised Bonus",
                "sequence": 201,
                "code": "UNCAT",
                "struct_id": self.developer_pay_structure.id,
                "amount_select": "code",
                "amount_python_compute": (
                    "result = inputs['UNCAT'].amount if 'UNCAT' in inputs else 0.0"
                ),
            }
        )
        self.assertFalse(rule.category_id)

        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip with two inputs of one uncategorised rule",
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "struct_id": self.developer_pay_structure.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )
        for amount in (100.0, 150.0):
            self.env["hr.payslip.input"].create(
                {
                    "payslip_id": payslip.id,
                    "input_type_id": input_type.id,
                    "amount": amount,
                }
            )
        payslip.compute_sheet()

        lines = payslip.line_ids.filtered(lambda line: line.code == "UNCAT")
        self.assertTrue(
            lines, "The uncategorised multi-input rule should produce lines"
        )
        self.assertFalse(lines.category_id)
