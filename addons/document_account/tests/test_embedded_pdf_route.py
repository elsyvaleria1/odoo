import base64

from odoo.tests import HttpCase, new_test_user, tagged

EMBEDDED = b"%PDF- Fake PDF content"
XML = (
    b'<?xml version="1.0" ?>\n<test> <Attachment>'
    + base64.b64encode(EMBEDDED)
    + b"</Attachment> </test>"
)


@tagged("post_install", "-at_install", "test_document_bridge")
class TestEmbeddedPdfRoute(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal = new_test_user(
            cls.env, "embedded_portal", groups="base.group_portal"
        )
        cls.internal = new_test_user(
            cls.env, "embedded_internal", groups="base.group_user"
        )
        cls.document = cls.env["document.document"].create(
            {
                "name": "invoice.xml",
                "datas": base64.b64encode(XML),
                "user_folder_id": "COMPANY",
                "access_internal": "none",
            }
        )
        cls.document.action_update_access_rights(
            access_via_link="view", is_access_via_link_hidden=False
        )
        cls.assertTrue(cls, cls.document.has_embedded_pdf)

    def _preview(self):
        return self.url_open(
            f"/documents/content/{self.document.access_token}?download=0"
        )

    def assertPreviewed(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, EMBEDDED)
        self.assertTrue(
            response.headers["Content-Disposition"].startswith("inline"),
            response.headers["Content-Disposition"],
        )
        self.assertEqual(
            response.headers.get("Content-Security-Policy"), "default-src 'none'"
        )

    def test_a_link_previews_the_embedded_pdf_for_anyone_who_holds_it(self):
        for login in (None, "embedded_portal", "embedded_internal"):
            with self.subTest(login=login):
                self.authenticate(login, login)
                self.assertPreviewed(self._preview())

    def test_a_preview_is_a_visit(self):
        self.authenticate("embedded_internal", "embedded_internal")
        self._preview()
        self.assertTrue(
            self.env["document.access.log"].search_count(
                [
                    ("document_id", "=", self.document.id),
                    ("partner_id", "=", self.internal.partner_id.id),
                    ("action", "=", "view"),
                ]
            )
        )

    def test_a_blocked_invoice_still_previews_and_an_unknown_token_does_not(self):
        self.document.is_download_blocked = True
        self.authenticate(None, None)
        self.assertPreviewed(self._preview())
        missing = self.url_open(f"/documents/content/xo{self.document.id + 10**6:x}")
        self.assertEqual(missing.status_code, 404)
