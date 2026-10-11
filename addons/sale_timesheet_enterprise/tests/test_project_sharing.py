from datetime import timedelta

from lxml import etree

from odoo import Command, fields

from odoo.addons.project.tests.test_project_sharing import TestProjectSharingCommon
from odoo.addons.sale_timesheet_enterprise.models.project_task import (
    PROJECT_TASK_READABLE_FIELDS_TO_MAP,
)
from odoo.addons.sale_timesheet_enterprise.models.sale_order_line import (
    DEFAULT_INVOICED_TIMESHEET,
)


class TestProjectSharing(TestProjectSharingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.analytic_plan = cls.env["account.analytic.plan"].create(
            {
                "name": "Plan",
            }
        )

        cls.analytic_account = cls.env["account.analytic.account"].create(
            {
                "name": "Analytic Account for Project Shared",
                "plan_id": cls.analytic_plan.id,
                "code": "TEST",
            }
        )
        cls.project_portal.write(
            {
                "account_id": cls.analytic_account.id,
            }
        )

        cls.empl_project_user = cls.env["hr.employee"].create(
            {
                "name": "User Empl Employee",
                "user_id": cls.user_projectuser.id,
            }
        )
        cls.env["wizard.project.project.share"].create(
            {
                "res_model": "project.project",
                "res_id": cls.project_portal.id,
                "collaborator_ids": [
                    Command.create(
                        {
                            "partner_id": cls.user_portal.partner_id.id,
                            "access_mode": "edit",
                        }
                    ),
                ],
            }
        ).action_send_mail()

    def test_project_sharing_timesheets_visibility(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sale.invoiced_timesheet", DEFAULT_INVOICED_TIMESHEET
        )
        project_shared = self.project_portal

        task = (
            self.env["project.task"]
            .with_context(
                {"tracking_disable": True, "default_project_id": project_shared.id}
            )
            .create(
                {
                    "name": "Test Timesheets invoicing policy",
                }
            )
        )
        common_timesheet_vals = {
            "project_id": project_shared.id,
            "task_id": task.id,
            "date": fields.Date.today() - timedelta(days=1),
        }
        timesheets = (
            self.env["account.analytic.line"]
            .with_context({"tracking_disable": True})
            .create(
                [
                    {
                        **common_timesheet_vals,
                        "name": "Timesheet 1",
                        "unit_amount": 2.0,
                        "employee_id": self.empl_project_user.id,
                    },
                    {
                        **common_timesheet_vals,
                        "name": "Timesheet 2",
                        "unit_amount": 3.0,
                        "employee_id": self.empl_project_user.id,
                    },
                ]
            )
        )

        task.message_subscribe(partner_ids=self.user_portal.partner_id.ids)
        task_read_with_portal_user = task.with_user(self.user_portal).read(
            ["timesheet_ids"]
        )
        self.assertEqual(
            len(task_read_with_portal_user[0]["timesheet_ids"]),
            2,
            "The external collaborator should see the both timesheets created in that task.",
        )

        self.env["ir.config_parameter"].sudo().set_param(
            "sale.invoiced_timesheet", "approved"
        )

        task_read_with_portal_user = task.with_user(self.user_portal).read(
            ["timesheet_ids"]
        )
        self.assertFalse(
            task_read_with_portal_user[0]["timesheet_ids"],
            "The external collaborator should see no timesheets into that task since the timesheets are not validated.",
        )

        timesheet1 = timesheets[0]
        timesheet1.action_validate_timesheet()
        self.assertTrue(timesheet1.validated, "The timesheet should be validated")

        task_read_with_portal_user = task.with_user(self.user_portal).read(
            ["timesheet_ids"]
        )
        self.assertEqual(
            len(task_read_with_portal_user[0]["timesheet_ids"]),
            1,
            "The external collaborator should only see the timesheet validated into that task and not all timesheets.",
        )

    def test_project_sharing_remaining_hours(self):
        project_shared = self.project_portal
        task = (
            self.env["project.task"]
            .with_context(
                {"tracking_disable": True, "default_project_id": project_shared.id}
            )
            .create({"name": "test project ", "planned_hours": 10.0})
        )
        task_read_with_portal_user = task.with_user(self.user_portal).read(
            ["portal_remaining_hours"]
        )[0]["portal_remaining_hours"]
        self.assertEqual(
            task_read_with_portal_user,
            10.0,
            "The portal user portal_remaining_hours should equal planned_hours when there is no timesheet linked to the task",
        )

    def test_portal_reads_the_shared_hours_not_the_raw_ones(self):
        Task = self.env["project.task"].with_user(self.user_portal)
        for raw, shared in PROJECT_TASK_READABLE_FIELDS_TO_MAP.items():
            self.assertFalse(Task._has_field_access(Task._fields[raw], "read"), raw)
            self.assertTrue(
                Task._has_field_access(Task._fields[shared], "read"), shared
            )

    def test_the_sharing_views_name_no_hours_the_portal_cannot_read(self):
        Task = self.env["project.task"].with_user(self.user_portal)
        for kind, view_type in (
            ("form", "form"),
            ("kanban", "kanban"),
            ("tree", "list"),
        ):
            view = self.env.ref(f"project.project_sharing_project_task_view_{kind}")
            views = Task.get_views([(view.id, view_type)])["views"]
            arch = etree.fromstring(views[view_type]["arch"])
            named = {node.get("name") for node in arch.iter("field")}
            self.assertFalse(named & set(PROJECT_TASK_READABLE_FIELDS_TO_MAP), kind)
