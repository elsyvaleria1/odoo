from werkzeug.exceptions import Forbidden, Unauthorized

from odoo import fields, http
from odoo.exceptions import UserError

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController

KIOSK_IOT_MESSAGE_TYPES = frozenset({"iot_action", "webrtc_offer"})


class PosSelfOrderControllerIot(PosSelfOrderController):
    @http.route(
        "/pos-self-order/iot-payment-cancelled/",
        auth="public",
        type="jsonrpc",
        website=True,
    )
    def iot_payment_cancelled(self, access_token, order_id):
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
    def iot_payment_success(
        self, access_token, order_id, payment_method_id, payment_info
    ):
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
    def get_iot_box_data(self, access_token, iot_box_id):
        pos_config = self._get_pos_config(access_token)
        iot_box = self._kiosk_iot_boxes(pos_config).filtered(
            lambda box: box.id == iot_box_id
        )
        if not iot_box:
            return {"error": "Self Order: No IoT Box found"}
        return iot_box.read(["ip", "identifier", "version"])

    @http.route(
        "/pos-self-order/iot-box-websocket-channel/", auth="public", type="jsonrpc"
    )
    def iot_box_websocket_channel(
        self, access_token, message=None, message_type="iot_action"
    ):
        try:
            pos_config = self._get_pos_config(access_token)
        except Unauthorized:
            return ""
        if pos_config.self_ordering_mode != "kiosk":
            return ""
        if message:
            targets = set(message.get("iot_identifiers") or [])
            if message.get("iot_identifier"):
                targets.add(message["iot_identifier"])
            allowed = set(self._kiosk_iot_boxes(pos_config).mapped("identifier"))
            if (
                message_type not in KIOSK_IOT_MESSAGE_TYPES
                or not targets
                or not targets <= allowed
            ):
                raise Forbidden
        channels = pos_config.env["iot.channel"]
        reply_key = channels._kiosk_reply_key(pos_config)
        if message:
            channels._send_message(message, message_type, reply_key=reply_key)
        return channels._reply_channel(reply_key)

    def _kiosk_iot_boxes(self, pos_config):
        if pos_config.self_ordering_mode != "kiosk":
            return pos_config.env["iot.box"]
        return pos_config.iot_device_ids.iot_id
