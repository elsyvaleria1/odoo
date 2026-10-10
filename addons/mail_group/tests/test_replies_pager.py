from lxml import html

from odoo import http
from odoo.tests import HttpCase, tagged

from odoo.addons.web.controllers.utils import FRAGMENTS_HEADER


@tagged("post_install", "-at_install")
class TestRepliesPager(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env["mail.group"].create(
            {
                "name": "Pager group",
                "alias_name": "pager.group",
                "access_mode": "public",
            }
        )
        message_values = {
            "mail_group_id": cls.group.id,
            "email_from": "someone@example.com",
            "moderation_status": "accepted",
        }
        cls.thread = cls.env["mail.group.message"].create(
            {**message_values, "subject": "Thread", "body": "<p>Thread</p>"}
        )
        cls.replies = cls.env["mail.group.message"].create(
            [
                {
                    **message_values,
                    "subject": f"Reply {index}",
                    "body": f"<p>Reply {index}</p>",
                    "group_message_parent_id": cls.thread.id,
                }
                for index in range(9)
            ]
        )

    def setUp(self):
        super().setUp()
        self.authenticate(None, None)
        self.route = f"/groups/{self.group.id}/{self.thread.id}/get_replies"

    def _ask(self, last_displayed_id, fragments=True, group=None):
        route = (
            self.route
            if not group
            else f"/groups/{group.id}/{self.thread.id}/get_replies"
        )
        return self.url_open(
            route,
            data={
                "last_displayed_id": last_displayed_id,
                "csrf_token": http.Request.csrf_token(self),
            },
            headers={FRAGMENTS_HEADER: "1"} if fragments else None,
            allow_redirects=False,
        )

    def test_a_row_gets_the_replies_after_it_and_the_row_for_the_page_after(self):
        last = self.replies[1]

        response = self._ask(last.id)

        self.assertEqual(response.status_code, 200, response.text)
        (fragment,) = response.json()["fragments"]
        self.assertEqual(
            fragment["key"], f"mail_group.replies.{self.thread.id}.{last.id}"
        )
        root = html.fromstring(fragment["html"])
        subjects = root.xpath("//h5/a/text()")
        self.assertEqual(subjects, [f"Reply {index}" for index in range(2, 7)])
        self.assertEqual(
            root.xpath("//div[@data-fragment]/@data-fragment"),
            [
                f"mail_group.replies.{self.thread.id}.{last.id}",
                f"mail_group.replies.{self.thread.id}.{self.replies[6].id}",
            ],
        )

    def test_the_last_page_ends_without_a_row(self):
        response = self._ask(self.replies[4].id)

        root = html.fromstring(response.json()["fragments"][0]["html"])
        self.assertEqual(
            root.xpath("//h5/a/text()"), [f"Reply {index}" for index in range(5, 9)]
        )
        self.assertFalse(root.xpath("//button[contains(@class, 'o_mg_read_more')]"))

    def test_without_javascript_the_row_leads_to_the_thread(self):
        response = self._ask(self.replies[1].id, fragments=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn(f"-{self.thread.id}", response.headers["Location"])

    def test_a_message_of_another_group_is_not_found(self):
        other = self.env["mail.group"].create(
            {
                "name": "Other group",
                "alias_name": "other.pager",
                "access_mode": "public",
            }
        )

        self.assertEqual(self._ask(self.replies[1].id, group=other).status_code, 404)

    def test_the_thread_page_offers_the_next_replies_as_a_form_of_its_own(self):
        page = html.fromstring(
            self.url_open(f"/groups/{self.group.id}/{self.thread.id}").content
        )

        (form,) = page.xpath("//form[.//button[contains(@class, 'o_mg_read_more')]]")
        self.assertTrue(form.get("action").endswith("/get_replies"))
        self.assertEqual(
            form.xpath("input[@name='last_displayed_id']/@value"),
            [str(self.replies[4].id)],
        )
        self.assertFalse(page.xpath("//form//form"))
