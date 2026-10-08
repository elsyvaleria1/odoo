import html
import re
from urllib.parse import urlsplit

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from odoo.addons.mail.tests.common import mail_new_test_user

# a 1x1 transparent PNG
SIGNATURE = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


@tagged("post_install", "-at_install", "access_link")
class TestFsmPortalProjectLinkSign(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create(
            {"name": "Signing customer", "is_company": True}
        )
        cls.contact = cls.env["res.partner"].create(
            {"name": "Customer's foreman", "parent_id": cls.customer.id}
        )
        cls.project = cls.env["project.project"].create(
            {
                "name": "Field Service through a link",
                "is_fsm": True,
                "allow_timesheets": True,
                "privacy_visibility": "portal",
                "partner_id": cls.customer.id,
                "company_id": cls.env.company.id,
            }
        )
        cls.task = cls.env["project.task"].create(
            {
                "name": "Report to sign",
                "project_id": cls.project.id,
                "partner_id": cls.customer.id,
            }
        )
        cls.employee = cls.env["hr.employee"].create({"name": "Technician"})
        cls._log_hours(cls.task)
        cls.comment_token = cls.project._portal_get_or_create_token()
        __, cls.view_token = cls.env["access.link"]._issue(
            cls.project, role="view", cause="share"
        )

    @classmethod
    def _log_hours(cls, task):
        cls.env["account.analytic.line"].create(
            {
                "name": "Repair",
                "task_id": task.id,
                "project_id": cls.project.id,
                "employee_id": cls.employee.id,
                "unit_amount": 1.0,
            }
        )

    def setUp(self):
        super().setUp()
        self.authenticate(None, None)

    def _page(self, token, task=None):
        task = task or self.task
        response = self.url_open(
            f"/my/projects/{self.project.id}/task/{task.id}?access_token={token}"
        )
        self.assertEqual(response.status_code, 200)
        return response.text

    def _sign_url(self, page):
        found = re.search(
            r'"callUrl": "([^"]*worksheet/sign[^"]*)"', html.unescape(page)
        )
        return found[1] if found else None

    def _sign(self, url):
        return self.url_open(
            url,
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {"name": "Customer", "signature": SIGNATURE},
            },
        ).json()["result"]

    def test_the_customers_project_link_signs_the_worksheet(self):
        self.assertTrue(self.task._has_to_be_signed())
        url = self._sign_url(self._page(self.comment_token))
        self.assertTrue(url, "the page offers to sign")
        result = self._sign(url)
        self.assertNotIn("error", result)
        self.assertTrue(self.task.worksheet_signature)
        self.assertEqual(self.task.worksheet_signed_by, "Customer")
        redirect = urlsplit(result["redirect_url"])
        self.assertEqual(
            redirect.path, f"/my/projects/{self.project.id}/task/{self.task.id}"
        )
        self.assertIn(f"access_token={self.comment_token}", redirect.query)

    @mute_logger("odoo.http")
    def test_the_public_view_link_offers_no_signature_and_signs_nothing(self):
        page = self._page(self.view_token)
        self.assertIsNone(self._sign_url(page))
        self.assertNotIn("Sign Report", page)
        base = f"/my/tasks/{self.task.id}/worksheet/sign/fsm"
        signed = self._page(self.comment_token)
        credentials = re.search(r"pid=(\d+)&hash=(\w+)", self._sign_url(signed))
        for query in (
            f"access_token={self.view_token}",
            f"access_token={self.comment_token}",
            (
                f"access_token={self.view_token}"
                f"&pid={credentials[1]}&hash={credentials[2]}"
            ),
        ):
            with self.subTest(query=query):
                self.assertIn("error", self._sign(f"{base}?{query}"))
        self.assertFalse(self.task.worksheet_signature)

    def test_a_contact_of_the_customers_company_signs(self):
        token = self.project._portal_get_or_create_token(self.contact)
        url = self._sign_url(self._page(token))
        self.assertTrue(url, "the page offers to sign")
        self.assertIn(f"pid={self.contact.id}", url)
        self.assertNotIn("error", self._sign(url))
        self.assertTrue(self.task.worksheet_signature)

    @mute_logger("odoo.http")
    def test_a_collaborators_invitation_from_another_company_signs_nothing(self):
        outsider = mail_new_test_user(
            self.env, "fsm_outsider", groups="base.group_portal"
        ).partner_id
        outsider.parent_id = self.env["res.partner"].create(
            {"name": "Subcontractor", "is_company": True}
        )
        self.project._add_collaborators(outsider, access_mode="edit")
        # the very link the Share dialog's invitation hands out
        token = self.project._portal_tokens(outsider)[outsider.id]
        page = self._page(token)
        self.assertIn(f'data-pid="{outsider.id}"', page, "the outsider comments")
        self.assertIsNone(self._sign_url(page))
        signed = {
            "pid": outsider.id,
            "hash": self.project._sign_token(outsider.id, token=token),
        }
        result = self._sign(
            f"/my/tasks/{self.task.id}/worksheet/sign/fsm?access_token={token}"
            f"&pid={signed['pid']}&hash={signed['hash']}"
        )
        self.assertIn("error", result)
        self.assertFalse(self.task.worksheet_signature)

    @mute_logger("odoo.http")
    def test_a_task_without_customer_signs_by_no_link(self):
        task = self.env["project.task"].create(
            {"name": "Nobody's report", "project_id": self.project.id}
        )
        task.partner_id = False
        self._log_hours(task)
        self.assertTrue(task._has_to_be_signed())
        page = self._page(self.comment_token, task)
        self.assertIsNone(self._sign_url(page))
        credentials = {
            "pid": self.customer.id,
            "hash": self.project._sign_token(
                self.customer.id, token=self.comment_token
            ),
        }
        result = self._sign(
            f"/my/tasks/{task.id}/worksheet/sign/fsm"
            f"?access_token={self.comment_token}"
            f"&pid={credentials['pid']}&hash={credentials['hash']}"
        )
        self.assertIn("error", result)
        self.assertFalse(task.worksheet_signature)
