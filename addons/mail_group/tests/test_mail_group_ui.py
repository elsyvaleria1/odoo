from odoo import http
from odoo.tests import HttpCase, tagged

from odoo.addons.web.controllers.utils import FRAGMENTS_HEADER


@tagged("post_install", "-at_install")
class TestMailGroupUi(HttpCase):
    def test_archives_filter_in_place(self):
        group = self.env["mail.group"].create(
            {"name": "PN List", "alias_name": "pn.list", "access_mode": "public"}
        )
        messages = self.env["mail.group.message"].create(
            [
                {
                    "subject": subject,
                    "mail_group_id": group.id,
                    "moderation_status": "accepted",
                    "email_from": '"Ada" <ada@example.com>',
                }
                for subject in ("PN January", "PN March")
            ]
        )
        for message, date in zip(messages, ("2026-01-15", "2026-03-10"), strict=True):
            self.env.cr.execute(
                "UPDATE mail_group_message SET create_date = %s WHERE id = %s",
                (date, message.id),
            )
        messages.invalidate_recordset(["create_date"])
        self.start_tour(
            f"/groups/{self.env['ir.http']._slug(group)}?mode=date",
            "mail_group_archives_partial_navigation",
        )

    def test_a_user_subscribes_in_place(self):
        group = self.env["mail.group"].create(
            {
                "name": "PN Joinable",
                "alias_name": "pn.joinable",
                "access_mode": "public",
            }
        )
        self.start_tour("/groups", "mail_group_subscribe_in_place", login="demo")
        self.assertTrue(
            group._find_member(
                self.env.ref("base.user_demo").email,
                self.env.ref("base.user_demo").partner_id.id,
            )
        )


@tagged("post_install", "-at_install")
class TestMailGroupSubscription(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env["mail.group"].create(
            {
                "name": "Subscribable",
                "alias_name": "subscribable",
                "access_mode": "public",
            }
        )

    def _subscription(self, headers=None, **values):
        return self.url_open(
            f"/group/{self.group.id}/subscription",
            data={
                "csrf_token": http.Request.csrf_token(self),
                "redirect": "/groups",
                **values,
            },
            headers=headers,
            allow_redirects=False,
        )

    def test_a_visitor_is_sent_a_confirmation_and_told_so(self):
        self.authenticate(None, None)

        response = self._subscription(action="subscribe", email="ann@example.com")
        page = self.url_open(response.headers["Location"])

        self.assertEqual(response.status_code, 303)
        self.assertIn(
            f"subscription_group={self.group.id}", response.headers["Location"]
        )
        self.assertIn("An email with instructions has been sent.", page.text)
        self.assertFalse(self.group._find_member("ann@example.com", None))

    def test_a_visitor_without_a_valid_email_is_told_in_place(self):
        self.authenticate(None, None)

        response = self._subscription(
            headers={FRAGMENTS_HEADER: "1"}, action="subscribe", email="not-an-email"
        )

        self.assertEqual(response.status_code, 200)
        keys = [fragment["key"] for fragment in response.json()["fragments"]]
        self.assertEqual(
            keys,
            [
                f"mail_group.subscription.{self.group.id}",
                f"mail_group.members.{self.group.id}",
            ],
        )
        self.assertIn(
            "Please enter a valid email address.",
            response.json()["fragments"][0]["html"],
        )
