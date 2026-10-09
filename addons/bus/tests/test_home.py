from unittest.mock import MagicMock, patch

from odoo.tests import BaseCase, TransactionCase, tagged

from ..controllers.home import _admin_password_warn, _is_private_address


@tagged("-at_install", "post_install")
class TestAdminPasswordWarnAddress(BaseCase):
    def test_private_addresses_are_recognised(self):
        for address in (
            "127.0.0.1",
            "10.1.2.3",
            "192.168.0.7",
            "::1",
            "fd00::1",
            "100.64.1.1",
        ):
            with self.subTest(address=address):
                self.assertTrue(_is_private_address(address))

    def test_public_addresses_are_recognised(self):
        for address in (
            "8.8.8.8",
            "1.1.1.1",
            "2001:4860:4860::8888",
            "2002:a00:1::",
            "192.0.2.1",
        ):
            with self.subTest(address=address):
                self.assertFalse(_is_private_address(address))

    def test_unparsable_addresses_do_not_raise(self):
        for address in (None, "", "unknown", "127.0.0.1, 10.0.0.1", "_hidden", "abc"):
            with self.subTest(address=address):
                self.assertFalse(_is_private_address(address))


@tagged("-at_install", "post_install")
class TestAdminPasswordWarnLanguage(TransactionCase):
    def test_the_warning_speaks_the_admin_language(self):
        self.env["ir.module.module"].search([("demo", "=", True)]).demo = False
        self.env["res.lang"]._activate_lang("es_ES")
        admin = self.env.ref("base.user_admin")
        admin.lang = "es_ES"
        request = MagicMock()
        request.params = {"password": "admin"}
        request.httprequest.remote_addr = "8.8.8.8"
        request.env = self.env(context=dict(self.env.context, lang="en_US"))
        sent = []
        with (
            patch("odoo.addons.bus.controllers.home.request", request),
            patch.object(
                type(self.env["res.partner"]),
                "_bus_send",
                lambda _partner, _type, payload: sent.append(payload),
            ),
        ):
            _admin_password_warn(admin.id)
        self.assertEqual(len(sent), 1)
        self.assertTrue(sent[0]["message"].startswith("Está usando la contraseña"))
