import secrets

from odoo import api, models
from odoo.exceptions import AccessError


class IotChannel(models.AbstractModel):
    _name = "iot.channel"
    _description = "The Websocket IoT Channel"

    # Whoever holds the channel name reads every message on it -- print jobs,
    # displays, payment terminals -- and the bus lets any client subscribe to
    # a name. The public methods are what a web client may call; server code
    # calls the private ones.
    def get_iot_channel(self):
        self._check_iot_channel_access()
        return self._get_iot_channel()

    @api.model
    def send_message(self, message, message_type="iot_action"):
        self._check_iot_channel_access()
        self._send_message(message, message_type)

    def _check_iot_channel_access(self) -> None:
        if not self.env.su and not self.env.user._is_internal():
            raise AccessError(self.env._("Only internal users can reach IoT boxes."))

    def _get_iot_channel(self):
        """Get the IoT websocket channel name (unique for every company).

        :return: The IoT websocket channel used to send the message
        """
        ir_config_parameter = self.env["ir.config_parameter"].sudo()
        ws_channel = ir_config_parameter.get_param("iot.ws_channel")
        if not ws_channel:
            ws_channel = f"iot_channel-{secrets.token_hex(16)}"
            ir_config_parameter.set_param("iot.ws_channel", ws_channel)

        return ws_channel

    def _send_message(self, message, message_type="iot_action"):
        """Send a message to a device via websocket.

        :param dict message: The message to send to the IoT Box
        :param str message_type: The type of the message (Default: call an action on a device)
        """
        self.env["bus.bus"]._sendone(self._get_iot_channel(), message_type, message)
