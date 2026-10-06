from odoo import api, fields, models


class DeviceDeviceMqtt(models.Model):
    _inherit = "device.device"

    comm_protocol = fields.Selection(
        selection_add=[("mqtt", "MQTT")],
        ondelete={"mqtt": "set default"},
    )

    mqtt_client_id = fields.Char(
        help="Client ID for MQTT connection (defaults to device identifier)"
    )
    mqtt_subscribe_topics = fields.Text(
        help="MQTT topics to subscribe to (one per line). Leave empty to use config default."
    )
    mqtt_publish_topic = fields.Char(
        help="MQTT topic for publishing commands. Leave empty to use config default."
    )

    @api.model
    def _persistent_protocols(self) -> list:
        return [*super()._persistent_protocols(), "mqtt"]

    @api.model
    def _streamed_protocols(self) -> list:
        return [*super()._streamed_protocols(), "mqtt"]

    @api.model
    def _stream_fields(self):
        return super()._stream_fields() | {
            "identifier",
            "mqtt_client_id",
            "mqtt_subscribe_topics",
            "mqtt_publish_topic",
        }

    def _protocol_default_port(self):
        self.check_singleton()
        if self.comm_protocol == "mqtt":
            use_tls = self.config_id.mqtt_use_tls if self.config_id else False
            return 8883 if use_tls else 1883
        return super()._protocol_default_port()

    def _protocol_display_endpoint(self):
        self.check_singleton()
        if self.comm_protocol == "mqtt":
            return self._mqtt_url()
        return super()._protocol_display_endpoint()

    def _mqtt_url(self) -> str:
        self.check_singleton()
        use_tls = self.config_id.mqtt_use_tls if self.config_id else False
        endpoint = self._get_effective_endpoint()
        port = self._get_port_effective() or self._protocol_default_port()
        return f"{'mqtts' if use_tls else 'mqtt'}://{endpoint}:{port}"

    def _stream_vals(self):
        self.check_singleton()
        if self.comm_protocol != "mqtt":
            return super()._stream_vals()
        config = self.config_id.sudo()
        basic = bool(config) and config.auth_type == "basic"
        options = {
            "qos": int(config.mqtt_qos) if config else 1,
            "client_id": self.mqtt_client_id or self.identifier,
        }
        publish_topic = self._get_effective_mqtt_publish_topic()
        if publish_topic:
            options["publish_topic"] = publish_topic
        if config and config.mqtt_session_expiry_interval > 0:
            options["session_expiry_interval"] = config.mqtt_session_expiry_interval
        return {
            "protocol": "mqtt",
            "url": self._mqtt_url(),
            "credential_id": config.credential_id.id if basic else False,
            "login": (config.auth_username if basic else False) or False,
            "subscriptions": {
                "topics": [
                    topic.strip()
                    for topic in (
                        self._get_effective_mqtt_subscribe_topics() or ""
                    ).splitlines()
                    if topic.strip()
                ]
            },
            "options": options,
        }

    def mqtt_connect(self):
        return self._stream_connect()

    def mqtt_disconnect(self):
        return self._stream_disconnect()

    def mqtt_read_data(self):
        return self._stream_read_status()

    def mqtt_send(self, payload, **meta):
        return self._stream_send(payload, **meta)

    def _get_effective_mqtt_publish_topic(self):
        self.check_singleton()
        if self.mqtt_publish_topic:
            return self.mqtt_publish_topic
        return self.config_id.mqtt_publish_topic if self.config_id else ""

    def _get_effective_mqtt_subscribe_topics(self):
        self.check_singleton()
        if self.mqtt_subscribe_topics:
            return self.mqtt_subscribe_topics
        return self.config_id.mqtt_subscribe_topics if self.config_id else ""
