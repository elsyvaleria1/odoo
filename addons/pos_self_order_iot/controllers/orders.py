from werkzeug.exceptions import Forbidden, Unauthorized

from odoo import fields, http
from odoo.exceptions import UserError

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController

# what a kiosk sends a box: an action on a device, and a WebRTC offer
KIOSK_IOT_MESSAGE_TYPES = frozenset({"iot_action", "webrtc_offer"})


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
        iot_box = self._kiosk_iot_boxes(pos_config).filtered(
            lambda box: box.id == iot_box_id
        )
        if not iot_box:
            return {"error": "Self Order: No IoT Box found"}
        return iot_box.read(["ip", "identifier", "version"])

    @http.route(
        "/pos-self-order/iot-box-websocket-channel/", auth="public", type="jsonrpc"
    )
    def iot_box_websocket_channel(  # noqa: E8539  device: a device's or a kiosk's credential, presented by a program
        self, access_token, message=None, message_type="iot_action"
    ):
        # the IoT channel is the database's, every box's traffic on it: it is
        # a kiosk's, which drives its point of sale's boxes from the browser,
        # never a phone's, whose token every QR code prints
        try:
            pos_config = self._get_pos_config(access_token)
        except Unauthorized:
            # If pos is closed, we don't want a traceback, and we don't care
            # about sending messages to the iot box: we return an empty ws channel
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
            pos_config.env["iot.channel"]._send_message(message, message_type)
        return pos_config.env["iot.channel"]._get_iot_channel()

    def _kiosk_iot_boxes(self, pos_config):
        if pos_config.self_ordering_mode != "kiosk":
            return pos_config.env["iot.box"]
        return pos_config.iot_device_ids.iot_id
