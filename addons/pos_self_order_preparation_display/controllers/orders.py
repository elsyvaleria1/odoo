from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController


class PosSelfOrderPreparationDisplayController(PosSelfOrderController):
    @http.route()
    def process_order(self, order, access_token, table_identifier, device_type):
        res = super().process_order(order, access_token, table_identifier, device_type)
        pos_config = self._get_pos_config(access_token)
        self._send_to_preparation_display(pos_config, res["pos.order"][0]["id"])
        return res

    @http.route()
    def change_printer_status(self, access_token, has_paper):
        super().change_printer_status(access_token, has_paper)
        pos_config = self._get_pos_config(access_token)
        pos_config.env["pos.prep.display"]._paper_status_change(pos_config)

    @http.route()
    def remove_order(self, access_token, order_id, order_access_token):
        pos_config = self._get_pos_config(access_token)
        pos_order = pos_config.env["pos.order"].browse(order_id)
        if not pos_order.can_be_cancelled():
            raise UserError(
                request.env._(
                    "This order cannot be cancelled because it's already in preparation."
                )
            )
        super().remove_order(access_token, order_id, order_access_token)

    def _send_to_preparation_display(self, pos_config, pos_order_id):
        pos_order = pos_config.env["pos.order"].browse(pos_order_id).exists()
        if (
            not pos_order.config_id.has_valid_self_payment_method()
            or pos_order.state == "paid"
        ):
            pos_order.env["pos.prep.order"].sudo().process_order(pos_order.id)
