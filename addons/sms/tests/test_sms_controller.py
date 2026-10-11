from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestSmsController(HttpCase):

    def test_malformed_webhook_payload_raises_user_error_not_type_error(self):
        response = self.url_open(
            "/sms/status",
            data='{"jsonrpc": "2.0", "method": "call", "params": {"message_statuses": [{"uuids": [], "sms_status": "delivered"}]}}',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        error = response.json()["error"]
        self.assertEqual(
            error["data"]["name"],
            "odoo.exceptions.UserError",
            "a malformed payload must surface as the intended UserError, not "
            "an unrelated TypeError from a bad UserError(...) call signature",
        )
