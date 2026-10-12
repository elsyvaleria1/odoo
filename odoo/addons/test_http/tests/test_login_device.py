import time

import requests

import odoo.http
from odoo.libs.json import dumps as json_dumps
from odoo.tests import get_db_name, tagged
from odoo.tests.common import Opener, new_test_user
from odoo.tools import mute_logger

from .test_common import TestHttpBase
from odoo.addons.test_http.controllers import CT_JSON

LOGIN_DEVICE_COOKIE = "login_device"
PASSWORD = "device-victim-pw"
DEVICE_BUDGET = 5


class _FromAddress(requests.adapters.HTTPAdapter):
    def __init__(self, address):
        self.address = address
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        kwargs["source_address"] = (self.address, 0)
        super().init_poolmanager(*args, **kwargs)


@tagged("post_install", "-at_install")
class TestLoginDevice(TestHttpBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env["ir.config_parameter"].sudo()
        icp.set_param("base.login_cooldown_after", "3")
        icp.set_param("base.login_cooldown_duration", "60")
        icp.set_param("base.login_cooldown_account_after", "5")
        cls.victim = new_test_user(cls.env, login="device_victim", password=PASSWORD)
        cls.mallory = new_test_user(
            cls.env, login="device_mallory", password="device-mallory-pw"
        )

    def setUp(self):
        super().setUp()
        muted = mute_logger("odoo.addons.base.models.res_users", "odoo.http")
        muted.__enter__()
        self.addCleanup(muted.__exit__)

    def _client(self, address):
        client = Opener(self)
        self.addCleanup(client.close)
        return self._at(client, address)

    def _at(self, client, address):
        previous = client.adapters.get("http://")
        client.mount("http://", _FromAddress(address))
        if previous is not None:
            previous.close()
        return client

    def _login(self, client, login, password):
        self.opener = client
        payload = {
            "jsonrpc": "2.0",
            "id": None,
            "method": "call",
            "params": {"db": get_db_name(), "login": login, "password": password},
        }
        response = self.db_url_open(
            "/web/session/authenticate", data=json_dumps(payload), headers=CT_JSON
        )
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            return body["error"]["data"]["message"]
        return body["result"]["uid"]

    def _logout(self, client):
        self.opener = client
        self.db_url_open("/web/session/logout").raise_for_status()

    def _victim_device(self, address="127.0.0.9"):
        device = self._client(address)
        self.assertEqual(self._login(device, "device_victim", PASSWORD), self.victim.id)
        self._logout(device)
        return device

    def _lock_victim(self):
        attacker = self._client("127.0.0.2")
        for _ in range(3):
            self.assertEqual(
                self._login(attacker, "device_victim", "guess"), "Access Denied"
            )
        self._at(attacker, "127.0.0.3")
        for _ in range(2):
            self.assertEqual(
                self._login(attacker, "device_victim", "guess"), "Access Denied"
            )
        self.assertIn(
            "Too many login failures",
            self._login(self._client("127.0.0.5"), "device_victim", PASSWORD),
            "the account is locked to a client without the device",
        )
        return attacker

    def _failures(self, source):
        self.env.cr.execute(
            "SELECT failures FROM res_users_login_cooldown WHERE source = %s",
            [source],
        )
        row = self.env.cr.fetchone()
        return row[0] if row else 0

    def test_a_locked_account_still_admits_the_device_that_signed_in(self):
        device = self._victim_device()
        attacker = self._lock_victim()
        self.assertEqual(self._login(device, "device_victim", PASSWORD), self.victim.id)
        self._logout(device)

        self.env.cr.execute(
            "UPDATE res_users_login_cooldown"
            " SET last_failure = last_failure - interval '61 seconds'"
            " WHERE source = %s",
            [f"account:{self.victim.id}"],
        )
        self._at(attacker, "127.0.0.4")
        self.assertEqual(
            self._login(attacker, "device_victim", "guess"), "Access Denied"
        )
        self.assertIn(
            "Too many login failures",
            self._login(self._client("127.0.0.6"), "device_victim", PASSWORD),
        )
        self.assertEqual(self._login(device, "device_victim", PASSWORD), self.victim.id)

    def _spend_the_device_budget(self, device, first_address):
        for i in range(DEVICE_BUDGET):
            self._at(device, f"127.0.0.{first_address + i}")
            self.assertEqual(
                self._login(device, "device_victim", "guess"), "Access Denied"
            )
        self.assertEqual(
            self._failures(f"account:{self.victim.id}"),
            0,
            "the device's failures do not count toward the account",
        )

    def _set_account_threshold(self, threshold):
        self.env["ir.config_parameter"].sudo().set_param(
            "base.login_cooldown_account_after", str(threshold)
        )

    def test_a_stolen_marker_adds_its_small_budget_to_the_accounts_once(self):
        self._set_account_threshold(30)
        device = self._victim_device()
        evaluated = 0
        for i in range(30):
            reply = self._login(
                self._client(f"127.0.1.{1 + i // 3}"), "device_victim", "guess"
            )
            self.assertEqual(reply, "Access Denied")
            evaluated += 1
        self.assertIn(
            "Too many login failures",
            self._login(self._client("127.0.1.20"), "device_victim", PASSWORD),
        )
        for i in range(10):
            self._at(device, f"127.0.1.{30 + i}")
            reply = self._login(device, "device_victim", "guess")
            if reply != "Access Denied":
                self.assertIn("Too many login failures", reply)
                break
            evaluated += 1
        self.assertEqual(
            evaluated,
            30 + DEVICE_BUDGET,
            "in one lockout window, a stolen marker evaluates the account's "
            "threshold plus the device budget, and no more",
        )
        self._at(device, "127.0.1.50")
        self.assertIn(
            "Too many login failures",
            self._login(device, "device_victim", PASSWORD),
            "the spent marker no longer exempts its holder",
        )

    def test_a_spent_device_counts_toward_the_account(self):
        device = self._victim_device()
        stolen = self._client("127.0.0.40")
        stolen.cookies.set(LOGIN_DEVICE_COOKIE, device.cookies.get(LOGIN_DEVICE_COOKIE))
        self._set_account_threshold(30)
        self._spend_the_device_budget(device, 20)
        self._at(device, "127.0.0.26")
        self.assertEqual(self._login(device, "device_victim", "guess"), "Access Denied")
        self.assertEqual(
            self._failures(f"account:{self.victim.id}"),
            1,
            "past its budget, the device's failure counts toward the account",
        )
        self._set_account_threshold(6)
        self._lock_victim()
        self._at(device, "127.0.0.27")
        self.assertIn(
            "Too many login failures", self._login(device, "device_victim", PASSWORD)
        )
        self.assertIn(
            "Too many login failures", self._login(stolen, "device_victim", PASSWORD)
        )

    def test_the_devices_own_success_forgives_none_of_its_failures(self):
        device = self._victim_device()
        stolen = self._client("127.0.0.42")
        stolen.cookies.set(LOGIN_DEVICE_COOKIE, device.cookies.get(LOGIN_DEVICE_COOKIE))
        self._set_account_threshold(30)
        for i in range(DEVICE_BUDGET - 1):
            self._at(stolen, f"127.0.0.{50 + i}")
            self.assertEqual(
                self._login(stolen, "device_victim", "guess"), "Access Denied"
            )
        self._at(device, "127.0.0.55")
        self.assertEqual(self._login(device, "device_victim", PASSWORD), self.victim.id)
        self._logout(device)
        for address in ("127.0.0.56", "127.0.0.57"):
            self._at(stolen, address)
            self.assertEqual(
                self._login(stolen, "device_victim", "guess"), "Access Denied"
            )
        self.assertEqual(
            self._failures(f"account:{self.victim.id}"),
            1,
            "the victim's sign-in left the thief one failure of the budget",
        )

    def test_a_spent_device_is_trusted_again_once_it_signs_in(self):
        device = self._victim_device()
        spent = device.cookies.get(LOGIN_DEVICE_COOKIE)
        self._spend_the_device_budget(device, 20)
        self._at(device, "127.0.0.26")
        self.assertEqual(self._login(device, "device_victim", PASSWORD), self.victim.id)
        self._logout(device)
        self.assertNotEqual(
            device.cookies.get(LOGIN_DEVICE_COOKIE),
            spent,
            "the device signs in as an ordinary browser and gets a new marker",
        )
        stolen = self._client("127.0.0.41")
        stolen.cookies.set(LOGIN_DEVICE_COOKIE, spent)
        self._lock_victim()
        self.assertIn(
            "Too many login failures", self._login(stolen, "device_victim", PASSWORD)
        )
        self._at(device, "127.0.0.28")
        self.assertEqual(self._login(device, "device_victim", PASSWORD), self.victim.id)

    def test_a_device_idle_past_the_retention_is_retired(self):
        device = self._victim_device()
        idle = self._victim_device("127.0.0.12")
        clients = self.env["auth.user.client"].with_context(active_test=False)
        self.env.flush_all()
        for client, days in ((device, 89), (idle, 91)):
            self.env.cr.execute(
                "UPDATE auth_user_client SET last_activity = now() - %s * interval '1 day'"
                " WHERE user_id = %s AND id = %s",
                [days, self.victim.id, self._device_id(client)],
            )
        clients.invalidate_model()
        self._lock_victim()
        self.assertIn(
            "Too many login failures",
            self._login(idle, "device_victim", PASSWORD),
            "idle longer than base.device_retention_days, the cleanup not run",
        )
        self.assertEqual(self._login(device, "device_victim", PASSWORD), self.victim.id)
        self._logout(device)

        self.env["ir.config_parameter"].sudo().set_param(
            "base.device_retention_days", "0"
        )
        self._at(idle, "127.0.0.13")
        self.assertEqual(
            self._login(idle, "device_victim", PASSWORD),
            self.victim.id,
            "no retention, no idle limit",
        )

    def _device_id(self, client):
        marker = client.cookies.get(LOGIN_DEVICE_COOKIE)
        return int(marker.split("_")[0].split(".")[1])

    def _revoke_all_devices(self, client):
        session = odoo.http.root.session_store.get(client.cookies.get("session_id"))
        session["identity-check-last"] = time.time()
        odoo.http.root.session_store.save(session)
        self.opener = client
        response = self.url_open(
            "/web/dataset/call_kw/res.users/action_revoke_all_devices",
            data=json_dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {
                        "model": "res.users",
                        "method": "action_revoke_all_devices",
                        "args": [self.victim.ids],
                        "kwargs": {},
                    },
                }
            ),
            headers=CT_JSON,
        ).json()
        self.assertEqual(response.get("result", {}).get("tag"), "reload", response)

    def test_log_out_from_all_devices_retires_every_marker(self):
        current = self._client("127.0.0.9")
        self.assertEqual(
            self._login(current, "device_victim", PASSWORD), self.victim.id
        )
        other = self._client("127.0.0.10")
        self.assertEqual(self._login(other, "device_victim", PASSWORD), self.victim.id)
        retired = current.cookies.get(LOGIN_DEVICE_COOKIE)
        stolen = self._client("127.0.0.11")
        stolen.cookies.set(LOGIN_DEVICE_COOKIE, retired)

        self._revoke_all_devices(current)
        rekeyed = current.cookies.get(LOGIN_DEVICE_COOKIE)
        self.assertTrue(rekeyed)
        self.assertNotEqual(rekeyed, retired, "this browser gets a fresh marker")
        self._logout(current)
        self._lock_victim()
        self.assertIn(
            "Too many login failures", self._login(other, "device_victim", PASSWORD)
        )
        self.assertIn(
            "Too many login failures",
            self._login(stolen, "device_victim", PASSWORD),
            "a stolen copy of this browser's marker is retired too",
        )
        self.assertEqual(
            self._login(current, "device_victim", PASSWORD), self.victim.id
        )

    def test_a_device_cookie_opens_its_own_account_alone(self):
        own = self._client("127.0.0.30")
        self.assertEqual(
            self._login(own, "device_mallory", "device-mallory-pw"), self.mallory.id
        )
        own_marker = own.cookies.get(LOGIN_DEVICE_COOKIE)
        self._lock_victim()
        self.assertIn(
            "Too many login failures", self._login(own, "device_victim", PASSWORD)
        )
        _uid, _sep, rest = own_marker.partition(".")
        forged = self._client("127.0.0.31")
        forged.cookies.set(LOGIN_DEVICE_COOKIE, f"{self.victim.id}.{rest}")
        self.assertIn(
            "Too many login failures", self._login(forged, "device_victim", PASSWORD)
        )

    def test_a_password_change_retires_every_device(self):
        device = self._victim_device()
        self._lock_victim()
        self.victim.password = "device-victim-pw-2"
        self.assertIn(
            "Too many login failures",
            self._login(device, "device_victim", "device-victim-pw-2"),
        )

    def test_a_revoked_device_is_retired(self):
        device = self._victim_device()
        self.env["auth.user.client"].with_context(active_test=False).search(
            [("user_id", "=", self.victim.id)]
        )._revoke()
        self._lock_victim()
        self.assertIn(
            "Too many login failures", self._login(device, "device_victim", PASSWORD)
        )
