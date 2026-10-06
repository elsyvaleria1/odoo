from odoo.tests.common import HttpCase

from .common import HelpdeskCommon
from odoo.addons.mail.tests.common import mail_new_test_user


class TestHelpdeskPortal(HttpCase, HelpdeskCommon):
    def test_customer_closure(self):
        self.test_team.allow_portal_ticket_closing = True
        self.test_team.helpdesk_privacy_visibility = "portal"

        portal_user = mail_new_test_user(
            self.env,
            name="helpdesk_portal",
            login="helpdesk_portal",
            email="helpdesk@portal.com",
            groups="base.group_portal",
        )

        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Test Ticket",
                "team_id": self.test_team.id,
                "stage_id": self.stage_new.id,
                "user_id": self.helpdesk_user.id,
            }
        )

        self.assertFalse(
            ticket.closed_by_partner, "The ticket should not be closed by the customer."
        )

        self.authenticate(portal_user.login, portal_user.login)
        response = self.url_open(f"/my/ticket/close/{ticket.id}/{ticket.access_token}")

        self.assertEqual(response.status_code, 200, "The request should be successful.")
        self.assertTrue(
            ticket.closed_by_partner, "The ticket should be closed by the customer."
        )
        self.assertEqual(
            ticket.stage_id,
            self.stage_done,
            "The ticket should be moved to the Done stage.",
        )

    def test_ignore_mail_scanner_closure(self):
        """Only GET requests should lead to a ticket being closed."""
        self.test_team.allow_portal_ticket_closing = True
        self.test_team.helpdesk_privacy_visibility = "portal"

        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Test Ticket",
                "team_id": self.test_team.id,
                "stage_id": self.stage_new.id,
                "user_id": self.helpdesk_user.id,
            }
        )

        url = f"/my/ticket/close/{ticket.id}/{ticket.access_token}"
        self.url_open(url, method="HEAD")
        self.assertFalse(ticket.closed_by_partner)
        self.url_open(url)
        self.assertTrue(ticket.closed_by_partner)

    def test_a_query_parameter_named_like_the_ticket_is_ignored(self):
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Test Ticket", "team_id": self.test_team.id}
        )
        url = f"/my/ticket/{ticket.id}/{ticket.access_token}"
        self.assertEqual(self.url_open(f"{url}?ticket=x").status_code, 200)
