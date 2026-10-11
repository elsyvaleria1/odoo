import time
from datetime import datetime, timedelta
from unittest.mock import patch

import lxml.html

import odoo.http
from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tests.common import HOST
from odoo.tools import mute_logger

from odoo.addons.auth_totp.controllers.home import TRUSTED_DEVICE_COOKIE
from odoo.addons.auth_totp.models.totp import TOTP


class TestAuthTimeout(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            "foo",
            groups="base.group_user,base.group_erp_manager,base.group_system",
        )

    def test_user_auth_methods(self):
        self.assertEqual(self.user._get_auth_methods(), ["password"])

        config = self.env["res.config.settings"].create({})
        config.auth_totp_enforce = True
        config.auth_totp_policy = "employee_required"
        config.execute()
        self.assertEqual(self.user._get_auth_methods(), ["totp_mail", "password"])

        self.user.totp_secret = "foo"
        self.assertEqual(self.user._get_auth_methods(), ["totp", "password"])

        self.env["auth.passkey.key"].create(
            {
                "name": "foo",
                "credential_identifier": "foo",
                "public_key": "foo",
                "create_uid": self.user.id,
            }
        )
        self.assertEqual(
            self.user._get_auth_methods(), ["webauthn", "totp", "password"]
        )

    def test_user_lock_timeouts(self):
        group1, group2, group3 = self.user.group_ids[:3]

        group1.lock_timeout_inactivity = 15
        group1.lock_timeout = 24 * 60
        group1.lock_timeout_mfa = True
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(86400, True)],
                "lock_timeout_inactivity": [(900, False)],
            },
        )

        group2.lock_timeout_inactivity = 60
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(86400, True)],
                "lock_timeout_inactivity": [(900, False)],
            },
        )

        group2.lock_timeout_inactivity_mfa = True
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(86400, True)],
                "lock_timeout_inactivity": [(900, False), (3600, True)],
            },
        )

        group2.lock_timeout_inactivity = 6
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(86400, True)],
                "lock_timeout_inactivity": [(360, True)],
            },
        )

        group2.lock_timeout = 48 * 60
        group2.lock_timeout_mfa = True
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(86400, True)],
                "lock_timeout_inactivity": [(360, True)],
            },
        )

        group2.lock_timeout = 12 * 60
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(43200, True)],
                "lock_timeout_inactivity": [(360, True)],
            },
        )

        group2.lock_timeout_mfa = False
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(43200, False), (86400, True)],
                "lock_timeout_inactivity": [(360, True)],
            },
        )

        group3.lock_timeout = 18 * 60
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(43200, False), (86400, True)],
                "lock_timeout_inactivity": [(360, True)],
            },
        )

        group3.lock_timeout_mfa = True
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(43200, False), (64800, True)],
                "lock_timeout_inactivity": [(360, True)],
            },
        )

        group3.lock_timeout = 6 * 60
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(21600, True)],
                "lock_timeout_inactivity": [(360, True)],
            },
        )

        group3.lock_timeout_inactivity = 3
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(21600, True)],
                "lock_timeout_inactivity": [(180, False), (360, True)],
            },
        )

        group3.lock_timeout_inactivity_mfa = True
        self.assertEqual(
            self.user._get_lock_timeouts(),
            {
                "lock_timeout": [(21600, True)],
                "lock_timeout_inactivity": [(180, True)],
            },
        )


@tagged("post_install", "-at_install")
class TestAuthTimeoutHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            "foobarbaz",
            groups="base.group_user,base.group_erp_manager,base.group_system",
        )

        cls.totp_code = 111111
        cls.totp_counter = 0
        origin_totp_match = TOTP.match

        def match(self, code, *args, **kwargs):
            if code == cls.totp_code:
                cls.totp_counter += 1
                return cls.totp_counter
            return origin_totp_match(self, code, *args, **kwargs)

        cls.classPatch(TOTP, "match", match)

        cls.passkey_credential_id = "foo"
        cls.passkey_credential_id_base64url = (
            "Zm9v"
        )
        PasskeyClass = cls.env.registry["auth.passkey.key"]
        origin_passkey_verify_registration_options = (
            PasskeyClass._get_registration_credential
        )

        def _get_registration_credential(self, registration):
            if registration.get("id") == cls.passkey_credential_id:
                return {
                    "credential_id": cls.passkey_credential_id.encode(),
                    "credential_public_key": cls.passkey_credential_id.encode(),
                }
            return origin_passkey_verify_registration_options(self, registration)

        cls.classPatch(
            PasskeyClass, "_get_registration_credential", _get_registration_credential
        )

        origin_passkey_verify_auth = PasskeyClass._get_new_sign_count

        def _get_new_sign_count(self, auth, public_key, sign_count):
            if (
                auth.get("id") == cls.passkey_credential_id_base64url
            ):
                return 1
            return origin_passkey_verify_auth(self, auth, public_key, sign_count)

        cls.classPatch(PasskeyClass, "_get_new_sign_count", _get_new_sign_count)

    def rpc(self, model, method, *args, **kwargs):
        return self.url_open(
            "/web/dataset/call_kw",
            json={
                "params": {
                    "model": model,
                    "method": method,
                    "args": args,
                    "kwargs": kwargs,
                }
            },
        ).json()

    def set_session_create_time(self, session_id, timestamp):
        session = odoo.http.root.session_store.get(session_id)
        session["create_time"] = timestamp
        odoo.http.root.session_store.save(session)

    def set_session_last_check_identity(self, session_id, timestamp):
        session = odoo.http.root.session_store.get(session_id)
        session["identity-check-last"] = timestamp
        odoo.http.root.session_store.save(session)

    def set_session_next_check_identity(self, session_id, timestamp):
        session = odoo.http.root.session_store.get(session_id)
        session["identity-check-next"] = timestamp
        odoo.http.root.session_store.save(session)

    def set_auth_totp_mail(self):
        config = self.env["res.config.settings"].create({})
        config.auth_totp_enforce = True
        config.auth_totp_policy = "employee_required"
        config.execute()

    def set_auth_totp(self):
        action = self.rpc("res.users", "action_totp_enable_wizard", [self.user.id])[
            "result"
        ]
        self.rpc(
            action["res_model"],
            "enable",
            [action["res_id"]],
            context={"code": str(self.totp_code)},
        )

    def set_auth_passkey(self):
        wizard_id = self.rpc(
            "wizard.auth.passkey.key.create", "create", {"name": "foo"}
        )["result"]
        self.rpc(
            "wizard.auth.passkey.key.create",
            "action_generate_key",
            wizard_id,
            {"id": self.passkey_credential_id},
        )

    def check_identity(self, credentials):
        return self.url_open(
            "/auth-timeout/session/check-identity", json={"params": credentials}
        )

    def assertMustCheckIdentity(self):
        result = self.rpc("res.users", "read", [self.user.id], ["login"])
        self.assertEqual(
            result.get("error", {}).get("data", {}).get("name"),
            "odoo.addons.auth_timeout.models.ir_http.CheckIdentityException",
        )

    def assertSessionExpired(self):
        result = self.rpc("res.users", "read", [self.user.id], ["login"])
        self.assertEqual(
            result.get("error", {}).get("data", {}).get("name"),
            "odoo.http.SessionExpiredException",
        )

    def assertMustNotCheckIdentity(self):
        result = self.rpc("res.users", "read", [self.user.id], ["login"])
        self.assertTrue(result.get("result"))

    def test_check_identity_exception(self):
        group = self.user.group_ids[0]
        session_id = self.authenticate(self.user.login, self.user.login).sid

        group.lock_timeout_inactivity = 15
        self.set_session_next_check_identity(session_id, time.time())

        self.assertMustCheckIdentity()

        self.check_identity({"type": "password", "password": self.user.login})

        self.assertMustNotCheckIdentity()

        group.lock_timeout = 24 * 60
        self.set_session_create_time(session_id, time.time() - 25 * 60 * 60)

        self.assertSessionExpired()

    @mute_logger("odoo.addons.base.models.res_users")
    def test_check_identity_is_behind_the_login_cooldown(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "base.login_cooldown_after", "2"
        )
        group = self.user.group_ids[0]
        session_id = self.authenticate(self.user.login, self.user.login).sid
        group.lock_timeout_inactivity = 15
        self.set_session_next_check_identity(session_id, time.time())

        for _attempt in range(2):
            self.check_identity({"type": "password", "password": "wrong"})
        self.check_identity({"type": "password", "password": self.user.login})

        self.assertMustCheckIdentity()

    def test_authentication_methods(self):
        group = self.user.group_ids[0]
        group.lock_timeout_inactivity = 15

        session_id = self.authenticate(self.user.login, self.user.login).sid
        self.set_session_last_check_identity(session_id, time.time())

        self.set_session_next_check_identity(session_id, time.time() - 16 * 60)
        self.assertMustCheckIdentity()
        self.check_identity({"type": "password", "password": self.user.login})
        self.assertMustNotCheckIdentity()

        self.set_auth_totp_mail()
        self.set_session_next_check_identity(session_id, time.time() - 16 * 60)
        self.assertMustCheckIdentity()
        self.check_identity({"type": "totp_mail", "token": str(self.totp_code)})
        self.assertMustNotCheckIdentity()

        self.set_auth_totp()
        self.set_session_next_check_identity(session_id, time.time() - 16 * 60)
        self.assertMustCheckIdentity()
        self.check_identity({"type": "totp", "token": str(self.totp_code)})
        self.assertMustNotCheckIdentity()

        self.set_auth_passkey()

        self.set_session_next_check_identity(session_id, time.time() - 16 * 60)
        self.assertMustCheckIdentity()
        self.check_identity(
            {
                "type": "webauthn",
                "webauthn_response": json_dumps(
                    {"id": self.passkey_credential_id_base64url}
                ),
            }
        )
        self.assertMustNotCheckIdentity()

    def test_multiple_lock_timeouts_mfa(self):
        group1, group2 = self.user.group_ids[:2]

        group1.lock_timeout_inactivity = 15
        group1.lock_timeout_inactivity_mfa = False
        group2.lock_timeout_inactivity = 60
        group2.lock_timeout_inactivity_mfa = True

        config = self.env["res.config.settings"].create({})
        config.auth_totp_enforce = True
        config.auth_totp_policy = "employee_required"
        config.execute()

        session_id = self.authenticate(self.user.login, self.user.login).sid

        self.set_session_next_check_identity(session_id, time.time() - 30 * 60)

        self.assertMustCheckIdentity()

        self.check_identity({"type": "password", "password": self.user.login})

        self.assertMustNotCheckIdentity()

        self.set_session_next_check_identity(session_id, time.time() - 90 * 60)

        self.assertMustCheckIdentity()

        self.check_identity({"type": "password", "password": self.user.login})

        self.assertMustCheckIdentity()

        self.check_identity({"type": "password", "password": self.user.login})

        self.assertMustCheckIdentity()

        self.check_identity(
            {"type": "totp_mail", "token": self.user._get_totp_mail_code()[0]}
        )

        self.assertMustNotCheckIdentity()

    def test_multiple_inactivity_timeouts_mfa(self):
        group1, group2 = self.user.group_ids[:2]

        group1.lock_timeout_inactivity = 15
        group1.lock_timeout_inactivity_mfa = False
        group2.lock_timeout_inactivity = 30
        group2.lock_timeout_inactivity_mfa = True

        config = self.env["res.config.settings"].create({})
        config.auth_totp_enforce = True
        config.auth_totp_policy = "employee_required"
        config.execute()

        session_id = self.authenticate(self.user.login, self.user.login).sid

        self.set_session_next_check_identity(session_id, time.time() - 10 * 60)

        self.assertMustCheckIdentity()

        self.check_identity({"type": "password", "password": self.user.login})

        self.assertMustNotCheckIdentity()

        self.set_session_next_check_identity(session_id, time.time() - 16 * 60)

        self.assertMustCheckIdentity()

        self.check_identity({"type": "password", "password": self.user.login})

        self.assertMustCheckIdentity()

        self.check_identity({"type": "password", "password": self.user.login})

        self.assertMustCheckIdentity()

        self.check_identity(
            {"type": "totp_mail", "token": self.user._get_totp_mail_code()[0]}
        )

        self.assertMustNotCheckIdentity()

    def test_remember_device(self):
        group = self.user.group_ids[0]
        group.lock_timeout = 24 * 60
        group.lock_timeout_mfa = True

        session_id = self.authenticate(self.user.login, self.user.login).sid
        self.set_session_last_check_identity(session_id, time.time())
        self.set_auth_totp()

        self.opener.cookies.clear()
        del self.session

        csrf_token = (
            lxml.html.fromstring(self.url_open("/web/login").content)
            .xpath('//input[@name="csrf_token"]')[0]
            .get("value")
        )
        res = self.url_open(
            "/web/login",
            data={
                "login": self.user.login,
                "password": self.user.login,
                "csrf_token": csrf_token,
            },
        )
        self.assertIn("/web/login/totp", res.url)
        csrf_token = (
            lxml.html.fromstring(res.content)
            .xpath('//input[@name="csrf_token"]')[0]
            .get("value")
        )
        res = self.url_open(
            "/web/login/totp",
            data={
                "totp_token": self.totp_code,
                "remember": True,
                "csrf_token": csrf_token,
            },
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            },
        )

        expires = datetime.fromtimestamp(
            self.opener.cookies._cookies[HOST]["/"][TRUSTED_DEVICE_COOKIE].expires
        )
        self.assertLessEqual(
            expires, datetime.now() + timedelta(seconds=group.lock_timeout * 60)
        )
        self.assertGreater(
            expires, datetime.now() + timedelta(seconds=group.lock_timeout * 60 - 60)
        )

        device = self.env["auth.totp.trust"].search(
            [("user_id", "=", self.user.id)], order="id DESC", limit=1
        )
        self.assertLessEqual(
            device.expiration_date,
            datetime.now() + timedelta(seconds=group.lock_timeout * 60),
        )
        self.assertGreater(
            device.expiration_date,
            datetime.now() + timedelta(seconds=group.lock_timeout * 60 - 60),
        )

    def test_auth_timeout_tour(self):
        session_id = self.authenticate(self.user.login, self.user.login).sid
        self.set_session_last_check_identity(session_id, time.time())
        self.set_auth_totp_mail()
        self.set_auth_totp()
        self.set_auth_passkey()

        with patch.object(
            self.env.registry["res.groups"],
            "_get_lock_timeouts",
            return_value={
                "lock_timeout": [],
                "lock_timeout_inactivity": [
                    (1, False)
                ],
            },
        ):
            self.start_tour(
                "/odoo",
                "auth_timeout_tour_lock_timeout_inactivity",
                login=self.user.login,
            )

        with patch.object(
            self.env.registry["res.groups"],
            "_get_lock_timeouts",
            return_value={
                "lock_timeout": [],
                "lock_timeout_inactivity": [(1, True)],
            },
        ):
            self.start_tour(
                "/odoo",
                "auth_timeout_tour_lock_timeout_inactivity_2fa",
                login=self.user.login,
            )
