from odoo.tests.common import HttpCase, tagged

from odoo.addons.web.tests.test_csp import CspPageAssertions


@tagged("post_install", "-at_install")
class TestShopScriptPolicy(CspPageAssertions, HttpCase):
    def test_shop_pages(self):
        product = self.env["product.template"].create(
            {"name": "CSP Desk", "is_published": True, "list_price": 10.0}
        )
        for url in ("/shop", product.website_url, "/shop/cart"):
            self.assertPageScriptsNonced(url)
