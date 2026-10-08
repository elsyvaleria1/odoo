from datetime import datetime

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user

PRIVILEGE = "project_enterprise_hr.privilege_book_employee_tasks"


class TestBookEmployeeTasks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hr_officer = new_test_user(
            cls.env,
            login="booking_hr_officer",
            groups="base.group_user,hr.group_hr_user",
        )
        cls.assignee = new_test_user(cls.env, login="booking_assignee")
        project = cls.env["project.project"].create(
            {"name": "Members only", "privacy_visibility": "followers"}
        )
        dates = {
            "date_start": datetime(2026, 10, 5, 8),
            "date_end": datetime(2026, 10, 5, 12),
        }
        Task = cls.env["project.task"].with_context(tracking_disable=True)
        cls.dated_task = Task.create(
            {
                "name": "Dated",
                "project_id": project.id,
                "user_ids": cls.assignee.ids,
                **dates,
            }
        )
        cls.archived_task = Task.create(
            {
                "name": "Archived",
                "project_id": project.id,
                "user_ids": cls.assignee.ids,
                "active": False,
                **dates,
            }
        )
        cls.undated_task = Task.create(
            {"name": "Undated", "project_id": project.id, "user_ids": cls.assignee.ids}
        )
        cls.unassigned_task = Task.create(
            {"name": "Unassigned", "project_id": project.id, "user_ids": False, **dates}
        )

    def _active_resources(self, task):
        return (
            self.env["resource.reservation"]
            .sudo()
            .search([("res_model", "=", "project.task"), ("res_id", "=", task.id)])
            .resource_id
        )

    def test_an_hr_officer_books_a_new_employee_on_their_dated_tasks(self):
        employee = (
            self.env["hr.employee"]
            .with_user(self.hr_officer)
            .create({"name": "Booking Assignee", "user_id": self.assignee.id})
        )
        self.assertEqual(self._active_resources(self.dated_task), employee.resource_id)
        self.assertFalse(self._active_resources(self.archived_task))
        self.assertFalse(self._active_resources(self.undated_task))

    def test_the_privilege_reads_only_dated_assigned_active_tasks(self):
        tasks = (
            self.env["project.task"]
            .with_user(self.hr_officer)
            .with_privilege(PRIVILEGE)
            .with_context(active_test=False)
        )
        readable = tasks.search([])
        self.assertIn(self.dated_task, readable)
        for task in (self.archived_task, self.undated_task, self.unassigned_task):
            self.assertNotIn(task, readable)
            with self.assertRaises(AccessError):
                tasks.browse(task.id).check_access("read")
        self.assertFalse(tasks.browse(self.dated_task.id).has_access("write"))
        self.assertFalse(self.dated_task.with_user(self.hr_officer).has_access("read"))
