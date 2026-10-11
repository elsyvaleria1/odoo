from types import SimpleNamespace
from unittest.mock import patch

from odoo import api
from odoo.exceptions import AccessDenied
from odoo.http import _request_stack, dispatch_rpc
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
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
class TestLdapLoginGate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env["ir.config_parameter"].sudo()
        icp.set_param("base.login_cooldown_after", "3")
        icp.set_param("base.login_cooldown_duration", "60")
        icp.set_param("base.login_cooldown_account_after", "5")
        icp.set_param("base.rpc_api_key_only", "0")
        cls.known = new_test_user(cls.env, login="ldap_known", password="unused")
        cls.env.cr.execute(
            "UPDATE res_users SET password = NULL WHERE id = %s", [cls.known.id]
        )
        cls.env.invalidate_all()

    def setUp(self):
        super().setUp()
        self.directory = {"ldap_known": "known-pw", "ldap_newcomer": "newcomer-pw"}
        self.binds = []
        Ldap = type(self.env["res.company.ldap"])
        company = self.env.company
        conf = {
            "id": 0,
            "company": (company.id, company.name),
            "create_user": True,
            "user": False,
        }

        def authenticate(_ldap, _conf, login, password):
            self.binds.append(login)
            if self.directory.get(login.lower().strip()) != password:
                return False
            return f"cn={login}", {"cn": [login]}

        self.patch(Ldap, "_get_ldap_dicts", lambda _ldap: [conf])
        self.patch(Ldap, "_authenticate", authenticate)
        muted = mute_logger("odoo.addons.base.models.res_users")
        muted.__enter__()
        self.addCleanup(muted.__exit__)

    def _web_login(self, login, password, address):
        request = _WebRequest(address)
        try:
            with patch("odoo.addons.base.models.res_users.request", request):
                return api.Environment(self.env.cr, None, {})["res.users"].authenticate(
                    {"login": login, "password": password, "type": "password"},
                    {"interactive": True},
                )["uid"]
        except AccessDenied as refused:
            return refused.args[0]
        finally:
            request.release()

    def _rpc_authenticate(self, login, password, address):
        _request_stack.push(
            SimpleNamespace(httprequest=SimpleNamespace(remote_addr=address))
        )
        try:
            return dispatch_rpc(
                "common", "authenticate", [self.env.cr.dbname, login, password, {}]
            )
        finally:
            _request_stack.pop()

    def _accounts(self, login):
        return (
            self.env["res.users"]
            .with_context(active_test=False)
            .search_count([("login", "=", login)])
        )

    def test_a_new_login_is_held_to_the_address_cooldown(self):
        replies = [
            self._web_login("ldap_newcomer", "guess", "198.51.100.1") for _ in range(12)
        ]
        self.assertEqual(replies[:3], ["Access Denied"] * 3)
        self.assertTrue(all("Too many login failures" in r for r in replies[3:]))
        self.assertEqual(len(self.binds), 3, "a refused attempt never reaches LDAP")
        self.assertIn(
            "Too many login failures",
            self._web_login("ldap_newcomer", "newcomer-pw", "198.51.100.1"),
        )
        self.assertEqual(len(self.binds), 3)
        self.assertEqual(self._accounts("ldap_newcomer"), 0)

    def test_a_new_login_cools_down_as_an_account_does(self):
        for i in range(5):
            self.assertEqual(
                self._web_login("ldap_newcomer", "guess", f"198.51.100.{10 + i}"),
                "Access Denied",
            )
        self.assertIn(
            "Too many login failures",
            self._web_login("ldap_newcomer", "newcomer-pw", "198.51.100.20"),
        )
        self.assertEqual(len(self.binds), 5)

    def test_a_new_login_signs_in_and_gets_its_account(self):
        uid = self._web_login("LDAP_Newcomer", "newcomer-pw", "198.51.100.30")
        self.assertEqual(self.env["res.users"].browse(uid).login, "ldap_newcomer")
        self.assertEqual(
            self._web_login("ldap_newcomer", "newcomer-pw", "198.51.100.31"), uid
        )

    def test_a_key_only_rpc_door_never_asks_ldap(self):
        self.env["ir.config_parameter"].sudo().set_param("base.rpc_api_key_only", "1")
        self.env.flush_all()
        self.assertFalse(
            self._rpc_authenticate("ldap_newcomer", "newcomer-pw", "198.51.100.40")
        )
        self.assertFalse(
            self._rpc_authenticate("ldap_known", "known-pw", "198.51.100.41")
        )
        self.assertEqual(self.binds, [])
        self.assertEqual(self._accounts("ldap_newcomer"), 0)

    def test_a_cooled_address_at_rpc_never_asks_ldap(self):
        for _ in range(3):
            self.assertFalse(
                self._rpc_authenticate("ldap_newcomer", "guess", "198.51.100.50")
            )
        self.assertFalse(
            self._rpc_authenticate("ldap_newcomer", "newcomer-pw", "198.51.100.50")
        )
        self.assertEqual(len(self.binds), 3)
        uid = self._rpc_authenticate("ldap_newcomer", "newcomer-pw", "198.51.100.51")
        self.assertTrue(uid)
        self.assertEqual(self.env["res.users"].browse(uid).login, "ldap_newcomer")

    def test_another_spelling_of_an_account_is_that_account(self):
        self.assertEqual(
            self._web_login("LDAP_Known", "known-pw", "198.51.100.60"), self.known.id
        )
        for i in range(5):
            self.assertEqual(
                self._web_login("ldap_known", "guess", f"198.51.100.{61 + i}"),
                "Access Denied",
            )
        for i, spelling in enumerate(("LDAP_Known", " ldap_known", "ldap_known ")):
            self.assertIn(
                "Too many login failures",
                self._web_login(spelling, "known-pw", f"198.51.100.{70 + i}"),
                f"{spelling!r} guesses at the locked account",
            )
        self.assertEqual(self._accounts("ldap_known"), 1)

    def test_an_archived_account_is_not_recreated_from_the_directory(self):
        self.known.active = False
        self.assertEqual(
            self._web_login("ldap_known", "known-pw", "198.51.100.80"), "Access Denied"
        )
        self.assertEqual(self.binds, [])
        self.assertEqual(self._accounts("ldap_known"), 1)
