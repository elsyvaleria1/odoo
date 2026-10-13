import grp
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from odoo.tests import HttpCase, TransactionCase, mute_logger, new_test_user, tagged

from odoo.addons.auth_unix_peer import unix_peer

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDS551vG6smpVl4K4LAyFYU2PT1T582x4sfk9RM5P0qs"


class UnixPeerFiles:
    """Keys files owned by the test process, trusted in place of root."""

    def setUp(self):
        super().setUp()
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(unix_peer, "TRUSTED_OWNER", os.getuid()))

    def write_keys(self, name, content, mode=0o644):
        path = Path(self.tmp, name)
        path.write_text(content, encoding="utf-8")
        path.chmod(mode)
        return str(path)


@tagged("post_install", "-at_install")
class TestLoginFromKeys(UnixPeerFiles, TransactionCase):
    def test_shared_comment_names_the_login(self):
        path = self.write_keys(
            "keys",
            f"# admins\n\n{KEY} eli@example.com\n"
            f'from="127.0.0.1" {KEY} eli@example.com\n',
        )
        self.assertEqual(unix_peer.login_from_keys(path), "eli@example.com")

    def test_different_comments_name_nobody(self):
        path = self.write_keys(
            "keys", f"{KEY} eli@example.com\n{KEY} luis@example.com\n"
        )
        self.assertIsNone(unix_peer.login_from_keys(path))

    def test_key_without_comment_names_nobody(self):
        path = self.write_keys("keys", f"{KEY} eli@example.com\n{KEY}\n")
        self.assertIsNone(unix_peer.login_from_keys(path))

    def test_file_others_can_write_names_nobody(self):
        path = self.write_keys("keys", f"{KEY} eli@example.com\n", mode=0o664)
        self.assertIsNone(unix_peer.login_from_keys(path))

    def test_untrusted_owner_names_nobody(self):
        path = self.write_keys("keys", f"{KEY} eli@example.com\n")
        with patch.object(unix_peer, "TRUSTED_OWNER", os.getuid() + 1):
            self.assertIsNone(unix_peer.login_from_keys(path))

    def test_missing_file_names_nobody(self):
        self.assertIsNone(unix_peer.login_from_keys(str(Path(self.tmp, "none"))))

    def test_loopback_addresses(self):
        self.assertTrue(unix_peer.is_loopback("127.0.0.1"))
        self.assertTrue(unix_peer.is_loopback("::1"))
        self.assertTrue(unix_peer.is_loopback("::ffff:127.0.0.1"))
        self.assertFalse(unix_peer.is_loopback("51.79.101.111"))
        self.assertFalse(unix_peer.is_loopback("<local>"))


@tagged("post_install", "-at_install")
class TestUnixPeerAuth(UnixPeerFiles, HttpCase):
    """The test server and this test run as the same Unix user, so a call from here
    is a real loopback call the kernel attributes to that user."""

    def setUp(self):
        super().setUp()
        self.me = new_test_user(
            self.env,
            "unix.peer@example.com",
            groups="base.group_user,base.group_partner_manager",
        )
        self.unix_name = unix_peer.member_name(os.getuid(), self.my_group())
        self.write_keys(self.unix_name, f"{KEY} unix.peer@example.com\n")
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("auth_unix_peer.group", self.my_group())
        params.set_param("auth_unix_peer.keys_path", str(Path(self.tmp, "%u")))
        self.enterContext(
            mute_logger("odoo.http", "odoo.addons.auth_unix_peer.models.ir_http")
        )

    @staticmethod
    def my_group():
        return grp.getgrgid(os.getgid()).gr_name

    def call(self, headers=None):
        return self.url_open(
            "/json/2/res.partner/create",
            json={"vals_list": [{"name": "Unix peer call"}]},
            headers=headers or {},
        )

    def test_bare_local_call_runs_as_the_keys_owner(self):
        response = self.call()
        self.assertEqual(response.status_code, 200, response.text)
        partner = self.env["res.partner"].browse(response.json())
        self.assertEqual(partner.create_uid, self.me)

    def test_without_group_parameter_nobody_is_recognised(self):
        self.env["ir.config_parameter"].sudo().set_param("auth_unix_peer.group", False)
        self.assertEqual(self.call().status_code, 401)

    def test_unix_user_outside_the_group_is_not_recognised(self):
        others = next(
            (
                g.gr_name
                for g in grp.getgrall()
                if g.gr_gid != os.getgid() and self.unix_name not in g.gr_mem
            ),
            None,
        )
        self.env["ir.config_parameter"].sudo().set_param("auth_unix_peer.group", others)
        self.assertEqual(self.call().status_code, 401)

    def test_login_that_is_no_user_is_refused(self):
        self.write_keys(self.unix_name, f"{KEY} nobody@example.com\n")
        self.assertEqual(self.call().status_code, 401)

    def test_archived_user_is_refused(self):
        self.me.active = False
        self.assertEqual(self.call().status_code, 401)

    def test_portal_user_is_refused(self):
        new_test_user(self.env, "portal.peer@example.com", groups="base.group_portal")
        self.write_keys(self.unix_name, f"{KEY} portal.peer@example.com\n")
        self.assertEqual(self.call().status_code, 401)

    def test_api_key_still_decides_when_given(self):
        response = self.call({"Authorization": "Bearer not-a-key"})
        self.assertEqual(response.status_code, 401)
