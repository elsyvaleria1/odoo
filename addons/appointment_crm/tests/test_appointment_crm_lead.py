from odoo.tests import HttpCase, tagged, users


@tagged("post_install", "-at_install")
class AppointmentCrmLeadPropagationTest(HttpCase):
    @users("admin")
    def test_tour_default_opportunity_propagation(self):
        self.env.user.tz = "Europe/Brussels"
        opportunity = self.env["crm.lead"].create({"name": "Test Opportunity"})
        appointment_type = self.env["appointment.type"].create(
            {"name": "Test AppointmentCRM"}
        )
        self.start_tour("/odoo", "appointment_crm_meeting_tour", login="admin")
        appointment_invite = self.env["appointment.invite"].search(
            [("appointment_type_ids", "in", appointment_type.ids)]
        )
        self.assertTrue(appointment_invite.opportunity_id == opportunity)
