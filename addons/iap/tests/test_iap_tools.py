from odoo.tests import TransactionCase, tagged

from odoo.addons.iap.tools.iap_tools import iap_get_endpoint


@tagged("post_install", "-at_install")
class TestIapEndpoint(TransactionCase):
    def test_endpoint_param_overrides_default(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "iap.endpoint", "https://iap.test.example.com"
        )
        self.assertEqual(iap_get_endpoint(self.env), "https://iap.test.example.com")
