from odoo import Command
from odoo.tests import Form, tagged

from odoo.addons.sale_timesheet.tests.common import TestCommonSaleTimesheet


@tagged("post_install", "-at_install")
class TestTasksTicketsConversionSol(TestCommonSaleTimesheet):
    @classmethod
    def get_default_groups(cls):
        return super().get_default_groups() + cls.env.ref(
            "helpdesk.group_helpdesk_manager"
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.helpdesk_stage = cls.env["helpdesk.stage"].create(
            {
                "name": "New",
            }
        )

        cls.helpdesk_team = cls.env["team.team"].create(
            {
                "use_helpdesk": True,
                "name": "Test Team",
                "use_helpdesk_timesheet": True,
                "use_helpdesk_sale_timesheet": True,
                "project_id": cls.project_task_rate.id,
                "helpdesk_stage_ids": [Command.link(cls.helpdesk_stage.id)],
            }
        )

        cls.project_step = cls.env["project.workflow.step"].create(
            {
                "name": "New",
            }
        )

        cls.project_task_rate.write(
            {
                "workflow_step_ids": [Command.link(cls.project_step.id)],
            }
        )

    def setUp(self):
        super().setUp()

        self.ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Test Ticket",
                "team_id": self.helpdesk_team.id,
                "partner_id": self.partner_b.id,
            }
        )

        self.task = self.env["project.task"].create(
            {
                "name": "Test Task",
                "project_id": self.project_task_rate.id,
                "sale_line_id": self.so.line_ids[-1].id,
            }
        )

    def test_convert_ticket_with_sol_to_task(self):
        form = Form(
            self.env["wizard.helpdesk.ticket.convert.task"].with_context(
                {"to_convert": [self.ticket.id]}
            )
        )

        form.project_id = self.project_task_rate
        form.step_id = self.project_step

        wizard = form.save()
        view = wizard.action_convert()

        task = self.env["project.task"].browse(view["res_id"])
        self.assertEqual(
            self.ticket.sale_line_id,
            task.sale_line_id,
            "The ticket and the task should have the same SOL",
        )

    def test_convert_task_with_sol_to_ticket(self):
        form = Form(
            self.env["wizard.project.task.convert.ticket"].with_context(
                {"to_convert": [self.task.id]}
            )
        )

        form.team_id = self.helpdesk_team
        form.stage_id = self.helpdesk_stage

        wizard = form.save()
        view = wizard.action_convert()

        ticket = self.env["helpdesk.ticket"].browse(view["res_id"])
        self.assertEqual(
            self.task.sale_line_id,
            ticket.sale_line_id,
            "The ticket and the task should have the same SOL",
        )
