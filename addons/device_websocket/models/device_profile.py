from odoo import api, fields, models


class DeviceConfig(models.Model):
    _inherit = "device.profile"

    protocol = fields.Selection(
        selection_add=[("websocket", "WebSocket")],
        ondelete={"websocket": "set default"},
    )

    ws_auto_reconnect = fields.Boolean(
        default=True,
        help="Automatically reconnect WebSocket if connection is lost",
    )
    ws_ping_interval = fields.Integer(
        default=30,
        help="WebSocket keepalive ping interval",
    )

    @api.model
    def _stream_fields(self):
        return super()._stream_fields() | {"ws_ping_interval"}
