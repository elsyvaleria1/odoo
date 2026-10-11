from odoo import http
from odoo.tests.common import tagged

from odoo.addons.base.tests.common import HttpCaseWithUserDemo, HttpCaseWithUserPortal


@tagged("post_install", "-at_install")
class TestAuthSignupFlowWith2faEnforced(HttpCaseWithUserPortal, HttpCaseWithUserDemo):
    def setUp(self):
        super().setUp()
        self.env["res.config.settings"].create(
            {
                "auth_signup_uninvited": "b2c",
                "auth_totp_enforce": True,
                "auth_totp_policy": "all_required",
            }
        ).execute()

    def test_signup_with_2fa_enforced(self):
        self.env.company.email = "mycompany@example.com"

        self.authenticate(None, None)
        csrf_token = http.Request.csrf_token(self)

        name = "toto"
        payload = {
            "login": "toto@example.com",
            "name": name,
            "password": "mypassword",
            "confirm_password": "mypassword",
            "csrf_token": csrf_token,
        }
        response = self.url_open("/web/signup", data=payload)
        new_user = self.env["res.users"].search([("name", "=", name)])
        self.assertTrue(new_user)
        self.assertEqual(
            response.status_code, 200, "Signup request should succeed with a 200"
        )
