from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DeviceConfig(models.Model):
    _inherit = "device.profile"

    protocol = fields.Selection(
        selection_add=[("mqtt", "MQTT")],
        ondelete={"mqtt": "set default"},
    )

    mqtt_qos = fields.Selection(
        selection=[
            ("0", "At most once (QoS 0)"),
            ("1", "At least once (QoS 1)"),
            ("2", "Exactly once (QoS 2)"),
        ],
        default="1",
        help="MQTT Quality of Service level",
    )
    mqtt_use_tls = fields.Boolean(
        default=False,
        help="Enable TLS/SSL encryption for MQTT connections",
    )

    mqtt_session_expiry_interval = fields.Integer(
        default=0,
        help="MQTT v5.0: Session expiry interval in seconds. "
        "0 = session ends on disconnect (default). "
        "Max 4,294,967,295 seconds (~136 years). "
        "Set to preserve session state between connections.",
    )
    mqtt_receive_maximum = fields.Integer(
        default=65535,
        help="MQTT v5.0: Maximum number of QoS 1 and QoS 2 messages "
        "the server can send simultaneously. "
        "Range: 1-65535. Default: 65535 (MQTT v5.0 spec default).",
    )
    mqtt_max_packet_size = fields.Integer(
        default=0,
        help="MQTT v5.0: Maximum packet size client is willing to accept. "
        "0 = no limit (default). "
        "If set, server won't send packets larger than this value.",
    )

    mqtt_subscribe_topics = fields.Text(
        help="Default MQTT topics to subscribe to (one per line). Can be overridden at device level."
    )
    mqtt_publish_topic = fields.Char(
        help="Default MQTT topic for publishing commands. Can be overridden at device level."
    )

    @api.model
    def _stream_fields(self):
        return super()._stream_fields() | {
            "mqtt_qos",
            "mqtt_use_tls",
            "mqtt_session_expiry_interval",
            "mqtt_subscribe_topics",
            "mqtt_publish_topic",
        }

    @api.constrains("mqtt_receive_maximum")
    def _check_mqtt_receive_maximum(self) -> None:
        for config in self:
            if config.mqtt_receive_maximum < 1 or config.mqtt_receive_maximum > 65535:
                raise ValidationError(
                    self.env._(
                        "MQTT Receive Maximum must be between 1 and 65535 (MQTT v5.0 specification)"
                    )
                )

    @api.constrains("mqtt_session_expiry_interval")
    def _check_mqtt_session_expiry(self) -> None:
        for config in self:
            if (
                config.mqtt_session_expiry_interval < 0
                or config.mqtt_session_expiry_interval > 4294967295
            ):
                raise ValidationError(
                    self.env._(
                        "MQTT Session Expiry Interval must be between 0 and "
                        "4,294,967,295 seconds (MQTT v5.0 specification)"
                    )
                )

    @api.constrains("mqtt_max_packet_size")
    def _check_mqtt_max_packet_size(self) -> None:
        for config in self:
            if config.mqtt_max_packet_size < 0:
                raise ValidationError(
                    self.env._("MQTT Maximum Packet Size cannot be negative")
                )
