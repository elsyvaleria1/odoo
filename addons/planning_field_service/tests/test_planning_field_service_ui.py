from odoo.tests import HttpCase, tagged

from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("post_install", "-at_install")
class TestPlanningFieldServiceUi(HttpCase):
    def test_an_employee_declares_and_starts_a_visit(self):
        visitor = mail_new_test_user(
            self.env,
            login="fs_tour_visitor",
            groups="planning.group_planning_user",
            name="Visitor",
        )
        self.env["hr.employee"].create(
            {"name": "Visitor", "user_id": visitor.id, "tz": "UTC"}
        )
        self.env["res.partner"].create({"name": "Rancho El Sabino"})

        self.start_tour(
            "/", "planning_field_service_declare_visit", login="fs_tour_visitor"
        )

        visit = self.env["planning.slot"].search([("user_id", "=", visitor.id)])
        self.assertEqual(visit.state, "3_in_progress")
        self.assertEqual(visit.partner_id.name, "Rancho El Sabino")
