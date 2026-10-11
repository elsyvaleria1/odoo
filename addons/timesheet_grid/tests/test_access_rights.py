from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import new_test_user

from odoo.addons.hr_timesheet.tests.test_timesheet import TestCommonTimesheet


class TestAccessRightsTimesheetGrid(TestCommonTimesheet):
    def setUp(self):
        super().setUp()

        self.user_approver = new_test_user(
            self.env, "user_approver", groups="hr_timesheet.group_hr_timesheet_approver"
        )

        self.empl_approver = self.env["hr.employee"].create(
            {
                "name": "Empl Approver 1",
                "user_id": self.user_approver.id,
                "timesheet_manager_id": self.user_manager.id,
            }
        )

        self.user_approver2 = new_test_user(
            self.env,
            "user_approver2",
            groups="hr_timesheet.group_hr_timesheet_approver",
        )

        self.empl_approver2 = self.env["hr.employee"].create(
            {
                "name": "Empl Approver 2",
                "user_id": self.user_approver2.id,
                "timesheet_manager_id": self.user_approver.id,
            }
        )

        self.empl_employee.write({"timesheet_manager_id": self.user_approver.id})

        today = fields.Date.today()

        self.timesheet = (
            self.env["account.analytic.line"]
            .with_user(self.user_approver)
            .create(
                {
                    "name": "My timesheet 1",
                    "project_id": self.project_customer.id,
                    "task_id": self.task2.id,
                    "date": today - timedelta(days=1),
                    "unit_amount": 2,
                    "employee_id": self.empl_employee.id,
                }
            )
        )

        self.user_employee3 = new_test_user(
            self.env, "user_employee3", groups="hr_timesheet.group_hr_timesheet_user"
        )

        self.empl_employee3 = self.env["hr.employee"].create(
            {
                "name": "User Empl Employee 3",
                "user_id": self.user_employee3.id,
                "timesheet_manager_id": self.user_approver.id,
            }
        )

        self.timesheet2 = (
            self.env["account.analytic.line"]
            .with_user(self.user_approver)
            .create(
                {
                    "name": "My timesheet 4",
                    "project_id": self.project_customer.id,
                    "task_id": self.task1.id,
                    "date": today - timedelta(days=1),
                    "unit_amount": 2,
                    "employee_id": self.empl_employee3.id,
                }
            )
        )

        self.timesheet3 = (
            self.env["account.analytic.line"]
            .with_user(self.user_manager)
            .create(
                {
                    "name": "My old timesheet",
                    "project_id": self.project_customer.id,
                    "task_id": self.task1.id,
                    "date": today - timedelta(days=10),
                    "unit_amount": 2,
                    "employee_id": self.empl_employee3.id,
                }
            )
        )

        self.timesheet4 = (
            self.env["account.analytic.line"]
            .with_user(self.user_manager)
            .create(
                {
                    "name": "My old timesheet 2",
                    "project_id": self.project_customer.id,
                    "task_id": self.task1.id,
                    "date": today - timedelta(days=10),
                    "unit_amount": 2,
                    "employee_id": self.empl_employee2.id,
                }
            )
        )

        self.project_follower = self.env["project.project"].create(
            {
                "name": "Project with visibility set on 'Invited employees'",
                "allow_timesheets": True,
                "privacy_visibility": "followers",
            }
        )
        self.project_follower.member_user_ids = (
            self.user_approver | self.user_employee | self.user_manager
        )

        self.timesheet_approver2 = (
            self.env["account.analytic.line"]
            .with_user(self.user_approver2)
            .create(
                {
                    "name": "Timesheet Approver2",
                    "project_id": self.project_customer.id,
                    "task_id": self.task1.id,
                    "date": today - timedelta(days=1),
                    "unit_amount": 1,
                    "employee_id": self.empl_approver2.id,
                }
            )
        )

        self.user_employee4 = new_test_user(
            self.env, "user_employee4", groups="hr_timesheet.group_hr_timesheet_user"
        )

        self.empl_employee4 = self.env["hr.employee"].create(
            {
                "name": "User Empl Employee 4",
                "user_id": self.user_employee4.id,
            }
        )

        self.timesheet5 = (
            self.env["account.analytic.line"]
            .with_user(self.user_approver)
            .create(
                {
                    "name": "My timesheet 5",
                    "project_id": self.project_customer.id,
                    "task_id": self.task1.id,
                    "date": today - timedelta(days=1),
                    "unit_amount": 2,
                    "employee_id": self.empl_employee4.id,
                }
            )
        )

    def test_access_rights_for_employee(self):
        timesheet_user1 = (
            self.env["account.analytic.line"]
            .with_user(self.user_employee)
            .create(
                {
                    "project_id": self.project_customer.id,
                    "task_id": self.task1.id,
                    "name": "timesheet for employee 1",
                    "unit_amount": 1,
                }
            )
        )

        with self.assertRaises(AccessError):
            timesheet_user1.with_user(self.user_employee2).read([])

            timesheet_user1.with_user(self.user_employee2).write({"unit_amount": 0.5})

            timesheet_user1.with_user(self.user_employee2).unlink()

            self.env["account.analytic.line"].with_user(self.user_employee).create(
                {
                    "project_id": self.project_customer.id,
                    "task_id": self.task1.id,
                    "name": "a second timesheet for employee 2",
                    "unit_amount": 8,
                    "employee_id": self.empl_employee2.id,
                }
            )

        timesheet_user1.with_user(self.user_employee).write({"unit_amount": 5})

        self.assertEqual(timesheet_user1.unit_amount, 5)

        timesheet_user1.with_user(self.user_employee).unlink()

    def test_access_rights_for_approver(self):
        timesheet_user1 = self.env["account.analytic.line"].create(
            {
                "project_id": self.project_customer.id,
                "task_id": self.task1.id,
                "name": "timesheet for employee 1",
                "unit_amount": 1,
                "employee_id": self.empl_employee.id,
            }
        )

        res = timesheet_user1.with_user(self.user_approver).read(["name"])
        self.assertEqual(timesheet_user1.name, res[0]["name"])

        timesheet_user1.with_user(self.user_approver).write({"unit_amount": 5})
        self.assertEqual(timesheet_user1.unit_amount, 5)

        timesheet_user1.with_user(self.user_approver).unlink()

    def test_access_rights_for_manager(self):
        timesheet_user1 = self.env["account.analytic.line"].create(
            {
                "project_id": self.project_customer.id,
                "task_id": self.task1.id,
                "name": "timesheet for employee 1",
                "unit_amount": 1,
                "employee_id": self.empl_employee.id,
            }
        )

        res = timesheet_user1.with_user(self.user_manager).read(["name"])
        self.assertEqual(timesheet_user1.name, res[0]["name"])

        timesheet_user1.with_user(self.user_manager).write({"unit_amount": 5})
        self.assertEqual(timesheet_user1.unit_amount, 5)

        timesheet_user1.with_user(self.user_manager).unlink()

    def test_timesheet_validation_approver_and_invalidate(self):
        timesheet_to_validate = self.timesheet
        timesheet_to_validate.with_user(self.user_approver).action_validate_timesheet()
        self.assertTrue(timesheet_to_validate.validated)
        timesheet_to_validate.with_user(
            self.user_approver
        ).action_invalidate_timesheet()
        self.assertFalse(timesheet_to_validate.validated)

    def test_timesheet_validation_approver_own_timesheet(self):
        timesheet_to_validate = self.timesheet_approver2
        timesheet_to_validate.with_user(self.user_approver2).action_validate_timesheet()
        self.assertFalse(timesheet_to_validate.validated)
        timesheet_to_validate.with_user(self.user_approver).action_validate_timesheet()
        self.assertTrue(timesheet_to_validate.validated)

    def test_timesheet_validation_by_approver_when_he_is_not_responsible(self):
        timesheet_to_validate = self.timesheet2

        res = timesheet_to_validate.with_user(
            self.user_approver2
        ).action_validate_timesheet()
        self.assertEqual(res["params"]["type"], "danger")
        self.assertEqual(timesheet_to_validate.validated, False)

    def test_timesheet_validation_by_approver_when_he_is_manager_of_employee(self):
        timesheet_to_validate = self.timesheet2
        timesheet_to_validate.with_user(self.user_approver).action_validate_timesheet()
        self.assertEqual(timesheet_to_validate.validated, True)

    def test_show_timesheet_only_if_user_follow_project(self):
        Timesheet = self.env["account.analytic.line"]
        timesheet = Timesheet.with_user(self.user_manager).create(
            {"project_id": self.project_follower.id, "name": "/"}
        )

        with self.assertRaises(AccessError):
            timesheet.with_user(self.user_employee).read()
            timesheet.with_user(self.user_approver).read()

    def test_employee_update_validated_timesheet(self):
        timesheet_to_validate = self.timesheet
        timesheet_to_validate.with_user(self.user_approver).action_validate_timesheet()
        self.assertEqual(self.timesheet.validated, True)
        with self.assertRaises(AccessError):
            self.timesheet.with_user(self.user_employee).write({"unit_amount": 10})

        self.assertEqual(self.timesheet.unit_amount, 2)

    def test_employee_validate_timesheet(self):
        timesheet_to_validate = self.timesheet
        res = timesheet_to_validate.with_user(
            self.user_employee
        ).action_validate_timesheet()
        self.assertEqual(res["params"]["type"], "danger")
        self.assertEqual(self.timesheet.validated, False)

    def test_employee_read_timesheet_of_other_employee(self):
        with self.assertRaises(AccessError):
            self.timesheet.with_user(self.user_employee3).read([])
            self.timesheet.with_user(self.user_employee2).read([])

        res = self.timesheet.with_user(self.user_employee).read(["name"])
        self.assertEqual(res[0]["name"], "My timesheet 1")

    def test_last_validated_timesheet_date(self):
        self.assertFalse(self.empl_employee3.last_validated_timesheet_date)
        timesheet = (
            self.env["account.analytic.line"]
            .with_user(self.user_employee3)
            .create(
                {
                    "name": "timesheet",
                    "project_id": self.project_customer.id,
                    "task_id": self.task1.id,
                    "date": fields.Datetime.today() - timedelta(days=40),
                    "unit_amount": 2,
                    "employee_id": self.empl_employee3.id,
                }
            )
        )
        timesheet.with_user(self.user_approver).action_validate_timesheet()

        self.assertEqual(
            self.empl_employee3.last_validated_timesheet_date, timesheet.date
        )
        timesheet.with_user(self.user_approver).action_invalidate_timesheet()
        self.assertFalse(self.empl_employee3.last_validated_timesheet_date)

        yesterday = fields.Date.today() - timedelta(days=1)
        timesheet1 = (
            self.env["account.analytic.line"]
            .with_user(self.user_employee3)
            .create(
                {
                    "name": "timesheet 1",
                    "project_id": self.project_customer.id,
                    "task_id": self.task1.id,
                    "date": yesterday,
                    "unit_amount": 2,
                    "employee_id": self.empl_employee3.id,
                }
            )
        )
        self.timesheet4.write({"date": self.timesheet2.date})
        (
            self.timesheet3 + self.timesheet2 + self.timesheet4
        ).action_validate_timesheet()
        self.assertEqual(
            self.empl_employee3.last_validated_timesheet_date,
            max(self.timesheet3.date, self.timesheet2.date),
        )

        with self.assertRaises(AccessError):
            timesheet1.unlink()

        with self.assertRaises(AccessError):
            self.env["account.analytic.line"].with_user(self.user_employee3).create(
                {
                    "name": "timesheet",
                    "project_id": self.project_customer.id,
                    "task_id": self.task1.id,
                    "date": fields.Datetime.today() - timedelta(days=10),
                    "unit_amount": 2,
                    "employee_id": self.empl_employee3.id,
                }
            )

        timesheet = (
            self.env["account.analytic.line"]
            .with_user(self.user_employee3)
            .create(
                {
                    "name": "timesheet",
                    "project_id": self.project_customer.id,
                    "task_id": self.task1.id,
                    "date": fields.Datetime.today() + timedelta(days=10),
                    "unit_amount": 2,
                    "employee_id": self.empl_employee3.id,
                }
            )
        )

        with self.assertRaises(AccessError):
            timesheet.with_user(self.user_employee3).write(
                {
                    "date": fields.Datetime.today() - timedelta(days=10),
                }
            )

        timesheet.with_user(self.user_approver).action_validate_timesheet()
        self.assertEqual(self.empl_employee3.last_validated_timesheet_date, yesterday)

        (timesheet + self.timesheet2 + self.timesheet4).with_user(
            self.user_approver
        ).action_invalidate_timesheet()
        self.assertEqual(
            self.empl_employee3.last_validated_timesheet_date, self.timesheet3.date
        )

        self.timesheet3.with_user(self.user_approver).action_invalidate_timesheet()
        self.assertFalse(self.empl_employee3.last_validated_timesheet_date)

    def test_old_timesheet(self):
        today = fields.Date.today()
        timesheet1, timesheet2, timesheet3, timesheet4 = (
            self.env["account.analytic.line"]
            .with_user(self.user_employee3)
            .create(
                [
                    {
                        "name": "Timesheet1",
                        "project_id": self.project_customer.id,
                        "task_id": self.task1.id,
                        "unit_amount": 2,
                        "employee_id": self.empl_employee3.id,
                    },
                    {
                        "name": "Timesheet2",
                        "project_id": self.project_customer.id,
                        "task_id": self.task1.id,
                        "date": today - timedelta(days=2),
                        "unit_amount": 2,
                        "employee_id": self.empl_employee3.id,
                    },
                    {
                        "name": "Timesheet3",
                        "project_id": self.project_customer.id,
                        "task_id": self.task1.id,
                        "date": today - timedelta(days=1),
                        "unit_amount": 2,
                        "employee_id": self.empl_employee3.id,
                    },
                    {
                        "name": "Timesheet4",
                        "project_id": self.project_customer.id,
                        "task_id": self.task1.id,
                        "date": today,
                        "unit_amount": 2,
                        "employee_id": self.empl_employee3.id,
                    },
                ]
            )
        )

        timesheet1.with_user(self.user_employee3).action_timer_start()
        timesheet1.write(
            {"date": today - timedelta(days=3)}
        )
        self.assertTrue(timesheet1.is_timer_running)
        timesheet2.with_user(self.user_approver).action_validate_timesheet()
        self.assertFalse(timesheet1.is_timer_running)

        timesheet1.with_user(self.user_employee3).action_timer_start()
        self.assertFalse(timesheet1.is_timer_running)
        timesheet5 = self.env["account.analytic.line"].search(
            [
                ("employee_id", "=", self.empl_employee3.id),
                ("is_timer_running", "=", True),
            ]
        )
        self.assertEqual(len(timesheet5), 1)
        self.assertEqual(timesheet5.project_id, self.project_customer)
        self.assertEqual(timesheet5.task_id, self.task1)
        self.assertEqual(timesheet5.date, today)

        timesheet5.with_user(self.user_employee3).action_timer_stop()
        self.assertFalse(timesheet5.is_timer_running)

        timesheet4.with_user(self.user_employee3).action_timer_start()
        self.assertTrue(timesheet4.is_timer_running)
        timesheet3.with_user(self.user_approver).action_validate_timesheet()
        self.assertTrue(timesheet4.is_timer_running)

    def test_approve_user_without_approver_and_parents(self):
        timesheet_to_validate = self.timesheet5
        timesheet_to_validate.with_user(self.user_approver).action_validate_timesheet()
        self.assertEqual(timesheet_to_validate.validated, True)

    def test_update_timesheet_from_archived_employee(self):
        self.empl_employee3.active = False
        self.assertEqual(
            self.timesheet2.employee_id,
            self.empl_employee3,
            "The timesheet should be for the archived employee",
        )
        self.assertEqual(
            self.timesheet2.unit_amount, 2, "The timesheet should have 2 hours"
        )
        self.assertEqual(
            self.timesheet2.validated, False, "The timesheet should not be validated"
        )
        self.timesheet2.with_user(self.user_approver).write({"unit_amount": 3})
        self.assertEqual(
            self.timesheet2.unit_amount, 3, "The timesheet should have 3 hours"
        )

        self.timesheet2.with_user(self.user_approver).action_validate_timesheet()
        self.assertEqual(
            self.timesheet2.validated, True, "The timesheet should be validated"
        )
        self.timesheet2.with_user(self.user_approver).write({"unit_amount": 4})
        self.assertEqual(
            self.timesheet2.unit_amount, 4, "The timesheet should have 4 hours"
        )

    def test_recursive_approver_validation(self):

        self.assertFalse(
            self.empl_approver.user_id.has_group("hr_timesheet.group_timesheet_manager")
        )
        self.assertFalse(
            self.empl_approver2.user_id.has_group(
                "hr_timesheet.group_timesheet_manager"
            )
        )

        self.empl_employee.parent_id = self.empl_approver2
        self.empl_employee.timesheet_manager_id = self.empl_approver2.user_id
        self.empl_approver2.parent_id = self.empl_approver
        self.empl_approver2.timesheet_manager_id = self.empl_approver.user_id

        self.assertEqual(self.timesheet.employee_id, self.empl_employee)

        self.timesheet.with_user(self.user_approver).action_validate_timesheet()

        self.timesheet.with_user(self.user_approver).date = (
            fields.Date.today() - timedelta(days=2)
        )
