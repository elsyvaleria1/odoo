
from lxml import html

from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.common import HttpCaseWithUserPortal

REVOKE_DEVICE_HOOK_CLASS = "o_totp_portal_revoke_device"


@tagged("post_install", "-at_install")
class TestRevokeDeviceHook(HttpCaseWithUserPortal):
    def _portal_user_with_a_trusted_device(self):
        user = self.user_portal
        user.sudo().with_context(mail_notify_force_send=False).write(
            {"totp_secret": "test"}
        )
        self.env["auth.totp.trust"].with_user(user).sudo()._issue("test-device")
        return user

    def test_trusted_device_row_carries_the_interaction_hook(self):
        user = self._portal_user_with_a_trusted_device()

        self.authenticate("portal", "portal")
        page = self.url_open("/my/security").text

        self.assertIn("test-device", page, "the trusted device should be listed")
        self.assertIn(
            REVOKE_DEVICE_HOOK_CLASS,
            page,
            "the per-device revoke control lost the class its interaction binds "
            "to; RevokeTrustedDevice will never attach",
        )
        self.assertTrue(user.totp_trust_ids)

    def test_a_device_holding_the_trust_is_badged(self):
        user = self._portal_user_with_a_trusted_device()
        trust = self.env["auth.totp.trust"].sudo().search([("user_id", "=", user.id)])
        self.assertEqual(len(trust), 1)
        Device = self.env["auth.user.client"].sudo()
        trusted, plain = Device.create(
            [
                {
                    "user_id": user.id,
                    "recognition_key_hash": "trusted",
                    "name": "Trusted laptop",
                    "totp_trust_ids": [Command.link(trust.id)],
                },
                {
                    "user_id": user.id,
                    "recognition_key_hash": "plain",
                    "name": "Plain laptop",
                },
            ]
        )

        self.authenticate("portal", "portal")
        page = html.fromstring(self.url_open("/my/security").content)

        badged = page.xpath(
            "//li[contains(@class, 'o_portal_device')]"
            "[.//span[contains(@class, 'o_portal_device_trusted')]]//span[@class='fw-bold']"
        )
        self.assertEqual([span.text.strip() for span in badged], [trusted.name])
        self.assertTrue(plain.active)

    def test_revoking_one_device_removes_it(self):
        user = self._portal_user_with_a_trusted_device()

        self.start_tour(
            "/my/security", "auth_portal_revoke_trusted_device", login="portal"
        )

        self.assertFalse(
            user.totp_trust_ids,
            "the tour reported success, so the device must actually be gone",
        )
