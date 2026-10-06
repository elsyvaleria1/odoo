from odoo.libs.redact import mask_text, mask_url
from odoo.tests import BaseCase, tagged


@tagged("-at_install", "post_install")
class TestLinkSignatureRedaction(BaseCase):
    def test_a_link_signature_is_masked_wherever_it_is_logged(self):
        url = "/mail/view?model=sale.order&res_id=5&pid=3&hash=0a1b2c3d4e5f"
        self.assertEqual(
            mask_url(url),
            "/mail/view?model=sale.order&res_id=5&pid=3&hash=***REDACTED***",
        )
        self.assertNotIn("0a1b2c3d4e5f", mask_text(f"redirect to {url}"))
        self.assertNotIn(
            "0a1b2c3d4e5f", mask_url("/mail/view?_hash=0a1b2c3d4e5f&pid=3")
        )

    def test_a_hash_without_a_partner_is_no_signature(self):
        url = "/website/translations?hash=0a1b2c3d4e5f&lang=fr_FR"
        self.assertEqual(mask_url(url), url)

    def test_a_signed_link_inside_a_login_redirect_is_masked(self):
        url = (
            "/web/login?redirect=%2Fmail%2Fview%3Fmodel%3Dsale.order%26res_id%3D5"
            "%26access_token%3Dabc123%26pid%3D3%26hash%3D0a1b2c3d4e5f"
        )
        masked = mask_url(url)
        self.assertNotIn("abc123", masked)
        self.assertNotIn("0a1b2c3d4e5f", masked)

    def test_a_key_merely_ending_in_hash_is_not_a_signature(self):
        url = "/web/webclient/translations?translations_hash=0a1b2c3d4e5f"
        self.assertEqual(mask_url(url), url)
