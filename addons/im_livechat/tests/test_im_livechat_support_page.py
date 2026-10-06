import re
from unittest.mock import patch

import odoo

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.im_livechat.controllers.main import LivechatController
from odoo.addons.im_livechat.tests.common import TestGetOperatorCommon


@odoo.tests.tagged("-at_install", "post_install")
class TestImLivechatSupportPage(TestGetOperatorCommon):
    def test_load_modules(self):
        operator = self._create_operator()
        livechat_channel = self.env["im_livechat.channel"].create(
            {"name": "Support Channel", "user_ids": [operator.id]}
        )
        self.start_tour(
            f"/im_livechat/support/{livechat_channel.id}", "im_livechat.basic_tour"
        )

    def test_load_modules_cors(self):
        operator = self._create_operator()
        livechat_channel = self.env["im_livechat.channel"].create(
            {"name": "Support Channel", "user_ids": [operator.id]}
        )
        with patch.object(LivechatController, "_is_cors_request", return_value=True):
            self.start_tour(
                f"/im_livechat/support/{livechat_channel.id}", "im_livechat.basic_tour"
            )

    def test_the_external_loader_boots_on_an_available_channel_only(self):
        operator = self._create_operator()
        channel = self.env["im_livechat.channel"].create(
            {"name": "Loader", "user_ids": [operator.id]}
        )
        loader_url = f"/im_livechat/loader/{channel.id}"
        loader = self.url_open(loader_url).text
        self.assertIn("can_load_livechat: true", loader)
        self.assertIn(f'"channel_id": {channel.id}', loader)
        operator.sudo().presence_ids.unlink()
        loader = self.url_open(loader_url).text
        self.assertIn("can_load_livechat: false", loader)
        self.assertNotIn('"channel_id"', loader)

    def test_the_embed_snippet_carries_no_nonce(self):
        channel = self.env["im_livechat.channel"].create({"name": "Embed"})
        values = {"url": channel.get_base_url(), "channel_id": channel.id}
        # rendered where the channel form computes it and where the support
        # page includes it: neither is a website page
        with MockRequest(self.env, is_frontend=False) as request:
            request.csp_nonce = "n0nce"
            self.assertIn(
                'nonce="n0nce"',
                self.env["ir.qweb"]._render("im_livechat.external_loader", values),
            )
            self.assertIn("/im_livechat/loader/", channel.script_external)
            self.assertNotIn("nonce", channel.script_external)

    def test_the_support_page_scripts_run_under_the_page_nonce(self):
        channel = self.env["im_livechat.channel"].create({"name": "Support"})
        response = self.url_open(f"/im_livechat/support/{channel.id}")
        policy = response.headers["Content-Security-Policy"]
        nonce = re.search(r"'nonce-([^']+)'", policy).group(1)
        scripts = re.findall(r"<script\b[^>]*>", response.text)
        self.assertTrue(scripts)
        for script in scripts:
            with self.subTest(script=script):
                self.assertIn(f'nonce="{nonce}"', script)

    def test_the_support_page_runs_without_unsafe_eval(self):
        channel = self.env["im_livechat.channel"].create({"name": "Support"})
        url = f"/im_livechat/support/{channel.id}"
        policy = self.url_open(url).headers["Content-Security-Policy"]
        self.assertNotIn("'unsafe-eval'", policy)
        self.env["ir.config_parameter"].set_param(
            "web.base.url", "https://livechat.example.com"
        )
        self.env["ir.config_parameter"].set_param("web.base.url.freeze", True)
        policy = self.url_open(url).headers["Content-Security-Policy"]
        self.assertIn("'unsafe-eval'", policy, "the embed comes from another origin")
