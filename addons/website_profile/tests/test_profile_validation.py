from odoo import http
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.web.controllers.utils import PARTIAL_NAVIGATION_HEADER
from odoo.addons.website_profile.models.res_users import VALIDATION_KARMA_GAIN


@tagged("post_install", "-at_install")
class TestProfileValidation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = mail_new_test_user(
            cls.env,
            login="wp_profile_user",
            email="wp.profile@example.com",
            groups="base.group_user",
        )

    def test_token_is_deterministic_per_day(self):
        Users = self.env["res.users"]
        token_1 = Users._generate_profile_token(self.user.id, self.user.email)
        token_2 = Users._generate_profile_token(self.user.id, self.user.email)
        self.assertEqual(token_1, token_2)

    def test_token_differs_per_email(self):
        Users = self.env["res.users"]
        token_1 = Users._generate_profile_token(self.user.id, "a@example.com")
        token_2 = Users._generate_profile_token(self.user.id, "b@example.com")
        self.assertNotEqual(token_1, token_2)

    def test_valid_token_grants_validation_karma(self):
        self.user.karma = 0
        token = self.env["res.users"]._generate_profile_token(
            self.user.id, self.user.email
        )
        self.assertTrue(
            self.user._process_profile_validation_token(token, self.user.email)
        )
        self.assertEqual(self.user.karma, VALIDATION_KARMA_GAIN)

    def test_wrong_token_is_rejected(self):
        self.user.karma = 0
        self.assertFalse(
            self.user._process_profile_validation_token("forged", self.user.email)
        )
        self.assertEqual(self.user.karma, 0)

    def test_token_on_active_user_is_rejected(self):
        self.user.karma = 10
        token = self.env["res.users"]._generate_profile_token(
            self.user.id, self.user.email
        )
        self.assertFalse(
            self.user._process_profile_validation_token(token, self.user.email)
        )
        self.assertEqual(self.user.karma, 10)

    def test_validation_email_requires_an_email(self):
        self.user.email = False
        self.assertFalse(self.user._send_profile_validation_email())

    def test_validation_email_is_sent_with_token_url(self):
        Mail = self.env["mail.mail"].sudo()
        last_id = Mail.search([], order="id desc", limit=1).id or 0

        self.assertTrue(self.user._send_profile_validation_email())

        mails = Mail.search([("id", ">", last_id)], order="id desc")
        self.assertTrue(mails)
        body = mails[0].body_html or ""
        self.assertIn("/profile/validate_email", body)
        self.assertIn(
            self.user._generate_profile_token(self.user.id, self.user.email), body
        )

    def test_validation_email_forwards_extra_params(self):
        Mail = self.env["mail.mail"].sudo()
        last_id = Mail.search([], order="id desc", limit=1).id or 0

        self.user._send_profile_validation_email(forum_id=42)

        mails = Mail.search([("id", ">", last_id)], order="id desc")
        self.assertTrue(mails)
        self.assertIn("forum_id=42", mails[0].body_html or "")


@tagged("post_install", "-at_install")
class TestProfileValidationRoutes(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = mail_new_test_user(
            cls.env,
            login="wp_route_user",
            email="wp.route@example.com",
            groups="base.group_portal",
            karma=0,
        )

    def _session(self):
        return http.root.session_store.get(self.session.sid)

    def test_sending_the_email_returns_to_the_page(self):
        self.authenticate("wp_route_user", "wp_route_user")
        Mail = self.env["mail.mail"].sudo()
        last_id = Mail.search([], order="id desc", limit=1).id or 0

        response = self.url_open(
            "/profile/send_validation_email",
            data={
                "csrf_token": http.Request.csrf_token(self),
                "redirect_url": "/profile/users?x=1",
            },
            allow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/profile/users?x=1"))
        self.assertTrue(Mail.search([("id", ">", last_id)]))
        self.assertTrue(self._session()["validation_email_sent"])

    def test_the_validation_is_announced_once_on_a_page_shown(self):
        self.authenticate("wp_route_user", "wp_route_user")
        token = self.env["res.users"]._generate_profile_token(
            self.user.id, self.user.email
        )
        page = f"/profile/user/{self.user.id}"
        self.url_open(
            "/profile/validate_email",
            params={
                "token": token,
                "user_id": self.user.id,
                "email": self.user.email,
                "redirect_url": "/profile/users",
            },
            allow_redirects=False,
        )

        self.url_open(page, headers={PARTIAL_NAVIGATION_HEADER: "1"})
        kept = self._session()["validation_email_done"]
        self.url_open(page)
        cleared = self._session()["validation_email_done"]

        self.assertTrue(kept)
        self.assertFalse(cleared)
