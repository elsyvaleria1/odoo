import logging

from odoo.fields import Command
from odoo.http import root
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.models.website import CART_SESSION_CACHE_KEY
from odoo.addons.website_sale.tests.common import WebsiteSaleCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestCartOnReadonlyPage(HttpCase, WebsiteSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._enable_pricelists()
        cls.customer = cls._create_new_portal_user(website_id=cls.website.id)
        cls.stale_pricelist = cls._create_pricelist(
            name="Stale", website_id=cls.website.id
        )
        cls.current_pricelist = cls._create_pricelist(
            name="Current", website_id=cls.website.id
        )
        cls.customer.partner_id.property_product_pricelist = cls.current_pricelist
        cls.customer_cart = cls.env["sale.order"].create(
            {
                "partner_id": cls.customer.partner_id.id,
                "website_id": cls.website.id,
                "pricelist_id": cls.stale_pricelist.id,
                "line_ids": [Command.create({"product_id": cls.product.id})],
            }
        )
        page = cls.website.with_context(website_id=cls.website.id).new_page(
            "readonly-cart"
        )
        cls.env["website.page"].browse(page["page_id"]).is_published = True
        cls.page_url = page["url"]

    def _cart_pricelist_after(self, response):
        self.assertEqual(response.status_code, 200, response.url)
        self.env.invalidate_all()
        pricelist = self.customer_cart.pricelist_id
        _logger.debug("%s -> cart pricelist %s", response.url, pricelist.name)
        return pricelist

    def test_a_cart_resumed_on_a_readonly_page_is_cached_and_refreshed_by_the_next_writable_request(
        self,
    ):
        self.authenticate(self.customer.login, self.customer.login)

        page = self.url_open(self.page_url)
        self.assertEqual(self._cart_pricelist_after(page), self.stale_pricelist)
        session = root.session_store.get(self.opener.cookies["session_id"])
        self.assertEqual(session[CART_SESSION_CACHE_KEY], self.customer_cart.id)

        cart = self.url_open("/shop/cart")
        self.assertEqual(self._cart_pricelist_after(cart), self.current_pricelist)

    def test_a_cart_pricelist_read_on_a_readonly_route_is_recomputed_by_the_next_writable_request(
        self,
    ):
        session = self.authenticate(self.customer.login, self.customer.login)
        session[CART_SESSION_CACHE_KEY] = self.customer_cart.id
        root.session_store.save(session)

        self.call_jsonrpc(
            "/website_sale/get_combination_info",
            {
                "product_template_id": self.product.product_tmpl_id.id,
                "product_id": self.product.id,
                "combination": [],
                "add_qty": 1,
            },
        )
        self.env.invalidate_all()
        self.assertEqual(self.customer_cart.pricelist_id, self.stale_pricelist)

        shop = self.url_open("/shop")
        self.assertEqual(self._cart_pricelist_after(shop), self.current_pricelist)
