import secrets
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from odoo.db import db_connect
from odoo.exceptions import AccessDenied
from odoo.http import _request_stack, dispatch_rpc
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_api_key, new_test_user
from odoo.tools import mute_logger


class _WebRequest:
    def __init__(self, address):
        self.httprequest = SimpleNamespace(remote_addr=address)
        self.cookies = {}
        self.after_release = []

    def call_after_release(self, func):
        self.after_release.append(func)

    def release(self):
        pending, self.after_release = self.after_release, []
        for func in pending:
            func()


@tagged("post_install", "-at_install")
class TestRpcLoginCooldown(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env["ir.config_parameter"].sudo()
        icp.set_param("base.login_cooldown_after", "3")
        icp.set_param("base.login_cooldown_duration", "60")
        icp.set_param("base.login_cooldown_account_after", "5")
        icp.set_param("base.rpc_api_key_only", "0")
        cls.user = new_test_user(
            cls.env,
            login="rpc_target",
            password="rpc-target-pw",
            groups="base.group_user",
        )
        cls.key = new_test_api_key(cls.user)

    def setUp(self):
        super().setUp()
        muted = mute_logger("odoo.addons.base.models.res_users")
        muted.__enter__()
        self.addCleanup(muted.__exit__)

    def _dispatch(self, service, method, params, address):
        _request_stack.push(
            SimpleNamespace(httprequest=SimpleNamespace(remote_addr=address))
        )
        try:
            return dispatch_rpc(service, method, params)
        finally:
            _request_stack.pop()

    def _call(self, secret, address, uid=None):
        return self._dispatch(
            "object",
            "execute_kw",
            [
                self.env.cr.dbname,
                uid or self.user.id,
                secret,
                "res.users",
                "context_get",
                [],
            ],
            address,
        )

    def _authenticate(self, login, secret, address):
        return self._dispatch(
            "common", "authenticate", [self.env.cr.dbname, login, secret, {}], address
        )

    def _web_login(self, login, password, address):
        request = _WebRequest(address)
        try:
            with patch("odoo.addons.base.models.res_users.request", request):
                return self.env["res.users"].authenticate(
                    {"login": login, "password": password, "type": "password"},
                    {"interactive": True},
                )
        finally:
            request.release()

    def _require_keys(self):
        self.env["ir.config_parameter"].sudo().set_param("base.rpc_api_key_only", "1")
        self.env.flush_all()

    def _refused(self, message=""):
        return self.assertRaisesRegex(AccessDenied, message)

    def _fail(self, address, uid=None):
        with self._refused():
            self._call("wrong-password", address, uid)

    @contextmanager
    def _claim_held_elsewhere(self, address):
        with db_connect(self.env.cr.dbname).cursor() as other:
            other.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                [f"login_cooldown:{address}"],
            )
            try:
                yield
            finally:
                other.rollback()

    def test_wrong_passwords_at_the_object_door_cool_the_address_down(self):
        for _ in range(3):
            self._fail("203.0.113.10")
        with self._refused("Too many login failures"):
            self._call("rpc-target-pw", "203.0.113.10")
        self.assertEqual(
            self._call("rpc-target-pw", "203.0.113.11")["uid"], self.user.id
        )

    def test_wrong_passwords_at_the_authenticate_door_cool_the_address_down(self):
        for _ in range(3):
            self.assertFalse(self._authenticate("rpc_target", "nope", "203.0.113.20"))
        self.assertFalse(
            self._authenticate("rpc_target", "rpc-target-pw", "203.0.113.20")
        )
        self.assertEqual(
            self._authenticate("rpc_target", "rpc-target-pw", "203.0.113.21"),
            self.user.id,
        )

    def test_an_uncached_attempt_is_refused_while_another_is_in_flight(self):
        with self._claim_held_elsewhere("203.0.113.30"):
            with self._refused("in progress"):
                self._call("rpc-target-pw", "203.0.113.30")
        self.assertEqual(
            self._call("rpc-target-pw", "203.0.113.30")["uid"], self.user.id
        )

    def test_a_cached_credential_takes_no_claim_and_is_still_cooled_down(self):
        self._call("rpc-target-pw", "203.0.113.40")
        with self._claim_held_elsewhere("203.0.113.41"):
            self.assertEqual(
                self._call("rpc-target-pw", "203.0.113.41")["uid"], self.user.id
            )
        for _ in range(3):
            self._fail("203.0.113.42")
        with self._refused("Too many login failures"):
            self._call("rpc-target-pw", "203.0.113.42")

    def test_guesses_spread_over_addresses_cool_the_account_down(self):
        for i in range(5):
            self._fail(f"198.51.100.{i}")
        with self._refused():
            self._call("rpc-target-pw", "198.51.100.99")
        with self._refused("Too many login failures"):
            self._web_login("rpc_target", "rpc-target-pw", "198.51.100.98")
        self.assertEqual(self._call(self.key, "198.51.100.97")["uid"], self.user.id)
        self.assertEqual(
            self._authenticate("rpc_target", self.key, "198.51.100.96"), self.user.id
        )

    def test_a_key_does_not_clear_what_password_guesses_counted(self):
        for i in range(4):
            self._fail(f"198.51.100.{10 + i}")
        self._call(self.key, "198.51.100.20")
        self._fail("198.51.100.21")
        with self._refused():
            self._call("rpc-target-pw", "198.51.100.22")

    def test_a_password_success_clears_the_account(self):
        for i in range(4):
            self._fail(f"198.51.100.{30 + i}")
        self._call("rpc-target-pw", "198.51.100.40")
        for i in range(4):
            self._fail(f"198.51.100.{50 + i}")
        self.assertEqual(
            self._call("rpc-target-pw", "198.51.100.60")["uid"], self.user.id
        )

    def test_an_unknown_login_cools_down_like_a_known_one(self):
        for i in range(5):
            with self._refused():
                self._web_login("nobody_by_that_name", "x", f"192.0.2.{i}")
            with self._refused():
                self._web_login("rpc_target", "x", f"192.0.2.{20 + i}")
        for login in ("nobody_by_that_name", "rpc_target"):
            with self._refused("Too many login failures"):
                self._web_login(login, "x", "192.0.2.99")

    def test_an_unknown_uid_is_refused_as_a_wrong_password_is(self):
        unknown = self.env["res.users"].search([], order="id desc", limit=1).id + 1000
        for _ in range(3):
            with self._refused():
                self._call("rpc-target-pw", "203.0.113.95", uid=unknown)
        with self._refused("Too many login failures"):
            self._call("rpc-target-pw", "203.0.113.95")

    def test_a_login_of_any_length_is_counted(self):
        login = secrets.token_hex(5000)
        for _ in range(3):
            with self._refused():
                self._web_login(login, "x", "203.0.113.90")
        with self._refused("Too many login failures"):
            self._web_login("rpc_target", "rpc-target-pw", "203.0.113.90")

    def test_a_password_is_refused_at_the_rpc_doors_when_keys_are_required(self):
        self._require_keys()
        with self._refused():
            self._call("rpc-target-pw", "203.0.113.50")
        self.assertFalse(
            self._authenticate("rpc_target", "rpc-target-pw", "203.0.113.50")
        )
        self.assertEqual(self._call(self.key, "203.0.113.51")["uid"], self.user.id)
        self.assertEqual(
            self._authenticate("rpc_target", self.key, "203.0.113.51"), self.user.id
        )
        self.assertEqual(
            self._web_login("rpc_target", "rpc-target-pw", "203.0.113.52")["uid"],
            self.user.id,
        )

    def test_a_cached_password_is_refused_once_keys_are_required(self):
        self._call("rpc-target-pw", "203.0.113.60")
        self._require_keys()
        with self._refused():
            self._call("rpc-target-pw", "203.0.113.60")

    def _failures(self, source):
        cooldown = self.env["res.users"]._login_cooldown()
        return cooldown.states(self.env.cr, [source])[source][0]

    def test_wrong_keys_count_toward_the_address_and_the_account(self):
        self._require_keys()
        for i in range(5):
            self._fail(f"203.0.113.{70 + i}")
        self.assertEqual(self._failures("203.0.113.70"), 1)
        self.assertEqual(self._failures(f"account:{self.user.id}"), 5)
        with self._refused("Too many login failures"):
            self._web_login("rpc_target", "rpc-target-pw", "203.0.113.80")

    def test_a_valid_key_enters_from_a_cooled_address(self):
        for _ in range(3):
            self._fail("203.0.113.100")
        with self._refused("Too many login failures"):
            self._call("rpc-target-pw", "203.0.113.100")
        self.assertFalse(
            self._authenticate("rpc_target", "rpc-target-pw", "203.0.113.100")
        )
        self.assertEqual(self._call(self.key, "203.0.113.100")["uid"], self.user.id)
        self.assertEqual(
            self._authenticate("rpc_target", self.key, "203.0.113.100"), self.user.id
        )
        with self._refused("Too many login failures"):
            self._web_login("rpc_target", "rpc-target-pw", "203.0.113.100")

    def test_a_wrong_key_from_a_cooled_address_is_refused_and_counted(self):
        for _ in range(3):
            self._fail("203.0.113.110")
        with self._refused("Too many login failures"):
            self._call("0" * 40, "203.0.113.110")
        self.assertFalse(self._authenticate("rpc_target", "0" * 40, "203.0.113.110"))
        self.assertEqual(self._failures("203.0.113.110"), 5)
        self.assertEqual(self._failures(f"account:{self.user.id}"), 5)

    def test_a_key_clears_no_address_count(self):
        for _ in range(2):
            self._fail("203.0.113.120")
        self._call(self.key, "203.0.113.120")
        self.assertEqual(self._failures("203.0.113.120"), 2)
        self._fail("203.0.113.120")
        with self._refused("Too many login failures"):
            self._call("rpc-target-pw", "203.0.113.120")

    def test_a_login_without_an_account_meets_its_auth_methods_inside_the_gate(self):
        asked = []

        def login_unknown(_users, credential, _user_agent_env):
            asked.append(credential["login"])
            raise AccessDenied

        self.patch(type(self.env["res.users"]), "_login_unknown", login_unknown)
        for _ in range(4):
            self.assertFalse(
                self._authenticate("nobody_here", "guess", "203.0.113.130")
            )
        self.assertEqual(len(asked), 3, "not from a cooled address")
        self._require_keys()
        self.assertFalse(self._authenticate("nobody_here", "guess", "203.0.113.131"))
        self.assertEqual(len(asked), 3, "not at a door taking keys alone")
        with self._refused():
            self._web_login("nobody_else", "guess", "203.0.113.132")
        self.assertEqual(asked[3:], ["nobody_else"], "interactive, it is asked")


@tagged("post_install", "-at_install")
class TestRpcKeysOnlyDefault(TransactionCase):
    def test_a_new_database_takes_keys_only_at_the_rpc_doors(self):
        self.assertTrue(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param_bool("base.rpc_api_key_only")
        )
        self.assertTrue(self.env.ref("base.user_admin")._is_rpc_api_key_only())
