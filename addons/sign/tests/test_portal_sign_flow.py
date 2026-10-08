import re

from odoo.tests import tagged
from odoo.tools import mute_logger

from .sign_request_common import SignRequestCommon
from odoo.addons.base.tests.common import HttpCaseWithUserPortal


@tagged("post_install", "-at_install")
class TestPortalSignFlow(HttpCaseWithUserPortal, SignRequestCommon):
    def test_portal_sign_document(self):
        """Test for signing a document from the portal."""
        self.create_sign_request_1_role(self.partner_portal, self.env["res.partner"])
        self.start_tour("/", "portal_sign_document", login="portal")

    def test_portal_download_signed_document(self):
        """Test for download a signed document using download button."""
        sign_request = self.create_sign_request_1_role(
            self.partner_portal, self.env["res.partner"]
        )
        sign_request_item = {
            sign_request_item.role_id: sign_request_item
            for sign_request_item in sign_request.request_item_ids
        }
        sign_request_item_signer_1 = sign_request_item[self.role_signer_1]

        sign_request_item_signer_1.sudo().sign(self.single_signer_sign_values)
        self.start_tour("/", "portal_download_signed_document", login="portal")

    def _post_in_history(self, sign_request, body, token):
        return self.url_open(
            "/mail/message/post",
            json={
                "params": {
                    "thread_model": sign_request._name,
                    "thread_id": sign_request.id,
                    "post_data": {"body": body},
                    "token": token,
                }
            },
        ).json()

    @mute_logger("odoo.http")
    def test_the_signer_writes_in_the_history_and_the_request_link_does_not(self):
        sign_request = self.create_sign_request_1_role(
            self.partner_portal, self.env["res.partner"]
        )
        self.authenticate("portal", "portal")
        page = self.url_open(f"/my/signature/{sign_request.request_item_ids.id}")
        chatter = re.search(r'class="[^"]*o_portal_chatter[^>]*', page.text)[0]
        token = re.search(r'data-token="([^"]+)"', chatter)[1]
        self.assertNotEqual(token, sign_request.access_token)

        self.assertNotIn(
            "error", self._post_in_history(sign_request, "From the signer", token)
        )
        self.env.invalidate_all()
        self.assertEqual(sign_request.message_ids[0].author_id, self.partner_portal)
        refused = self._post_in_history(
            sign_request, "Through the request's view link", sign_request.access_token
        )
        self.assertIn("error", refused)

        self.authenticate(None, None)
        self.assertIn(
            "error",
            self._post_in_history(sign_request, "Anonymous, with the signer's", token),
            "the signer's link opens for the signer, signed in, alone",
        )
