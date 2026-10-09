from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from odoo.addons.pos_online_payment.controllers.payment_portal import PaymentPortal


class PaymentPortalSelfOrder(PaymentPortal):
    @http.route()
    def pos_order_pay(self, pos_order_id, access_token=None, exit_route=None):
        pos_order_sudo = self._check_order_access(pos_order_id, access_token)
        pos_order_sudo._send_notification_online_payment_status("progress")
        return super().pos_order_pay(
            pos_order_id, access_token=access_token, exit_route=exit_route
        )

    @http.route()
    def pos_order_pay_confirmation(
        self, pos_order_id, tx_id=None, access_token=None, exit_route=None, **kwargs
    ):
        result = super().pos_order_pay_confirmation(
            pos_order_id,
            tx_id=tx_id,
            access_token=access_token,
            exit_route=exit_route,
            **kwargs,
        )
        tx_id = self._cast_as_int(tx_id)
        if not tx_id:
            return result
        try:
            pos_order_sudo = self._check_order_access(pos_order_id, access_token)
        except AccessError, ValidationError:
            return result
        tx_sudo = request.env["payment.transaction"].sudo().browse(tx_id).exists()
        if tx_sudo.pos_order_id == pos_order_sudo and tx_sudo.state not in (
            "authorized",
            "done",
        ):
            pos_order_sudo._send_notification_online_payment_status("fail")
        return result
