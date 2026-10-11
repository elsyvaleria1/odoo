from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestCorsLivechatTranscript(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        operator = cls.env["res.users"].create(
            {"name": "Operator", "login": "operator_cors_transcript"}
        )
        cls.env["mail.presence"]._update_presence(operator)
        cls.livechat_channel = cls.env["im_livechat.channel"].create(
            {"name": "Test Livechat Channel", "user_ids": [operator.id]}
        )

    def _start_cors_session(self):
        data = self.call_jsonrpc(
            "/im_livechat/cors/get_session",
            {"channel_id": self.livechat_channel.id, "persisted": True},
        )
        self.authenticate(None, None)
        return data["channel_id"], data["store_data"]["Store"]["guest_token"]

    def test_transcript_download_takes_the_guest_token_in_the_body(self):
        channel_id, guest_token = self._start_cors_session()
        route = f"/im_livechat/cors/download_transcript/{channel_id}"
        res = self.url_open(route, data={"guest_token": guest_token})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["Content-Type"], "application/pdf")
        with mute_logger("odoo.http"):
            res = self.url_open(f"{route}?guest_token={guest_token}")
        self.assertEqual(res.status_code, 405)

    def test_dead_cors_init_route_is_gone(self):
        with mute_logger("odoo.http"):
            res = self.url_open(
                "/im_livechat/cors/init",
                data='{"jsonrpc": "2.0", "method": "call", "params": {"channel_id": %d}}'
                % self.livechat_channel.id,
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["error"]["code"], 404)
