import html
import re

from odoo.tests import HttpCase, tagged

from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("post_install", "-at_install", "access_link")
class TestPortalProjectLinkReport(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create(
            {"name": "Report customer", "is_company": True}
        )
        cls.contact = mail_new_test_user(
            cls.env, "report_contact", groups="base.group_portal"
        )
        cls.contact.partner_id.parent_id = cls.customer
        cls.project = cls.env["project.project"].create(
            {
                "name": "Timesheeted through a link",
                "privacy_visibility": "portal",
                "allow_timesheets": True,
                "partner_id": cls.customer.id,
            }
        )
        cls.task = cls.env["project.task"].create(
            {
                "name": "Task with hours",
                "project_id": cls.project.id,
                "partner_id": cls.customer.id,
            }
        )
        employee = cls.env["hr.employee"].create({"name": "Timesheeter"})
        cls.env["account.analytic.line"].create(
            {
                "name": "Hours",
                "task_id": cls.task.id,
                "project_id": cls.project.id,
                "employee_id": employee.id,
                "unit_amount": 2.0,
            }
        )
        cls.tokens = {
            "comment": cls.project._portal_get_or_create_token(),
            "view": cls.env["access.link"]._issue(
                cls.project, role="view", cause="share"
            )[1],
        }

    def _print_href(self, token):
        page = self.url_open(
            f"/my/projects/{self.project.id}/task/{self.task.id}?access_token={token}"
        )
        self.assertEqual(page.status_code, 200)
        button = re.search(r"<a[^>]*o_project_timesheet_print[^>]*>", page.text)
        if not button:
            return None
        return html.unescape(re.search(r'href="([^"]*)"', button[0])[1])

    def test_the_print_button_works_for_every_project_link(self):
        for login in ("report_contact", None):
            for role, token in self.tokens.items():
                with self.subTest(login=login, role=role):
                    self.authenticate(login, login)
                    href = self._print_href(token)
                    if login:
                        self.assertTrue(href, "the customer's contact sees hours")
                    if not href:
                        continue
                    response = self.url_open(href, allow_redirects=False)
                    self.assertEqual(response.status_code, 200, href)
                    self.assertEqual(
                        response.headers["Content-Type"], "application/pdf"
                    )

    def test_a_project_link_prints_no_task_outside_its_project(self):
        other = self.env["project.task"].create(
            {
                "name": "Elsewhere",
                "project_id": self.env["project.project"].create({"name": "Other"}).id,
            }
        )
        self.authenticate(None, None)
        response = self.url_open(
            f"/my/projects/{self.project.id}/task/{other.id}"
            f"?report_type=pdf&access_token={self.tokens['view']}",
            allow_redirects=False,
        )
        self.assertNotEqual(response.status_code, 200)
