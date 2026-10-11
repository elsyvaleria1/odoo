from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestEmbedPage(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        channel = cls.env["slide.channel"].create(
            {
                "name": "Embedded course",
                "visibility": "public",
                "enroll": "public",
                "is_published": True,
            }
        )
        cls.infographic = cls.env["slide.slide"].create(
            {
                "name": "Shared infographic",
                "channel_id": channel.id,
                "slide_category": "infographic",
                "is_published": True,
                "is_preview": True,
            }
        )
        cls.mounted = ".o_wslides_embed_share_email .o_wslides_js_share_email"

    def _open(self, login, code):
        self.browser_js(
            f"/slides/embed_external/{self.infographic.id}",
            code,
            ready=f"!!document.querySelector('{self.mounted}')",
            login=login,
        )

    def test_a_signed_in_viewer_gets_the_shared_email_form(self):
        self._open(
            "admin",
            f"""
            const widget = document.querySelector('{self.mounted}');
            if (widget.querySelector('input') && widget.querySelector('button')) {{
                console.log('test successful');
            }} else {{
                console.error('no email form in ' + widget.outerHTML);
            }}
            """,
        )

    def test_a_visitor_is_asked_to_log_in(self):
        self._open(
            None,
            f"""
            const widget = document.querySelector('{self.mounted}');
            if (!widget.querySelector('input') && widget.textContent.includes('login')) {{
                console.log('test successful');
            }} else {{
                console.error('visitor sees ' + widget.outerHTML);
            }}
            """,
        )
