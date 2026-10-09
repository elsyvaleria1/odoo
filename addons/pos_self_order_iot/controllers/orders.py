from werkzeug.exceptions import Unauthorized

from odoo import fields, http
from odoo.exceptions import UserError

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController


class PosSelfOrderControllerIot(PosSelfOrderController):
    @http.route(
        "/pos-self-order/iot-payment-cancelled/",
        auth="public",
        type="jsonrpc",
        website=True,
    )
    def iot_payment_cancelled(self, access_token, order_id):  # noqa: E8539  device: a device's or a kiosk's credential, presented by a program
        pos_config = self._get_pos_config(access_token)
        order = pos_config.env["pos.order"].search(
            [("id", "=", order_id), ("config_id", "=", pos_config.id)]
        )
        order._send_payment_result("fail")

    @http.route(
        "/pos-self-order/iot-payment-success/",
        auth="public",
        type="jsonrpc",
        website=True,
    )
    def iot_payment_success(  # noqa: E8539  device: a device's or a kiosk's credential, presented by a program
        self, access_token, order_id, payment_method_id, payment_info
    ):
        # the IoT box answers the kiosk's browser, never this server: the
        # approval cannot be checked with the terminal, so it is taken only
        # from a kiosk, for its own terminal, once per transaction
        pos_config = self._get_pos_config(access_token)
        payment_method = pos_config.payment_method_ids.filtered(
            lambda p: p.id == payment_method_id and p.iot_device_id
        )
        order = pos_config.env["pos.order"].search(
            [("id", "=", order_id), ("config_id", "=", pos_config.id)]
        )
        if not order or not payment_method or pos_config.self_ordering_mode != "kiosk":
            raise Unauthorized
        try:
            with order.env.cr.savepoint():
                paid = order._add_kiosk_terminal_payment(
                    payment_method,
                    {
                        "payment_date": fields.Datetime.now(),
                        "card_type": payment_info.get("Card"),
                        "transaction_id": payment_info.get("PaymentTransactionID"),
                        "payment_status": "Success",
                        "ticket": payment_info.get("Ticket"),
                    },
                )
        except UserError as error:
            return {"error": error.args[0]}
        if paid:
            order._send_payment_result("Success")
        return None

    @http.route(
        "/pos-self-order/get-iot-box-data/", auth="public", type="jsonrpc", website=True
    )
    def get_iot_box_data(self, access_token, iot_box_id):  # noqa: E8539  device: a device's or a kiosk's credential, presented by a program
        pos_config = self._get_pos_config(access_token)
        iot_data = pos_config.env["iot.box"].sudo().browse(iot_box_id)
        if not iot_data:
            return {"error": "Self Order: No IoT Box found"}
        return iot_data.read(["ip", "identifier", "version"])

    @http.route(
        "/pos-self-order/iot-box-websocket-channel/", auth="public", type="jsonrpc"
    )
    def iot_box_websocket_channel(  # noqa: E8539  device: a device's or a kiosk's credential, presented by a program
        self, access_token, message=None, message_type="iot_action"
    ):
        try:
            pos_config = self._get_pos_config(access_token)
        except Unauthorized:
            # If pos is closed, we don't want a traceback, and we don't care
            # about sending messages to the iot box: we return an empty ws channel
            return ""
        iot_channel = pos_config.env["iot.channel"]
        if message:
            iot_channel.send_message(message, message_type)

        return iot_channel.get_iot_channel()
