import base64
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import new_unbound_test_api_key

from odoo.addons.device.tests.common import DeviceHttpCase

PASSWORD = "dav-probe-password"
HOME = "/dav/addressbooks/"


def dav_key(user):
    return user.env(user=user)["res.users.apikeys"]._generate(
        "dav", "DAV probe", datetime.now() + timedelta(days=1)
    )


@tagged("post_install", "-at_install")
class TestDavAuthentication(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {
                "name": "DAV Auth Config",
                "dav_enabled": True,
                "dav_addressbook_enabled": True,
            }
        )
        cls.sync_user = cls.env["res.users"].create(
            {
                "name": "Phone Owner",
                "login": "dav-phone@example.com",
                "password": PASSWORD,
            }
        )
        cls.outsider = cls.env["res.users"].create(
            {
                "name": "Accounts Payable",
                "login": "dav-outsider@example.com",
                "password": PASSWORD,
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "DAVx5 Phone",
                "identifier": "DAV-AUTH-1",
                "config_id": cls.config.id,
                "comm_protocol": "https",
                "device_category_id": cls.env.ref(
                    "device_dav_sync.device_category_dav_client"
                ).id,
                "dav_sync_enabled": True,
                "dav_addressbook_enabled": True,
                "dav_user_id": cls.sync_user.id,
            }
        )
        cls.sync_key = dav_key(cls.sync_user)
        cls.outsider_key = dav_key(cls.outsider)

    def _propfind(self, header):
        headers = {"Depth": "0"}
        if header:
            headers["Authorization"] = header
        return self.url_open(HOME, method="PROPFIND", headers=headers)

    def _refusals(self):
        return self.env["integration.exchange"].search(
            [
                ("state", "=", "refused"),
                (
                    "refusal_reason",
                    "in",
                    ("authentication_failed", "endpoint_not_found"),
                ),
                "|",
                ("channel_id", "like", "device.device,%"),
                ("channel_name", "like", "device.device:%"),
            ]
        )

    def _basic(self, login, password=None):
        if password is None:
            password = (
                self.sync_key if login == self.sync_user.login else self.outsider_key
            )
        raw = base64.b64encode(f"{login}:{password}".encode()).decode()
        return f"Basic {raw}"

    def _assert_challenged(self, response):
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.headers.get("WWW-Authenticate"), 'Basic realm="Odoo DAV"'
        )

    def test_basic_auth_works_for_a_user_with_a_dav_device(self):
        response = self._propfind(self._basic(self.sync_user.login))
        self.assertEqual(response.status_code, 207)
        self.assertIn(self.sync_user.login, response.text)

    def test_basic_auth_refuses_a_user_with_no_dav_device(self):
        self._assert_challenged(self._propfind(self._basic(self.outsider.login)))

    def test_basic_auth_refuses_once_the_device_is_disabled(self):
        self.device.dav_sync_enabled = False
        self._assert_challenged(self._propfind(self._basic(self.sync_user.login)))

    def test_basic_auth_refuses_once_the_device_is_archived(self):
        self.device.active = False
        self._assert_challenged(self._propfind(self._basic(self.sync_user.login)))

    def test_a_wrong_password_is_still_refused(self):
        self._assert_challenged(
            self._propfind(self._basic(self.sync_user.login, "wrong"))
        )

    def test_the_login_password_is_never_a_dav_password(self):
        self._assert_challenged(
            self._propfind(self._basic(self.sync_user.login, PASSWORD))
        )

    def test_a_key_bound_to_another_door_is_refused(self):
        rpc_key = self.sync_user.env(user=self.sync_user)[
            "res.users.apikeys"
        ]._generate("rpc", "RPC", datetime.now() + timedelta(days=1))
        self._assert_challenged(
            self._propfind(self._basic(self.sync_user.login, rpc_key))
        )

    def test_a_key_bound_to_no_door_is_refused(self):
        unbound = new_unbound_test_api_key(self.sync_user)
        self._assert_challenged(
            self._propfind(self._basic(self.sync_user.login, unbound))
        )

    def test_the_device_mints_the_password_for_its_own_user_only(self):
        from odoo.exceptions import UserError

        action = self.device.with_user(self.sync_user).action_generate_dav_password()
        self.assertEqual(action["res_model"], "wizard.res.users.apikeys.create")
        self.assertEqual(
            action["context"]["default_scope_id"],
            self.env.ref("device_dav_sync.apikeys_scope_dav").id,
        )
        with self.assertRaises(UserError):
            self.device.with_user(self.outsider).action_generate_dav_password()

    def test_the_bearer_scheme_still_authenticates_its_device(self):
        token = self.device.credential_id.sudo().credential_value
        response = self._propfind(f"Bearer {token}")
        self.assertEqual(response.status_code, 207)

    def test_no_header_is_challenged(self):
        self._assert_challenged(self._propfind(None))

    def test_an_unknown_login_and_a_wrong_password_answer_alike(self):
        unknown = self._propfind(self._basic("nobody@example.com"))
        wrong = self._propfind(self._basic(self.sync_user.login, "wrong"))
        self.assertEqual(
            (
                unknown.status_code,
                unknown.text,
                dict(unknown.headers).get("WWW-Authenticate"),
            ),
            (
                wrong.status_code,
                wrong.text,
                dict(wrong.headers).get("WWW-Authenticate"),
            ),
            "the answer must not say whether the login exists",
        )

    def test_a_refused_password_is_recorded_without_the_password(self):
        headers = {"Authorization": self._basic(self.sync_user.login, "Guess-7731")}
        mocked = MagicMock()
        mocked.httprequest.headers = headers
        with patch("odoo.addons.device_dav_sync.models.device_device.request", mocked):
            resolution = self.env["device.device"]._receiver_for_dav()
        self.assertEqual(resolution.subject, self.device)

        allowed, status, reason = self.device.with_context(
            inbound_verify=resolution.verify
        )._check_inbound_request(headers, body=b"", remote_addr="203.0.113.40")

        self.assertFalse(allowed)
        self.assertEqual(status, 401)
        refusal = self._refusals()
        self.assertEqual(len(refusal), 1)
        self.assertEqual(refusal.channel_id, self.device)
        self.assertEqual(refusal.source_ip, "203.0.113.40")
        self.assertNotIn(
            "Guess-7731", f"{refusal.channel_name} {refusal.error_message} {reason}"
        )

    def test_a_guessing_caller_fills_one_row_not_the_table(self):
        for attempt in range(5):
            self._propfind(self._basic(f"guess{attempt}", "nope"))

        refusal = self._refusals()
        self.assertEqual(len(refusal), 1)
        self.assertEqual(refusal.attempt_count, 5)
        self.assertIn("basic login guess", refusal.channel_name)

    def test_an_unknown_bearer_token_is_recorded_by_fingerprint(self):
        self._propfind("Bearer not-a-device-token")

        refusal = self._refusals()
        self.assertTrue(
            refusal.channel_name.startswith("device.device: bearer sha256:")
        )
        self.assertNotIn(
            "not-a-device-token", f"{refusal.channel_name} {refusal.error_message}"
        )

    def test_a_client_asking_for_the_challenge_is_not_recorded(self):
        self._propfind(None)
        self._propfind(self._basic(self.sync_user.login))

        self.assertFalse(self._refusals())
