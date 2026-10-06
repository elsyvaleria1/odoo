from odoo.tests import tagged

from odoo.addons.website_sale.tests.common import MockRequest
from odoo.addons.website_sale_collect.controllers.delivery import InStoreDelivery
from odoo.addons.website_sale_collect.tests.common import ClickAndCollectCommon


@tagged("post_install", "-at_install")
class TestClickAndCollectExpressCheckout(ClickAndCollectCommon):
    def test_exclude_in_store_delivery_methods(self):
        express_delivery_methods = (
            InStoreDelivery._get_delivery_methods_express_checkout(self.cart)
        )

        self.assertNotIn(self.in_store_dm, express_delivery_methods)

    def test_the_delivery_step_offers_each_store_s_default_location(self):
        self.assertEqual(self.website.in_store_dm_id, self.in_store_dm)
        with MockRequest(self.env, website=self.website, sale_order_id=self.cart.id):
            context = InStoreDelivery()._prepare_additional_delivery_context()
        self.assertIn(self.in_store_dm.id, context["default_pickup_locations"])
