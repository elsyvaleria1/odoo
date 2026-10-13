import base64
import hmac
import os
import re
import struct
import time

from lxml import html

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged

UNRECOGNIZED_UA = "Odoo/19.0 CFNetwork/1494.0.7 Darwin/23.4.0"
CHROME_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _totp_token(secret_b32):
    key = base64.b32decode(re.sub(r"\s", "", secret_b32).upper())
    mac = hmac.new(key, struct.pack(">Q", int(time.time() / 30)), "sha1").digest()
    offset = mac[-1] & 0xF
    code = struct.unpack_from(">I", mac, offset)[0] & 0x7FFFFFFF
    return str(code % 10**6).zfill(6)


@tagged("post_install", "-at_install")
class TestTrustedDevice(HttpCase):
    def _new_2fa_user(self, login, groups):
        secret = base64.b32encode(os.urandom(20)).decode()
        user = new_test_user(self.env, login, password=login, groups=groups, tz="UTC")
        user.sudo().with_context(mail_notify_force_send=False).write(
            {"totp_secret": secret}
        )
        self.env.flush_all()
        return user, secret

    def _csrf(self, response):
        return (
            html.fromstring(response.content)
            .xpath('//input[@name="csrf_token"]')[0]
            .get("value")
        )

    def _login_remembering_device(self, login, secret, user_agent):
        self.opener.headers["User-Agent"] = user_agent
        login_page = self.url_open("/web/login")
        totp_form = self.url_open(
            "/web/login",
            data={
                "login": login,
                "password": login,
                "csrf_token": self._csrf(login_page),
            },
        )
        self.assertIn("totp_token", totp_form.text, "expected the 2FA form")
        return self.url_open(
            "/web/login/totp",
            data={
                "totp_token": _totp_token(secret),
                "remember": "on",
                "csrf_token": self._csrf(totp_form),
            },
            allow_redirects=False,
        )

    def test_unrecognized_user_agent_still_registers_the_device(self):
        user, secret = self._new_2fa_user("td_ua", "base.group_user")

        response = self._login_remembering_device("td_ua", secret, UNRECOGNIZED_UA)

        self.assertEqual(response.status_code, 303, "login should have succeeded")
        self.assertEqual(len(user.totp_trust_ids), 1)
        self.assertIn("Unknown browser", user.totp_trust_ids.name)

    def test_recognized_user_agent_names_the_device(self):
        user, secret = self._new_2fa_user("td_chrome", "base.group_user")

        response = self._login_remembering_device("td_chrome", secret, CHROME_UA)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(user.totp_trust_ids.name, "Chrome on Linux")

    def test_portal_user_may_remember_a_device(self):
        self.env["ir.config_parameter"].sudo().set_param("portal.allow_api_keys", False)
        user, secret = self._new_2fa_user("td_portal", "base.group_portal")

        response = self._login_remembering_device("td_portal", secret, CHROME_UA)

        self.assertEqual(response.status_code, 303, "login should have succeeded")
        self.assertEqual(len(user.totp_trust_ids), 1)

    def test_public_user_may_not_register_a_device(self):
        public_user = self.env.ref("base.public_user")
        with self.assertRaises(AccessError):
            self.env["auth.totp.trust"].with_user(public_user)._issue("nope")

    def test_the_remembered_browser_carries_its_trust_until_revoked(self):
        user, secret = self._new_2fa_user("td_link", "base.group_user")
        self._login_remembering_device("td_link", secret, CHROME_UA)
        self.env.invalidate_all()
        trust = user.totp_trust_ids
        self.assertEqual(len(trust), 1)
        self.assertEqual(user.auth_client_ids.totp_trust_ids, trust)

        user.auth_client_ids.with_user(user)._revoke()

        self.assertFalse(trust.exists(), "revoking the device ends its 2FA trust")

    def test_an_expired_trust_leaves_no_dangling_link(self):
        user, secret = self._new_2fa_user("td_expired", "base.group_user")
        self._login_remembering_device("td_expired", secret, CHROME_UA)
        self.env.invalidate_all()
        device, trust = user.auth_client_ids, user.totp_trust_ids
        self.assertTrue(device.totp_trust_ids)
        self.env.cr.execute("DELETE FROM auth_totp_trust WHERE id = %s", [trust.id])
        self.env.invalidate_all()
        self.assertFalse(device.totp_trust_ids)
