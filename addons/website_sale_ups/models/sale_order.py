from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def check_ups_service_type(self, value) -> dict | None:
        if value.get("sale_id"):
            order = self.browse(int(value["sale_id"]))
            with _debug.perf("ups_rate_shipment", cr=self.env.cr, order=order) as span:
                check = order.carrier_id.ups_rate_shipment(order)
                span.set(success=check["success"])
            if check["success"]:
                return {}
            else:
                _debug.logic(
                    "ups_service_type_reset",
                    order=order,
                    was=order.ups_service_type,
                    now=order.carrier_id.ups_default_service_type,
                )
                order.ups_service_type = order.carrier_id.ups_default_service_type
                return {"error": check["error_message"]}
        return None
