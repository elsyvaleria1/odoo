from odoo import Command
from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("-at_install", "post_install")
class TestLoaderPageCache(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = new_test_user(
            cls.env,
            login="loader_operator",
            groups="base.group_user,im_livechat.im_livechat_group_user",
        )
        cls.livechat_channel = cls.env["im_livechat.channel"].create(
            {"name": "Loader channel", "user_ids": [Command.set(cls.operator.ids)]}
        )
        cls.website = cls.env.ref("website.default_website")
        cls.website.channel_id = cls.livechat_channel
        cls.page = cls.env["website.page"].create(
            {
                "url": "/loader-page",
                "name": "loader page",
                "type": "qweb",
                "arch": """<t t-name="website_livechat.loader_page">
                    <t t-call="website.layout"><div id="wrap"/></t>
                </t>""",
                "key": "website_livechat.loader_page",
                "is_published": True,
                "website_id": cls.website.id,
                "track": False,
            }
        )

    def _set_operator_online(self, online):
        if online:
            self.env["mail.presence"]._update_presence(self.operator)
        else:
            self.operator.presence_ids.unlink()

    def _get_page_loader_data(self):
        html = self.url_open(self.page.url).text
        can_load, _, rest = html.partition("can_load_livechat: ")[2].partition(",")
        options = rest.partition("options: ")[2].partition(",\n")[0]
        return can_load, json_loads(options) if options.strip() else {}

    def _get_livechat_available(self, url):
        result = self.call_jsonrpc(
            "/mail/action",
            {"fetch_params": [["init_livechat", self.livechat_channel.id]]},
            headers={"Referer": self.base_url() + url},
        )
        return result["Store"]["livechat_available"]

    def test_cached_page_leaves_availability_to_the_client(self):
        for online in (False, True, False):
            with self.subTest(operator_online=online):
                self._set_operator_online(online)
                can_load, options = self._get_page_loader_data()
                self.assertEqual(can_load, "true")
                self.assertEqual(options["channel_id"], self.livechat_channel.id)
                self.assertEqual(self._get_livechat_available(self.page.url), online)

    def test_cached_page_hidden_by_rule_stays_hidden(self):
        self._set_operator_online(True)
        self.env["im_livechat.channel.rule"].create(
            {
                "channel_id": self.livechat_channel.id,
                "action": "hide_button",
                "regex_url": "/loader-page",
            }
        )
        self._get_page_loader_data()
        can_load, _options = self._get_page_loader_data()
        self.assertEqual(can_load, "true")
        self.assertFalse(self._get_livechat_available(self.page.url))
        self.assertTrue(self._get_livechat_available("/contactus"))

    def test_channel_option_write_reaches_the_cached_page(self):
        self._set_operator_online(True)
        self.assertNotEqual(
            self._get_page_loader_data()[1]["button_text"], "Talk to a human"
        )
        self.livechat_channel.button_text = "Talk to a human"
        self.assertEqual(
            self._get_page_loader_data()[1]["button_text"], "Talk to a human"
        )

    def test_website_channel_write_reaches_the_cached_page(self):
        self._set_operator_online(True)
        other_channel = self.env["im_livechat.channel"].create(
            {"name": "Other channel", "user_ids": [Command.set(self.operator.ids)]}
        )
        self.assertEqual(
            self._get_page_loader_data()[1]["channel_id"], self.livechat_channel.id
        )
        self.website.channel_id = other_channel
        self.assertEqual(
            self._get_page_loader_data()[1]["channel_id"], other_channel.id
        )
        self.website.channel_id = False
        self.assertNotIn("can_load_livechat", self.url_open(self.page.url).text)
