import datetime

from odoo.tests import common, freeze_time

from odoo.addons.mail.tests.common import mail_new_test_user


@freeze_time("2020-01-01")
class TestTaskAbsences(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.tz = "Europe/Brussels"
        cls.user_a = mail_new_test_user(
            cls.env,
            login="absent_a",
            groups="base.group_user,hr_holidays.group_hr_holidays_user",
        )
        cls.employee_a = cls.env["hr.employee"].create(
            {"name": "Absent A", "user_id": cls.user_a.id, "tz": "UTC"}
        )
        cls.user_b = mail_new_test_user(
            cls.env,
            login="absent_b",
            groups="base.group_user,hr_holidays.group_hr_holidays_user",
        )
        cls.employee_b = cls.env["hr.employee"].create(
            {"name": "Absent B", "user_id": cls.user_b.id, "tz": "UTC"}
        )
        cls.leave_type = cls.env["hr.leave.type"].create(
            {
                "name": "absence",
                "requires_allocation": False,
                "request_unit": "hour",
            }
        )
        cls.project = cls.env["project.project"].create({"name": "Absences"})

    def _leave(self, employee, approve=True):
        leave = (
            self.env["hr.leave"]
            .sudo()
            .create(
                {
                    "holiday_status_id": self.leave_type.id,
                    "employee_id": employee.id,
                    "request_date_from": "2020-01-02",
                    "request_date_to": "2020-01-02",
                }
            )
        )
        if approve:
            leave.action_approve()
        return leave

    def _task(self, users, name="Planned task"):
        return self.env["project.task"].create(
            {
                "name": name,
                "project_id": self.project.id,
                "user_ids": users,
                "date_start": datetime.datetime(2020, 1, 2, 8, 0),
                "date_end": datetime.datetime(2020, 1, 2, 17, 0),
            }
        )

    def test_search_is_absent(self):
        self._leave(self.employee_a)
        absent_task = self._task(self.user_a)
        self._task(self.user_b, name="No leave task")

        found = self.env["project.task"].search([("is_absent", "=", True)])
        self.assertIn(absent_task, found)

    def test_multi_employee_warning(self):
        self._leave(self.employee_a)
        self._leave(self.employee_b)
        task = self._task(self.user_a | self.user_b)
        self.assertIn("are on time off", task.leave_warning)

        user_c = mail_new_test_user(
            self.env,
            login="absent_c",
            groups="base.group_user,hr_holidays.group_hr_holidays_user",
        )
        self.env["hr.employee"].create(
            {"name": "Absent C", "user_id": user_c.id, "tz": "UTC"}
        )
        partial = self._task(self.user_a | user_c, name="One on leave")
        self.assertIn("Absent A", partial.leave_warning)
        self.assertNotIn("Absent C", partial.leave_warning)
