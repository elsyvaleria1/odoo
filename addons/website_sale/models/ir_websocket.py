from odoo import models
from odoo.http import request

from odoo.addons.bus.websocket import wsrequest
from odoo.addons.website_sale.models.website import CART_SESSION_CACHE_KEY


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _implicit_bus_channels(self):
        channels = super()._implicit_bus_channels()
        current = request or wsrequest
        session = current.session if current else None
        order_id = session.get(CART_SESSION_CACHE_KEY) if session else None
        if order_id:
            channels.append(self.env["sale.order"].browse(order_id))
        return channels
