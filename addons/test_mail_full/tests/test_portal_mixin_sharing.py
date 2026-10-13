from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestPortalMixinSharing(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Portal share partner", "email": "portal.share@test.example.com"},
        )
        cls.record = cls.env["mail.test.portal"].create(
            {"name": "Shareable record", "partner_id": cls.partner.id},
        )

    def test_token_is_minted_once_and_persists(self):
        self.assertFalse(self.record.access_token)

        token = self.record._portal_get_or_create_token()

        self.assertTrue(token)
        self.assertEqual(self.record.access_token, token)
        self.assertEqual(self.record._portal_get_or_create_token(), token)

    def test_share_url_direct_carries_token(self):
        url = self.record._get_share_url()

        self.assertIn("access_token=", url)
        self.assertIn(self.record.access_token, url)
        self.assertNotIn("/mail/view", url)

    def test_share_url_redirect_carries_model_and_res_id(self):
        url = self.record._get_share_url(redirect=True)

        self.assertIn("/mail/view", url)
        self.assertIn("model=mail.test.portal", url)
        self.assertIn(f"res_id={self.record.id}", url)

    def test_share_url_without_token(self):
        url = self.record._get_share_url(share_token=False)

        self.assertNotIn("access_token", url)
        self.assertFalse(self.record.access_token)

    def test_share_url_with_pid_adds_signed_hash(self):
        url = self.record._get_share_url(pid=self.partner.id)

        self.assertIn(f"pid={self.partner.id}", url)
        self.assertIn("hash=", url)
        self.assertIn(self.record._sign_token(self.partner.id), url)

    def test_access_warning_defaults_to_empty(self):
        self.assertEqual(self.record.access_warning, "")

    def test_share_url_denied_without_read_access(self):
        portal_user = new_test_user(
            self.env, login="portal_share_denied", groups="base.group_portal"
        )

        with self.assertRaises(AccessError):
            self.record.with_user(portal_user)._get_share_url()

        self.assertFalse(self.record.access_token)
