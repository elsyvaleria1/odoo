from odoo.tests import tagged

from odoo.addons.sale_timesheet.tests.common import TestCommonSaleTimesheet


@tagged("-at_install", "post_install", "helpdesk_sale_timesheet")
class TestSaleTimesheetInTicket(TestCommonSaleTimesheet):
    @classmethod
    def get_default_groups(cls):
        return super().get_default_groups() + cls.env.ref(
            "helpdesk.group_helpdesk_manager"
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.helpdesk_team = cls.env["team.team"].create(
            {
                "use_helpdesk": True,
                "name": "Test Team",
                "use_helpdesk_timesheet": True,
                "use_helpdesk_sale_timesheet": True,
                "project_id": cls.project_task_rate.id,
                "helpdesk_use_sla": True,
            }
        )

    def test_sla_customer_restriction(self):
        partner_in_sla = self.env["res.partner"].create(
            {
                "name": "Partner in SLA",
            }
        )
        partner_not_in_sla = self.env["res.partner"].create(
            {
                "name": "Partner in not in SLA",
            }
        )
        helpdesk_stage = self.env["helpdesk.stage"].create(
            {
                "name": "New",
                "sequence": 0,
            }
        )
        sla_policy = self.env["helpdesk.sla"].create(
            {
                "name": "SLA Policy",
                "partner_ids": [partner_in_sla.id],
                "team_id": self.helpdesk_team.id,
                "priority": "0",
                "stage_id": helpdesk_stage.id,
            }
        )
        ticket_sla_present = self.env["helpdesk.ticket"].create(
            {
                "name": "Ticket SLA Present",
                "partner_id": partner_in_sla.id,
                "team_id": self.helpdesk_team.id,
                "priority": "0",
                "stage_id": helpdesk_stage.id,
            }
        )
        self.assertTrue(
            sla_policy in ticket_sla_present.sla_status_ids.sla_id,
            "SLA Policy should be present on the ticket",
        )
        ticket_sla_not_present = self.env["helpdesk.ticket"].create(
            {
                "name": "Ticket without SLA",
                "partner_id": partner_not_in_sla.id,
                "team_id": self.helpdesk_team.id,
                "priority": "0",
                "stage_id": helpdesk_stage.id,
            }
        )
        self.assertFalse(
            sla_policy in ticket_sla_not_present.sla_status_ids.sla_id,
            "SLA Policy shouldn't be present on the ticket",
        )
