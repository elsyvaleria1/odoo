from odoo.tests import HttpCase, tagged

AWAIT_PROBE = """
    const awaited = odoo.__session_info__.await_precompiled_templates;
    if (awaited === %s) {
        console.log("test successful");
    } else {
        console.error("await_precompiled_templates is " + awaited);
    }
"""


@tagged("-at_install", "post_install")
class TestLoaderScriptPolicy(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        website = cls.env.ref("website.default_website")
        website.channel_id = cls.env["im_livechat.channel"].create(
            {"name": "Policy channel"}
        )

    def test_the_loader_keeps_an_editor_page_s_bounded_wait(self):
        self.browser_js("/", AWAIT_PROBE % "false", login="admin")

    def test_the_loader_keeps_a_public_page_s_wait(self):
        self.browser_js("/", AWAIT_PROBE % "true")
