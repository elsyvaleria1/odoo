import re

from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestLeadFormPhone(HttpCase):
    def test_a_posted_phone_id_does_not_link_someone_elses_number(self):
        victim = self.env["res.partner"].create(
            {
                "name": "Victim",
                "phone_ids": [(0, 0, {"number": "+32 470 11 22 33", "type": "mobile"})],
            }
        )
        victim_phone = victim.phone_ids
        visitor = new_test_user(
            self.env, login="lead_form_portal", groups="base.group_portal"
        )
        visitor.partner_id.email = "lead_form_portal@example.com"
        self.authenticate("lead_form_portal", "lead_form_portal")
        response = self.url_open(
            "/website/form/crm.lead",
            data={
                "email_from": "lead_form_portal@example.com",
                "contact_name": "Visitor",
                "name": "Lead",
                "phone_ids": str(victim_phone.id),
                "csrf_token": re.search(
                    r'csrf_token: "([^"]+)"', self.url_open("/").text
                ).group(1),
            },
        )
        lead = self.env["crm.lead"].browse(response.json()["id"])
        self.assertNotIn(victim_phone, lead.phone_ids)
        self.assertNotIn(victim_phone, visitor.partner_id.phone_ids)
