from datetime import date, datetime

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import HrWorkEntryAttendanceCommon


@tagged("-at_install", "post_install", "work_entry_attendance")
class TestWorkentryAttendance(HrWorkEntryAttendanceCommon):
    def test_basic_generation(self):
        attendance_vals_list = []
        for i in range(1, 31):
            new_date = datetime(2021, 9, i, 13, 0, 0)
            if new_date.weekday() >= 5:
                continue
            attendance_vals_list.append(
                {
                    "employee_id": self.employee.id,
                    "check_in": new_date,
                    "check_out": new_date.replace(hour=17),
                }
            )
        attendances = self.env["hr.attendance"].create(attendance_vals_list)
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertFalse(work_entries)
        self.contract.generate_work_entries(date(2021, 9, 1), date(2021, 9, 30))
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(len(attendances), len(work_entries))
        self.assertTrue(all(hwe.attendance_id for hwe in work_entries))

    def test_lunch_time_case(self):
        week_day = datetime(2022, 9, 19, 8, 0, 0)
        weekend = datetime(2022, 9, 18, 8, 0, 0)
        attendances = self.env["hr.attendance"].create(
            [
                {
                    "employee_id": self.employee.id,
                    "check_in": week_day,
                    "check_out": week_day.replace(hour=20),
                },
                {
                    "employee_id": self.employee.id,
                    "check_in": weekend,
                    "check_out": weekend.replace(hour=20),
                },
            ]
        )
        attendances.action_approve_overtime()
        self.contract.generate_work_entries(date(2022, 9, 18), date(2022, 9, 19))
        sunday = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id), ("date", "<", week_day)]
        )

        monday = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id), ("date", ">=", week_day)]
        )

        self.assertEqual(len(sunday), 1)
        self.assertEqual(sunday.date, date(2022, 9, 18))
        self.assertEqual(sunday.duration, 12)

        self.assertEqual(len(monday), 2)
        attendance_type_id = self.env.ref("hr_work_entry.work_entry_type_attendance").id
        overtime_type_id = self.env.ref("hr_work_entry.work_entry_type_overtime").id
        monday_attendance_work_entry = monday.filtered_domain(
            [("work_entry_type_id", "=", attendance_type_id)]
        )
        monday_overtime_work_entry = monday.filtered_domain(
            [("work_entry_type_id", "=", overtime_type_id)]
        )
        self.assertEqual(monday_overtime_work_entry.date, date(2022, 9, 19))
        self.assertEqual(monday_overtime_work_entry.duration, 3)
        self.assertEqual(monday_attendance_work_entry.date, date(2022, 9, 19))
        self.assertEqual(monday_attendance_work_entry.duration, 8)

        self.contract.resource_calendar_id.schedule_type = "flexible"
        flex_day = datetime(2022, 9, 20, 8, 0, 0)
        attendance = self.env["hr.attendance"].create(
            [
                {
                    "employee_id": self.employee.id,
                    "check_in": flex_day,
                    "check_out": flex_day.replace(hour=20),
                },
            ]
        )
        attendance.action_approve_overtime()
        self.contract.generate_work_entries(date(2022, 9, 20), date(2022, 9, 21))
        tuesday = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id), ("date", ">=", flex_day)]
        )
        tuesday_attendance_work_entry = tuesday.filtered_domain(
            [("work_entry_type_id", "=", attendance_type_id)]
        )
        tuesday_overtime_work_entry = tuesday.filtered_domain(
            [("work_entry_type_id", "=", overtime_type_id)]
        )
        self.assertEqual(len(tuesday), 2)
        self.assertEqual(tuesday_attendance_work_entry.date, date(2022, 9, 20))
        self.assertEqual(tuesday_attendance_work_entry.duration, 8)
        self.assertEqual(tuesday_overtime_work_entry.date, date(2022, 9, 20))
        self.assertEqual(tuesday_overtime_work_entry.duration, 4)

    def test_timezones(self):
        self.employee.version_id.resource_calendar_id.tz = "Asia/Tokyo"
        self.employee.tz = "Asia/Tokyo"
        monday_morning_tokyo = datetime(
            2024, 10, 20, 22, 0, 0
        )
        self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": monday_morning_tokyo,
                "check_out": monday_morning_tokyo.replace(day=21, hour=7),
            }
        )
        self.contract.generate_work_entries(date(2024, 10, 21), date(2024, 10, 21))

        we = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("date", ">=", monday_morning_tokyo),
            ]
        )

        self.assertEqual(len(we), 1)
        self.assertEqual(we.date, date(2024, 10, 21))
        self.assertEqual(we.duration, 8)

    def test_attendance_within_period(self):
        boundaries_attendances = self.env["hr.attendance"].create(
            [
                {
                    "employee_id": self.employee.id,
                    "check_in": datetime(2021, 9, 1, 14, 0, 0),
                    "check_out": datetime(2021, 9, 1, 17, 0, 0),
                },
                {
                    "employee_id": self.employee.id,
                    "check_in": datetime(2021, 9, 30, 14, 0, 0),
                    "check_out": datetime(2021, 9, 30, 17, 0, 0),
                },
            ]
        )
        self.contract.generate_work_entries(date(2021, 9, 1), date(2021, 9, 30))
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(len(work_entries), len(boundaries_attendances))

        inner_attendance = self.env["hr.attendance"].create(
            [
                {
                    "employee_id": self.employee.id,
                    "check_in": datetime(2021, 9, 14, 14, 0, 0),
                    "check_out": datetime(2021, 9, 14, 17, 0, 0),
                }
            ]
        )
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(
            len(work_entries), len(boundaries_attendances) + len(inner_attendance)
        )

    @freeze_time("2021-09-01")
    def test_attendance_spanning_days(self):
        self.contract.write(
            {
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
                "resource_calendar_id": False,
            }
        )
        self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 10, 22, 0, 0),
                "check_out": datetime(2021, 9, 11, 6, 0, 0),
            }
        )
        self.env["hr.attendance"].create(
            [
                {
                    "employee_id": self.employee.id,
                    "check_in": datetime(2021, 9, 11, 22, 0, 0),
                    "check_out": datetime(2021, 9, 12, 6, 0, 0),
                },
                {
                    "employee_id": self.employee.id,
                    "check_in": datetime(2021, 9, 13, 22, 0, 0),
                    "check_out": datetime(2021, 9, 15, 6, 0, 0),
                },
            ]
        )
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(len(work_entries), 7)
        hours_by_day = {}
        for entry in work_entries:
            hours_by_day[entry.date.day] = (
                hours_by_day.get(entry.date.day, 0) + entry.duration
            )
        self.assertEqual(
            hours_by_day, {10: 2.0, 11: 8.0, 12: 6.0, 13: 2.0, 14: 24.0, 15: 6.0}
        )

    def test_unlink(self):
        self.contract.write(
            {
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        attendance = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 14, 0, 0),
                "check_out": datetime(2021, 9, 14, 17, 0, 0),
            }
        )
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        attendance.unlink()
        self.assertFalse(work_entries.active)

    def test_reopen_attendance_archives_work_entry(self):
        self.contract.write(
            {
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        attendance = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 8, 0, 0),
                "check_out": datetime(2021, 9, 14, 12, 0, 0),
            }
        )
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertTrue(work_entries)
        attendance.write({"check_out": False})
        self.assertFalse(work_entries.filtered("active"))

    def test_second_attendance_same_day_keeps_first_work_entry(self):
        self.contract.write(
            {
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 8, 0, 0),
                "check_out": datetime(2021, 9, 14, 12, 0, 0),
            }
        )
        afternoon = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 13, 0, 0),
            }
        )
        afternoon.write({"check_out": datetime(2021, 9, 14, 17, 0, 0)})
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(sum(work_entries.mapped("duration")), 8.0)

    def test_work_entries_exclude_refused_overtime(self):
        self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 1, 4, 6, 0),
                "check_out": datetime(2021, 1, 4, 9, 0),
            }
        )
        attendance = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 1, 4, 13, 0),
                "check_out": datetime(2021, 1, 4, 20, 0),
            }
        )
        attendance.action_refuse_overtime()
        work_entries = self.contract.generate_work_entries(
            date(2021, 1, 4), date(2021, 1, 4)
        )
        total_work_entry_duration = sum(
            work_entry.duration for work_entry in work_entries
        )
        self.assertEqual(
            total_work_entry_duration, self.employee.resource_calendar_id.hours_per_day
        )

    def test_fully_flexible_working_schedule_work_entries(self):
        employee = self.env["hr.employee"].create(
            {
                "name": "Test",
                "date_version": datetime(2024, 9, 1),
                "contract_date_start": datetime(2024, 9, 1),
                "contract_date_end": datetime(2024, 9, 30),
                "wage": 5000.0,
                "work_entry_source": "attendance",
                "resource_calendar_id": False,
                "ruleset_id": False,
            }
        )

        self.env["resource.schedule.exception"].sudo().create(
            {
                "resource_id": employee.resource_id.id,
                "date_from": datetime(2024, 9, 2),
                "date_to": datetime(2024, 9, 3),
            }
        )

        employee.generate_work_entries(datetime(2024, 9, 1), datetime(2024, 9, 30))
        result_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", employee.id)]
        )
        self.assertEqual(len(result_entries), 2, "Two work entries should be generated")

        self.env["hr.attendance"].create(
            {
                "employee_id": employee.id,
                "check_in": datetime(2024, 9, 14, 14, 0, 0),
                "check_out": datetime(2024, 9, 14, 17, 0, 0),
            }
        )
        employee.generate_work_entries(datetime(2024, 9, 1), datetime(2024, 9, 30))
        result_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", employee.id)]
        )
        self.assertEqual(len(result_entries), 3, "Two work entry should be generated")

    def test_gto_flexible_calendar(self):
        start = datetime(2018, 1, 1, 6, 0, 0)
        end = datetime(2018, 1, 1, 18, 0, 0)
        self.env["resource.schedule.exception"].create(
            {
                "date_from": start,
                "date_to": end,
                "work_entry_type_id": self.work_entry_type_leave.id,
            }
        )

        flexible_calendar = self.env["resource.calendar"].create(
            {
                "name": "flexible calendar",
                "schedule_type": "flexible",
                "full_time_required_hours": 40,
                "hours_per_day": 8,
            }
        )

        self.richard_emp.version_id.write(
            {
                "resource_calendar_id": flexible_calendar.id,
                "work_entry_source": "attendance",
            }
        )

        self.env["hr.attendance"].create(
            [
                {
                    "check_in": datetime(2018, 1, 1, 9, 0, 0),
                    "check_out": datetime(2018, 1, 1, 11, 0, 0),
                    "employee_id": self.richard_emp.id,
                },
                {
                    "check_in": datetime(2018, 1, 1, 13, 0, 0),
                    "check_out": datetime(2018, 1, 1, 15, 0, 0),
                    "employee_id": self.richard_emp.id,
                },
            ]
        )

        work_entries = self.richard_emp.version_ids.generate_work_entries(
            start.date(), end.date()
        )
        time_off_entries = work_entries.filtered(
            lambda entry: entry.code == "LEAVETEST100"
        )
        self.assertEqual(len(time_off_entries), 1)
        self.assertEqual(time_off_entries.duration, 8)
        self.assertEqual((work_entries - time_off_entries).duration, 4)

    def test_creating_attendance_regenerate_work_entry(self):
        self.contract.write(
            {
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 8, 0, 0),
                "check_out": datetime(2021, 9, 14, 12, 0, 0),
            }
        )

        work_entries1 = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )

        self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 14, 0, 0),
                "check_out": datetime(2021, 9, 14, 17, 0, 0),
            }
        )

        work_entries2 = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )

        self.assertNotEqual(work_entries1, work_entries2)
        self.assertTrue(work_entries1.active)
        self.assertEqual(sorted(work_entries2.mapped("duration")), [3.0, 4.0])

    def test_writing_attendance_regenerate_work_entry(self):
        self.contract.write(
            {
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        attendance = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 8, 0, 0),
                "check_out": datetime(2021, 9, 14, 12, 0, 0),
            }
        )

        work_entries1 = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )

        attendance.write({"check_out": datetime(2021, 9, 14, 17, 0, 0)})

        work_entries2 = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )

        self.assertNotEqual(work_entries1, work_entries2)
        self.assertFalse(work_entries1.active)
        self.assertTrue(work_entries2.active)
        self.assertEqual(work_entries2.duration, 8)

    def test_writing_attendance_employee_regenerate_work_entry(self):
        self.contract.write(
            {
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        self.richard_emp.version_id.write(
            {
                "work_entry_source": "attendance",
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        attendance = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 8, 0, 0),
                "check_out": datetime(2021, 9, 14, 12, 0, 0),
            }
        )

        old_work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id), ("date", "=", date(2021, 9, 14))]
        )
        self.assertTrue(old_work_entries)
        self.assertTrue(old_work_entries.active)

        attendance.write({"employee_id": self.richard_emp.id})

        self.assertFalse(
            old_work_entries.active,
            "the old employee's work entry must be archived on reassignment",
        )
        new_work_entries = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.richard_emp.id),
                ("date", "=", date(2021, 9, 14)),
            ]
        )
        self.assertTrue(new_work_entries, "the new employee must get a work entry")
        self.assertEqual(new_work_entries.attendance_id, attendance)

    def test_unlinking_regenerate_work_entry(self):
        self.contract.write(
            {
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        attendance1 = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 8, 0, 0),
                "check_out": datetime(2021, 9, 14, 12, 0, 0),
            }
        )

        self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 14, 0, 0),
                "check_out": datetime(2021, 9, 14, 17, 0, 0),
            }
        )

        work_entries1 = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )

        attendance1.unlink()
        work_entries2 = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )

        self.assertNotEqual(work_entries1, work_entries2)
        self.assertFalse(any(work_entries1.mapped("active")))
        self.assertTrue(work_entries2.active)
        self.assertEqual(work_entries2.duration, 3)

    def test_fully_flexible_employee_overlapping_leaves(self):
        fully_flexible_emp = self.env["hr.employee"].create(
            {
                "name": "Flexible Employee",
                "date_version": datetime(2025, 6, 1).date(),
                "contract_date_start": datetime(2025, 6, 1).date(),
                "wage": 5000.0,
                "work_entry_source": "attendance",
                "resource_calendar_id": False,
            }
        )

        sick_leave_type = self.env["hr.work.entry.type"].search(
            [("code", "=", "LEAVE110")], limit=1
        )

        self.env["resource.schedule.exception"].create(
            [
                {
                    "name": "Sick Leave",
                    "date_from": datetime(2025, 6, 25),
                    "date_to": datetime(2025, 6, 29),
                    "resource_id": fully_flexible_emp.resource_id.id,
                    "work_entry_type_id": sick_leave_type.id,
                },
                {
                    "name": "Public Holiday",
                    "date_from": datetime(2025, 6, 27),
                    "date_to": datetime(2025, 6, 27, 23, 59, 59),
                    "calendar_id": False,
                    "work_entry_type_id": self.work_entry_type_leave.id,
                },
            ]
        )

        fully_flexible_emp.generate_work_entries(
            datetime(2025, 6, 25).date(), datetime(2025, 6, 29).date()
        )

    def test_approval_refusal_overtime_regenerates_work_entries_permission(self):
        user = new_test_user(self.env, login="user1", groups="base.group_user")
        self.employee.user_id = user.id

        attendance1 = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 13, 8, 0, 0),
                "check_out": datetime(2021, 9, 13, 20, 0, 0),
            }
        )

        with self.assertRaises(AccessError):
            self.assertTrue(
                attendance1.linked_overtime_ids,
                "There should be at least one linked overtime line created",
            )
            attendance1.linked_overtime_ids[0].with_user(user).action_approve()
            attendance1.linked_overtime_ids[0].with_user(user).action_refuse()

        self.employee.attendance_manager_id = user.id
        self.assertTrue(
            user.has_group("hr_attendance.group_hr_attendance_officer"),
            "User must be attendance officer to approve/refuse overtime",
        )

        attendance2 = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 8, 0, 0),
                "check_out": datetime(2021, 9, 14, 20, 0, 0),
            }
        )

        self.assertTrue(
            attendance2.linked_overtime_ids,
            "There should be at least one linked overtime line created",
        )
        attendance2.linked_overtime_ids[0].with_user(user).action_approve()
        attendance2.linked_overtime_ids[0].with_user(user).action_refuse()

    def test_no_overtime_work_entry_when_no_paid_rules(self):
        ruleset = self.env["hr.attendance.overtime.ruleset"].create(
            {
                "name": "Unpaid Ruleset",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "Unpaid Rule",
                            "base_off": "quantity",
                            "expected_hours_from_contract": True,
                            "quantity_period": "day",
                            "paid": False,
                        }
                    )
                ],
            }
        )
        self.employee.ruleset_id = ruleset
        attendance = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2025, 1, 10, 8, 0),
                "check_out": datetime(2025, 1, 10, 20, 0),
            }
        )
        self.employee.generate_work_entries(attendance.date, attendance.date)
        work_entries = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("date", "=", attendance.date),
                ("work_entry_type_id.code", "=", "OVERTIME"),
            ]
        )

        self.assertFalse(
            work_entries, "OVERTIME work entries must NOT be created when paid=False"
        )

    def test_overtime_work_entry_created_when_paid_rule_present(self):
        ruleset = self.env["hr.attendance.overtime.ruleset"].create(
            {
                "name": "Paid Ruleset",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "Paid Rule",
                            "base_off": "quantity",
                            "expected_hours_from_contract": True,
                            "quantity_period": "day",
                            "paid": True,
                        }
                    ),
                ],
            }
        )
        self.employee.ruleset_id = ruleset
        attendance = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2025, 1, 10, 8, 0),
                "check_out": datetime(2025, 1, 10, 20, 0),
            }
        )
        overtime = self.env["hr.attendance.overtime.line"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("date", "=", attendance.date),
            ]
        )
        self.assertTrue(overtime, "Overtime line SHOULD be created with paid rule")
        expected_hours = self.employee.resource_calendar_id.hours_per_day
        expected_overtime = 12 - expected_hours - 1
        self.assertEqual(
            overtime.duration,
            expected_overtime,
            f"Overtime duration should be {expected_overtime}",
        )

        self.employee.generate_work_entries(attendance.date, attendance.date)
        work_entry = self.env["hr.work.entry"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("date", "=", attendance.date),
                ("work_entry_type_id.code", "=", "OVERTIME"),
            ]
        )
        self.assertEqual(len(work_entry), 1)
        self.assertEqual(
            work_entry.duration,
            overtime.duration,
            "OVERTIME work entry duration should match overtime duration",
        )

    def test_ruleset_excludes_attendance_with_validated_work_entry(self):
        self.contract.write(
            {
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        attendance = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2021, 9, 14, 8, 0, 0),
                "check_out": datetime(2021, 9, 14, 12, 0, 0),
            }
        )
        work_entry = self.env["hr.work.entry"].search(
            [("attendance_id", "=", attendance.id)]
        )
        self.assertTrue(work_entry)

        self.assertIn(
            attendance,
            self.ruleset._attendances_to_regenerate_for(),
            "a draft-state work entry must not be excluded",
        )

        work_entry.sudo().write({"state": "validated"})

        self.assertNotIn(
            attendance,
            self.ruleset._attendances_to_regenerate_for(),
            "an attendance linked to a validated work entry must be excluded",
        )

    def test_multiple_overtime_lines_distribution_multiday_attendance(self):

        ruleset = self.env["hr.attendance.overtime.ruleset"].create(
            {
                "name": "Timing Ruleset",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "Outside schedule rule",
                            "base_off": "timing",
                            "timing_type": "schedule",
                            "resource_calendar_id": self.env.company.resource_calendar_id.id,
                            "paid": True,
                        }
                    ),
                ],
            }
        )

        calendar_employee = self.env["hr.employee"].create(
            {
                "name": "Calendar Employee",
                "tz": "UTC",
                "work_entry_source": "calendar",
                "date_version": "2020-01-01",
                "contract_date_start": "2020-01-01",
                "wage": 3500,
                "ruleset_id": ruleset.id,
            }
        )

        attendance = self.env["hr.attendance"].create(
            {
                "employee_id": calendar_employee.id,
                "check_in": datetime(2025, 12, 22, 0, 0),
                "check_out": datetime(2025, 12, 26, 6, 30),
            }
        )

        overtime_lines = self.env["hr.attendance.overtime.line"].search(
            [
                ("employee_id", "=", calendar_employee.id),
                ("date", ">=", date(2025, 12, 22)),
                ("date", "<=", date(2025, 12, 26)),
            ]
        )

        overtime_lines.action_approve()

        attendance.write(
            {
                "check_out": datetime(2025, 12, 27, 6, 30),
            }
        )

        overtime_lines = self.env["hr.attendance.overtime.line"].search(
            [
                ("employee_id", "=", calendar_employee.id),
                ("date", ">=", date(2025, 12, 22)),
                ("date", "<=", date(2025, 12, 27)),
            ]
        )
        overtime_lines.action_approve()

        start_date = date(2025, 12, 22)
        end_date = date(2025, 12, 27)
        calendar_employee.generate_work_entries(start_date, end_date)
