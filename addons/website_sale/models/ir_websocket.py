from odoo import models
from odoo.http import request

from odoo.addons.bus.websocket import wsrequest
from odoo.addons.website_sale.models.website import CART_SESSION_CACHE_KEY


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _get_bus_channels(self, channels):
        # the visitor's cart tells their other tabs it changed
        # (sale.order._notify_cart_changed); the server picks the channel, so
        # nobody hears another visitor's cart
        channels = super()._get_bus_channels(channels)
        session = (request or wsrequest).session
        order_id = session.get(CART_SESSION_CACHE_KEY) if session else None
        if order_id:
            channels = [*channels, self.env["sale.order"].browse(order_id)]
        return channels
