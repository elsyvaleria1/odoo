
from odoo.tests import TransactionCase, tagged

from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("post_install", "-at_install")
class TestMfaPolicy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.internal_user = mail_new_test_user(
            cls.env,
            login="totp_internal",
            email="totp.internal@example.com",
            groups="base.group_user",
        )
        cls.portal_user = mail_new_test_user(
            cls.env,
            login="totp_portal",
            email="totp.portal@example.com",
            groups="base.group_portal",
        )
        cls.icp = cls.env["ir.config_parameter"].sudo()

    def _set_policy(self, value):
        self.icp.set_param("auth_totp.policy", value)

    def test_no_policy_means_no_mail_mfa(self):
        self._set_policy(False)
        self.assertFalse(self.internal_user._get_mfa_type())

    def test_all_required_policy_covers_everyone(self):
        self._set_policy("all_required")
        self.assertEqual(self.internal_user._get_mfa_type(), "totp_mail")
        self.assertEqual(self.portal_user._get_mfa_type(), "totp_mail")

    def test_employee_policy_covers_internal_users_only(self):
        self._set_policy("employee_required")
        self.assertEqual(self.internal_user._get_mfa_type(), "totp_mail")
        self.assertFalse(self.portal_user._get_mfa_type())

    def test_mfa_url_points_to_totp_login(self):
        self._set_policy("all_required")
        self.assertEqual(self.internal_user._get_mfa_url(), "/web/login/totp")

    def test_rpc_requires_api_keys_under_policy(self):
        self.env["ir.config_parameter"].sudo().set_param("base.rpc_api_key_only", "0")
        self._set_policy("all_required")
        self.assertTrue(self.internal_user._is_rpc_api_key_only())
        self._set_policy(False)
        self.assertFalse(self.internal_user._is_rpc_api_key_only())
