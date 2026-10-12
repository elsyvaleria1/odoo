from datetime import datetime

from odoo.addons.hr_work_entry_attendance.tests.common import (
    HrWorkEntryAttendanceCommon,
)


class TestAttendanceActions(HrWorkEntryAttendanceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.struct_type = cls.env["hr.payroll.structure.type"].create(
            {"name": "Actions Structure Type", "wage_type": "hourly"}
        )
        cls.struct = cls.env["hr.payroll.structure"].create(
            {"name": "Actions Structure", "type_id": cls.struct_type.id}
        )
        cls.payslip = cls.env["hr.payslip"].create(
            {
                "name": "Actions Payslip",
                "employee_id": cls.employee.id,
                "struct_id": cls.struct.id,
                "date_from": "2024-01-01",
                "date_to": "2024-01-30",
            }
        )

    def test_attendance_count_and_action(self):
        attendances = self.env["hr.attendance"].create(
            [
                {
                    "employee_id": self.employee.id,
                    "check_in": datetime(2024, 1, 2, 8, 0),
                    "check_out": datetime(2024, 1, 2, 16, 0),
                },
                {
                    "employee_id": self.employee.id,
                    "check_in": datetime(2024, 1, 15, 8, 0),
                    "check_out": datetime(2024, 1, 15, 16, 0),
                },
            ]
        )
        self.payslip.invalidate_recordset(["attendance_count"])
        self.assertEqual(self.payslip.attendance_count, 2)

        action = self.payslip.action_view_attendances()
        self.assertEqual(action["res_model"], "hr.attendance")
        self.assertEqual(set(action["domain"][0][2]), set(attendances.ids))

    def test_attendance_count_non_attendance_source(self):
        employee = self.env["hr.employee"].create(
            {"name": "Calendar Employee", "wage": 10}
        )
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Calendar Payslip",
                "employee_id": employee.id,
                "struct_id": self.struct.id,
                "date_from": "2024-01-01",
                "date_to": "2024-01-30",
            }
        )
        self.env["hr.attendance"].create(
            {
                "employee_id": employee.id,
                "check_in": datetime(2024, 1, 10, 8, 0),
                "check_out": datetime(2024, 1, 10, 16, 0),
            }
        )
        self.assertNotEqual(payslip.version_id.work_entry_source, "attendance")
        payslip.invalidate_recordset(["attendance_count"])
        self.assertEqual(payslip.attendance_count, 0)

    def test_attendance_count_updates_on_work_entry_source_toggle(self):
        self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2024, 1, 10, 8, 0),
                "check_out": datetime(2024, 1, 10, 16, 0),
            }
        )
        self.assertEqual(self.payslip.attendance_count, 1)

        self.contract.work_entry_source = "calendar"
        self.assertEqual(self.payslip.attendance_count, 0)

        self.contract.work_entry_source = "attendance"
        self.assertEqual(self.payslip.attendance_count, 1)

    def test_open_attendances_rejects_multi_payslip(self):
        other = self.env["hr.payslip"].create(
            {
                "name": "Other Payslip",
                "employee_id": self.employee.id,
                "struct_id": self.struct.id,
                "date_from": "2024-02-01",
                "date_to": "2024-02-29",
            }
        )
        with self.assertRaisesRegex(ValueError, "Expected singleton"):
            (self.payslip | other).action_view_attendances()

    def test_overtime_worked_days_never_half_day(self):
        overtime_type = self.env.ref("hr_work_entry.work_entry_type_overtime")
        regular_type = self.env.ref("hr_work_entry.work_entry_type_attendance")
        overtime_wd, regular_wd = self.env["hr.payslip.worked_days"].create(
            [
                {
                    "payslip_id": self.payslip.id,
                    "work_entry_type_id": overtime_type.id,
                    "number_of_days": 0.5,
                    "number_of_hours": 2,
                },
                {
                    "payslip_id": self.payslip.id,
                    "work_entry_type_id": regular_type.id,
                    "number_of_days": 0.5,
                    "number_of_hours": 2,
                },
            ]
        )
        self.assertFalse(overtime_wd._is_half_day())
        self.assertTrue(regular_wd._is_half_day())
