from contextlib import contextmanager
from unittest.mock import patch

from lxml import html

from odoo.http import request
from odoo.libs.json import dumps as json_dumps
from odoo.tests import tagged
from odoo.tools import SQL, mute_logger

from odoo.addons.base.tests.common import HttpCaseWithUserDemo


class PasskeyTest(HttpCaseWithUserDemo):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.admin_user = cls.env.ref("base.user_admin")

        cls.passkeys = {
            "test-yubikey": {
                "user": cls.admin_user,
                "credential_identifier": "L2p6jvcWuCMTRmkZHKqqvQbz0Dhk3JbJOx1F8ci99nSNjlfx3Z7nkigMdUACLggB",
                "public_key": "pQECAyYgASFYIC9qeo73FrgjE0ZpGRwxLIG50L4kNlhj2DIyqSc_YiRSIlgg2q6bL2-IoJ6j_GkVTdfPKyx8RF5e8wzX9-Zk37AykM8=",
                "host": "http://localhost:8069",
                "registration": {
                    "challenge": "Uoa6M5jEP7I3ToyK9QA0vf8IcsezfeJk0rgs1pLUWrMgF9vd0-7Dv5iV3xW7r70-YqkweRXhACmDPmhHKtAIeQ",
                    "response": {
                        "id": "L2p6jvcWuCMTRmkZHKqqvQbz0Dhk3JbJOx1F8ci99nSNjlfx3Z7nkigMdUACLggB",
                        "rawId": "L2p6jvcWuCMTRmkZHKqqvQbz0Dhk3JbJOx1F8ci99nSNjlfx3Z7nkigMdUACLggB",
                        "response": {
                            "attestationObject": "o2NmbXRkbm9uZWdhdHRTdG10oGhhdXRoRGF0YVjCSZYN5YgOjGh0NBcPZHZgW4_krrmihjLHmVzzuoMdl2PFAAAAAgAAAAAAAAAAAAAAAAAAAAAAMC9qeo73FrgjE0ZpGRyqqr0G89A4ZNyWyTsdRfHIvfZ0jY5X8d2e55IoDHVAAi4IAaUBAgMmIAEhWCAvanqO9xa4IxNGaRkcMSyBudC-JDZYY9gyMqknP2IkUiJYINqumy9viKCeo_xpFU3XzyssfEReXvMM1_fmZN-wMpDPoWtjcmVkUHJvdGVjdAI",
                            "clientDataJSON": "eyJ0eXBlIjoid2ViYXV0aG4uY3JlYXRlIiwiY2hhbGxlbmdlIjoiVW9hNk01akVQN0kzVG95SzlRQTB2ZjhJY3NlemZlSmswcmdzMXBMVVdyTWdGOXZkMC03RHY1aVYzeFc3cjcwLVlxa3dlUlhoQUNtRFBtaEhLdEFJZVEiLCJvcmlnaW4iOiJodHRwOi8vbG9jYWxob3N0OjgwNjkiLCJjcm9zc09yaWdpbiI6ZmFsc2V9",
                            "transports": [
                                "nfc",
                                "usb",
                            ],
                            "publicKeyAlgorithm": -7,
                            "publicKey": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEL2p6jvcWuCMTRmkZHDEsgbnQviQ2WGPYMjKpJz9iJFLarpsvb4ignqP8aRVN188rLHxEXl7zDNf35mTfsDKQzw",
                            "authenticatorData": "SZYN5YgOjGh0NBcPZHZgW4_krrmihjLHmVzzuoMdl2PFAAAAAgAAAAAAAAAAAAAAAAAAAAAAMC9qeo73FrgjE0ZpGRyqqr0G89A4ZNyWyTsdRfHIvfZ0jY5X8d2e55IoDHVAAi4IAaUBAgMmIAEhWCAvanqO9xa4IxNGaRkcMSyBudC-JDZYY9gyMqknP2IkUiJYINqumy9viKCeo_xpFU3XzyssfEReXvMM1_fmZN-wMpDPoWtjcmVkUHJvdGVjdAI",
                        },
                        "type": "public-key",
                        "clientExtensionResults": {},
                        "authenticatorAttachment": "cross-platform",
                    },
                },
                "auth": {
                    "challenge": "DKrw5IeFiL0w_y5oB0RATPrqG1eFOC2P7yEiXCstBRuZYbSBBkAWfhAIInkMqWjYIN8vbKn7J3PMX_ThznHpqg",
                    "response": {
                        "id": "L2p6jvcWuCMTRmkZHKqqvQbz0Dhk3JbJOx1F8ci99nSNjlfx3Z7nkigMdUACLggB",
                        "rawId": "L2p6jvcWuCMTRmkZHKqqvQbz0Dhk3JbJOx1F8ci99nSNjlfx3Z7nkigMdUACLggB",
                        "response": {
                            "authenticatorData": "SZYN5YgOjGh0NBcPZHZgW4_krrmihjLHmVzzuoMdl2MFAAAAAw",
                            "clientDataJSON": "eyJ0eXBlIjoid2ViYXV0aG4uZ2V0IiwiY2hhbGxlbmdlIjoiREtydzVJZUZpTDB3X3k1b0IwUkFUUHJxRzFlRk9DMlA3eUVpWENzdEJSdVpZYlNCQmtBV2ZoQUlJbmtNcVdqWUlOOHZiS243SjNQTVhfVGh6bkhwcWciLCJvcmlnaW4iOiJodHRwOi8vbG9jYWxob3N0OjgwNjkiLCJjcm9zc09yaWdpbiI6ZmFsc2V9",
                            "signature": "MEUCIQD5iaPp48QMS3amx4PS89kv_EBAo3bBkaWnLzWlSgFSXgIgLWKEv9xR_ZwVXZbw2zx459RKbrQuAcd-UqD4gJw1lWY",
                            "userHandle": "Mg",
                        },
                        "type": "public-key",
                        "clientExtensionResults": {},
                        "authenticatorAttachment": "cross-platform",
                    },
                },
            },
            "test-yubikey-nano": {
                "user": cls.admin_user,
                "credential_identifier": "wtw0u7D8rp7nq7WBWFCt_FRhEHpU6EHvEgTn3BBid5N-UE5a9XCzS8NaVuh7ydFz",
                "public_key": "pQECAyYgASFYIMLcNLuw_K6e56u1gVioLcAJF8v8eUw7kfqTOqDdl7nFIlggFSs_nZWewd_JqzeWzXmJ6Wmn_nKuo82rCdoOZ-oewOU=",
                "host": "http://localhost:8069",
                "auth": {
                    "challenge": "oj09zruUyqUMIFO0ol5UltUd955Qqw9iche5w_g9k6jByR69ioWtnC-RWLRie_8sqHO_T2bICJplaQNPRxfpeA",
                    "response": {
                        "id": "wtw0u7D8rp7nq7WBWFCt_FRhEHpU6EHvEgTn3BBid5N-UE5a9XCzS8NaVuh7ydFz",
                        "rawId": "wtw0u7D8rp7nq7WBWFCt_FRhEHpU6EHvEgTn3BBid5N-UE5a9XCzS8NaVuh7ydFz",
                        "response": {
                            "authenticatorData": "SZYN5YgOjGh0NBcPZHZgW4_krrmihjLHmVzzuoMdl2MFAAAABg",
                            "clientDataJSON": "eyJ0eXBlIjoid2ViYXV0aG4uZ2V0IiwiY2hhbGxlbmdlIjoib2owOXpydVV5cVVNSUZPMG9sNVVsdFVkOTU1UXF3OWljaGU1d19nOWs2akJ5UjY5aW9XdG5DLVJXTFJpZV84c3FIT19UMmJJQ0pwbGFRTlBSeGZwZUEiLCJvcmlnaW4iOiJodHRwOi8vbG9jYWxob3N0OjgwNjkiLCJjcm9zc09yaWdpbiI6ZmFsc2V9",
                            "signature": "MEUCIDj-tI1yRGqnqd6uZeuInPaGY0yNYwC-5W4d024zwUs0AiEApJAst0t7G40ZRp1_TIKbftD-p9BkmafTPZBBe4Ps0P0",
                            "userHandle": "Mg",
                        },
                        "type": "public-key",
                        "clientExtensionResults": {},
                        "authenticatorAttachment": "cross-platform",
                    },
                },
            },
            "test-keepassxc": {
                "user": cls.user_demo,
                "credential_identifier": "y6aJVJsvvSSkbwTeGZ1FbQP_jCDho7EBPwZq-3lAjQ0",
                "public_key": "pQECAyYgASFYICjw-NoCHMkYYbRo8Q4SgJ4tZc8BSEmuEI0XmA6hUqR_IlggjtuBgyhwnr7PqABF2o8vCniMVa7_mTG6_l9Pc4eI4mo=",
                "host": "https://localhost:8888",
                "supports_sign_count": False,
                "auth": {
                    "challenge": "LNpV0dPIMtmpSwGenIH_h1VycQuAgFgQRJ9TPKBoNayScNAErS-rsnaU19n7_AaXzeiYRg3nGI3yuH0ai6UPXA",
                    "response": {
                        "id": "y6aJVJsvvSSkbwTeGZ1FbQP_jCDho7EBPwZq-3lAjQ0",
                        "rawId": "y6aJVJsvvSSkbwTeGZ1FbQP_jCDho7EBPwZq-3lAjQ0",
                        "response": {
                            "authenticatorData": "SZYN5YgOjGh0NBcPZHZgW4_krrmihjLHmVzzuoMdl2MFAAAAAA",
                            "clientDataJSON": "eyJjaGFsbGVuZ2UiOiJMTnBWMGRQSU10bXBTd0dlbklIX2gxVnljUXVBZ0ZnUVJKOVRQS0JvTmF5U2NOQUVyUy1yc25hVTE5bjdfQWFYemVpWVJnM25HSTN5dUgwYWk2VVBYQSIsImNyb3NzT3JpZ2luIjpmYWxzZSwib3JpZ2luIjoiaHR0cHM6Ly9sb2NhbGhvc3Q6ODg4OCIsInR5cGUiOiJ3ZWJhdXRobi5nZXQifQ",
                            "signature": "MEYCIQCqkh2NBQQao5uDTaBKyNhiEpnk4jgbH-PjdLAul9-d0gIhAMObtNTbaEMUILdNgCT01BKNN4NHRzkzsGaDN2Ozu0WX",
                            "userHandle": "Ng",
                        },
                        "type": "public-key",
                        "clientExtensionResults": {},
                        "authenticatorAttachment": "platform",
                    },
                },
            },
            "test-user-verification": {
                "user": cls.user_demo,
                "credential_identifier": "723TCjL_RdQHFk3Ysp-HUymcWoazFi3ZdfZ1bIn6MYC5bAXvI6B-j8G-UA1taMO0",
                "public_key": "pQECAyYgASFYIO9t0woy_0XUBxZN2LKpzFmzmauPpdgt7B1EnoVXHL56IlggUJWIu-UCOAFOCAMUXDXb36pJ49aWNI9Z7njiLQt7amw=",
                "host": "http://localhost:8069",
                "auth": {
                    "challenge": "MTIzNDU",
                    "response": {
                        "id": "723TCjL_RdQHFk3Ysp-HUymcWoazFi3ZdfZ1bIn6MYC5bAXvI6B-j8G-UA1taMO0",
                        "rawId": "723TCjL_RdQHFk3Ysp-HUymcWoazFi3ZdfZ1bIn6MYC5bAXvI6B-j8G-UA1taMO0",
                        "response": {
                            "authenticatorData": "SZYN5YgOjGh0NBcPZHZgW4_krrmihjLHmVzzuoMdl2MBAAAADg",
                            "clientDataJSON": "eyJ0eXBlIjoid2ViYXV0aG4uZ2V0IiwiY2hhbGxlbmdlIjoiTVRJek5EVSIsIm9yaWdpbiI6Imh0dHA6Ly9sb2NhbGhvc3Q6ODA2OSIsImNyb3NzT3JpZ2luIjpmYWxzZX0",
                            "signature": "MEQCIFYAdM82D9otAfX2s6WY4CyH8i733Km-3TZSYcfwDmbqAiB6OXGuoaMgX13v6LWCIdkCRY9ZTYhNzhXFTs1Wp7-zkQ",
                            "userHandle": "Mg",
                        },
                        "type": "public-key",
                        "clientExtensionResults": {},
                        "authenticatorAttachment": "cross-platform",
                    },
                },
            },
        }

        for key, values in cls.passkeys.items():
            cls.cr.execute(
                SQL(
                    """
                INSERT INTO auth_passkey_key (name, credential_identifier, public_key, create_uid, write_date, create_date)
                VALUES (%s, %s, %s, %s, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
                RETURNING id
                """,
                    key,
                    values["credential_identifier"],
                    values["public_key"],
                    values["user"].id,
                )
            )
            passkey_id = cls.cr.fetchone()
            values["passkey"] = cls.env["auth.passkey.key"].browse(passkey_id)

    def rpc(self, model, method, *args, **kwargs):
        return self.url_open(
            "/web/dataset/call_kw",
            headers={"Content-Type": "application/json"},
            data=json_dumps(
                {
                    "params": {
                        "model": model,
                        "method": method,
                        "args": args,
                        "kwargs": kwargs,
                    },
                }
            ),
        ).json()

    @contextmanager
    def patch_start_auth(self, challenge):
        origin_start_auth = self.env.registry["auth.passkey.key"]._start_auth

        def _start_auth(self):
            res = origin_start_auth(self)
            res["challenge"] = request.session["webauthn_challenge"] = challenge
            return res

        with patch.object(
            self.env.registry["auth.passkey.key"], "_start_auth", _start_auth
        ):
            yield

    @contextmanager
    def patch_start_registration(self, challenge):
        origin_start_registration = self.env.registry[
            "auth.passkey.key"
        ]._start_registration

        def _start_registration(self):
            res = origin_start_registration(self)
            res["challenge"] = request.session["webauthn_challenge"] = challenge
            return res

        with patch.object(
            self.env.registry["auth.passkey.key"],
            "_start_registration",
            _start_registration,
        ):
            yield

    def test_registration(self):
        passkey = self.passkeys["test-yubikey"]
        registration = passkey["registration"]
        webauthn_challenge, webauthn_response = (
            registration["challenge"],
            registration["response"],
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", passkey["host"]
        )
        with self.patch_start_registration(webauthn_challenge):
            self.admin_user.auth_passkey_key_ids.unlink()

            self.authenticate(self.admin_user.login, self.admin_user.login)

            wizard_id = self.rpc(
                "res.users", "action_create_passkey", self.admin_user.id
            )["result"]["res_id"]

            action = self.rpc(
                "wizard.res.users.check.identity",
                "run_check",
                wizard_id,
                context={"password": self.admin_user.login},
            )["result"]

            wizard_id = self.rpc(
                action["res_model"], "create", {"name": "test-yubikey"}
            )["result"]

            response = self.rpc(
                action["res_model"], "action_generate_key", wizard_id, webauthn_response
            )

            self.assertTrue(response.get("result"))
            self.assertFalse(response.get("error"))
            self.assertEqual(len(self.admin_user.auth_passkey_key_ids), 1)
            self.assertEqual(self.admin_user.auth_passkey_key_ids.name, "test-yubikey")
            self.assertEqual(self.admin_user.auth_passkey_key_ids.sign_count, 0)

    def test_authentication(self):
        for key in ["test-yubikey", "test-yubikey-nano", "test-keepassxc"]:
            passkey = self.passkeys[key]
            auth = passkey["auth"]
            webauthn_challenge, webauthn_response = auth["challenge"], auth["response"]
            self.env["ir.config_parameter"].sudo().set_param(
                "web.base.url", passkey["host"]
            )
            sign_count = passkey["passkey"].sign_count

            with self.patch_start_auth(webauthn_challenge):
                csrf_token = (
                    html.fromstring(self.url_open("/web/login").content)
                    .xpath('//input[@name="csrf_token"]')[0]
                    .get("value")
                )

                self.url_open(
                    "/auth/passkey/start-auth",
                    "{}",
                    headers={"Content-Type": "application/json"},
                )

                response = self.url_open(
                    "/web/login",
                    data={
                        "type": "webauthn",
                        "webauthn_response": json_dumps(webauthn_response),
                        "csrf_token": csrf_token,
                        "password": "",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.headers.get("Set-Cookie"))
                if passkey.get("supports_sign_count", True):
                    self.assertGreater(passkey["passkey"].sign_count, sign_count)
                else:
                    self.assertEqual(passkey["passkey"].sign_count, sign_count)

                csrf_token = (
                    html.fromstring(self.url_open("/web/login").content)
                    .xpath('//input[@name="csrf_token"]')[0]
                    .get("value")
                )
                response = self.url_open(
                    "/web/login",
                    data={
                        "type": "webauthn",
                        "webauthn_response": json_dumps(webauthn_response),
                        "csrf_token": csrf_token,
                    },
                )
                self.assertEqual(response.status_code, 200)
                error = (
                    html.fromstring(response.content)
                    .xpath('//p[@class="alert alert-danger"]')[0]
                    .text.strip()
                )
                self.assertEqual(error, "Cannot find a challenge for this session")

    def test_check_identity(self):
        for key in ["test-yubikey", "test-yubikey-nano", "test-keepassxc"]:
            passkey = self.passkeys[key]
            user, auth = passkey["user"], passkey["auth"]
            webauthn_challenge, webauthn_response = auth["challenge"], auth["response"]
            self.env["ir.config_parameter"].sudo().set_param(
                "web.base.url", passkey["host"]
            )
            sign_count = passkey["passkey"].sign_count

            with self.patch_start_auth(webauthn_challenge):
                self.authenticate(user.login, user.login)

                wizard_id = self.rpc(
                    "res.users", "action_open_api_key_wizard", user.id
                )["result"]["res_id"]

                self.url_open(
                    "/auth/passkey/start-auth",
                    "{}",
                    headers={"Content-Type": "application/json"},
                )

                response = self.rpc(
                    "wizard.res.users.check.identity",
                    "run_check",
                    wizard_id,
                    context={"password": json_dumps(webauthn_response)},
                )

                self.assertTrue(response.get("result"))
                self.assertFalse(response.get("error"))
                if passkey.get("supports_sign_count", True):
                    self.assertGreater(passkey["passkey"].sign_count, sign_count)
                    sign_count = passkey["passkey"].sign_count
                else:
                    self.assertEqual(passkey["passkey"].sign_count, sign_count)

                with mute_logger("odoo.http"):
                    response = self.rpc(
                        "wizard.res.users.check.identity",
                        "run_check",
                        wizard_id,
                        context={"password": json_dumps(webauthn_response)},
                    )

                self.assertFalse(response.get("result"))
                self.assertTrue(response.get("error"))
                self.assertEqual(
                    response["error"]["data"]["name"], "odoo.exceptions.UserError"
                )
                self.assertEqual(
                    response["error"]["data"]["message"],
                    "Incorrect Passkey. Please provide a valid passkey or use a different authentication method.",
                )
                self.assertEqual(passkey["passkey"].sign_count, sign_count)

                self.url_open(
                    "/auth/passkey/start-auth",
                    "{}",
                    headers={"Content-Type": "application/json"},
                )

                with mute_logger("odoo.http"):
                    response = self.rpc(
                        "wizard.res.users.check.identity",
                        "run_check",
                        wizard_id,
                        context={"password": json_dumps(webauthn_response)},
                    )

                if passkey.get("supports_sign_count", True):
                    self.assertFalse(response.get("result"))
                    self.assertTrue(response.get("error"))
                else:
                    self.assertTrue(response.get("result"))
                    self.assertFalse(response.get("error"))

                self.assertEqual(passkey["passkey"].sign_count, sign_count)

            self.url_open(
                "/auth/passkey/start-auth",
                "{}",
                headers={"Content-Type": "application/json"},
            )
            with mute_logger("odoo.http"):
                response = self.rpc(
                    "wizard.res.users.check.identity",
                    "run_check",
                    wizard_id,
                    context={"password": json_dumps(webauthn_response)},
                )
            self.assertFalse(response.get("result"))
            self.assertTrue(response.get("error"))
            self.assertEqual(passkey["passkey"].sign_count, sign_count)

    def test_check_user_verification(self):
        passkey = self.passkeys["test-user-verification"]
        webauthn_challenge, webauthn_response = (
            passkey["auth"]["challenge"],
            passkey["auth"]["response"],
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", passkey["host"]
        )

        with self.patch_start_auth(webauthn_challenge):
            csrf_token = (
                html.fromstring(self.url_open("/web/login").content)
                .xpath('//input[@name="csrf_token"]')[0]
                .get("value")
            )
            self.url_open(
                "/auth/passkey/start-auth",
                "{}",
                headers={"Content-Type": "application/json"},
            )
            response = self.url_open(
                "/web/login",
                data={
                    "type": "webauthn",
                    "webauthn_response": json_dumps(webauthn_response),
                    "csrf_token": csrf_token,
                    "password": "",
                },
            )
            self.assertTrue(response.url.endswith("/web/login"))
            error = (
                html.fromstring(response.content)
                .xpath('//p[@class="alert alert-danger"]')[0]
                .text.strip()
            )
            self.assertEqual(
                error,
                "User verification is required but user was not verified during authentication",
            )

            webauthn_response["response"]["authenticatorData"] = (
                "SZYN5YgOjGh0NBcPZHZgW4_krrmihjLHmVzzuoMdl2MFAAAAFQ"
            )
            webauthn_response["response"]["signature"] = (
                "MEQCIAdcWwNtQVrklYo70p5eHjVdSkA4Pgk6hbCCT6O8-V0BAiBBVKgroyNNOqN5xwO6Rr4yJV61J1TGWoOyUsoUftjypw"
            )

            csrf_token = (
                html.fromstring(self.url_open("/web/login").content)
                .xpath('//input[@name="csrf_token"]')[0]
                .get("value")
            )
            self.url_open(
                "/auth/passkey/start-auth",
                "{}",
                headers={"Content-Type": "application/json"},
            )
            response = self.url_open(
                "/web/login",
                data={
                    "type": "webauthn",
                    "webauthn_response": json_dumps(webauthn_response),
                    "csrf_token": csrf_token,
                    "password": "",
                },
            )

            self.assertTrue(response.url.endswith("/odoo"))


@tagged("post_install", "-at_install")
class PasskeyTestTours(PasskeyTest):
    def test_passkey_login(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", self.passkeys["test-keepassxc"]["host"]
        )
        with self.patch_start_auth(
            self.passkeys["test-keepassxc"]["auth"]["challenge"]
        ):
            self.start_tour("/web/login?debug=tests", "passkeys_tour_login")

    def test_passkey_backend(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", self.passkeys["test-yubikey"]["host"]
        )
        self.admin_user.tz = "UTC"
        self.admin_user.auth_passkey_key_ids.unlink()
        with self.patch_start_registration(
            self.passkeys["test-yubikey"]["registration"]["challenge"]
        ):
            self.start_tour(
                "/odoo?debug=tests", "passkeys_tour_registration", login="admin"
            )
        with self.patch_start_auth(self.passkeys["test-yubikey"]["auth"]["challenge"]):
            self.start_tour("/odoo?debug=tests", "passkeys_tour_verify", login="admin")
        self.start_tour("/odoo?debug=tests", "passkeys_tour_delete", login="admin")
