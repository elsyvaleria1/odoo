from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestGoogleCalendarOAuthState(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "google_calendar_client_id", "client-id"
        )
        cls.user = new_test_user(cls.env, login="gcal_oauth", groups="base.group_user")

    def test_the_state_the_sync_route_issues_authorizes_its_session_once(self):
        self.authenticate("gcal_oauth", "gcal_oauth")
        answer = self.call_jsonrpc(
            "/calendar_google/sync_data",
            {"model": "calendar.event", "fromurl": "/odoo/calendar"},
        )
        self.assertEqual(answer["status"], "need_auth")
        state = parse_qs(urlsplit(answer["url"]).query)["state"][0]
        query = urlencode({"state": state, "code": "a code"})
        with patch.object(
            type(self.env["google.service"]),
            "_get_google_tokens",
            return_value=("access", "refresh", 3600),
        ) as exchange:
            accepted = self.url_open(
                f"/google_account/authentication?{query}", allow_redirects=False
            )
            replayed = self.url_open(
                f"/google_account/authentication?{query}", allow_redirects=False
            )
        self.assertEqual(accepted.status_code, 303, accepted.text)
        self.assertTrue(accepted.headers["Location"].endswith("/odoo/calendar"))
        self.assertEqual(replayed.status_code, 400)
        exchange.assert_called_once()
        self.assertTrue(self.user.res_users_settings_id.sudo().google_calendar_rtoken)
