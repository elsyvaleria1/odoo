from odoo.tests import tagged

from odoo.addons.bus.models.bus import channel_with_db, dispatch, hashable
from odoo.addons.bus.tests.common import WebsocketCase


@tagged("post_install", "-at_install")
class TestCartBusSubscription(WebsocketCase):
    def test_a_visitors_websocket_hears_their_cart(self):
        product = self.env["product.product"].create(
            {
                "name": "PN Kettle",
                "list_price": 10.0,
                "is_published": True,
                "sale_ok": True,
            }
        )
        session = self.authenticate(None, None)
        self.call_jsonrpc(
            "/shop/cart/add",
            {
                "product_template_id": product.product_tmpl_id.id,
                "product_id": product.id,
                "quantity": 1,
            },
        )
        order = (
            self.env["sale.order.line"]
            .search([("product_id", "=", product.id)], order="id desc", limit=1)
            .order_id
        )

        websocket = self.websocket_connect(cookie=f"session_id={session.sid}")
        self.subscribe(websocket, [], self.env["bus.bus"]._bus_last_id())

        self.assertIn(
            hashable(channel_with_db(self.env.registry.db_name, order)),
            dispatch._channels_to_ws,
        )
