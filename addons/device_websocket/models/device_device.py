from odoo import api, fields, models


class DeviceDeviceWebsocket(models.Model):
    _inherit = "device.device"

    comm_protocol = fields.Selection(
        selection_add=[("websocket", "WebSocket")],
        ondelete={"websocket": "set default"},
    )

    _WEBSOCKET_DEFAULT_PORT = 80

    @api.model
    def _persistent_protocols(self) -> list:
        return [*super()._persistent_protocols(), "websocket"]

    @api.model
    def _streamed_protocols(self) -> list:
        return [*super()._streamed_protocols(), "websocket"]

    @api.model
    def _stream_fields(self):
        return super()._stream_fields() | {"http_endpoint_path"}

    def _protocol_default_port(self):
        self.check_singleton()
        if self.comm_protocol == "websocket":
            return self._WEBSOCKET_DEFAULT_PORT
        return super()._protocol_default_port()

    def _protocol_display_endpoint(self):
        self.check_singleton()
        if self.comm_protocol == "websocket":
            return self._websocket_url()
        return super()._protocol_display_endpoint()

    def _websocket_url(self):
        self.check_singleton()
        port = self.port or self._WEBSOCKET_DEFAULT_PORT
        url = f"ws://{self.endpoint}:{port}"
        path = self.http_endpoint_path or ""
        if path and not path.startswith("/"):
            path = "/" + path
        return url + path

    def _stream_vals(self):
        self.check_singleton()
        if self.comm_protocol != "websocket":
            return super()._stream_vals()
        config = self.config_id.sudo()
        options = {}
        credential_id = False
        login = False
        if config and config.auth_type in ("basic", "bearer") and config.credential_id:
            options["auth"] = "basic" if config.auth_type == "basic" else "bearer"
            credential_id = config.credential_id.id
            login = config.auth_username if config.auth_type == "basic" else False
        return {
            "protocol": "websocket",
            "url": self._websocket_url(),
            "credential_id": credential_id,
            "login": login or False,
            "subscriptions": {},
            "options": options,
            "heartbeat_seconds": (config.ws_ping_interval if config else 0) or 30,
        }

    def websocket_connect(self):
        return self._stream_connect()

    def websocket_disconnect(self):
        return self._stream_disconnect()

    def websocket_read_data(self):
        return self._stream_read_status()

    def websocket_send(self, payload, **meta):
        return self._stream_send(payload, **meta)
