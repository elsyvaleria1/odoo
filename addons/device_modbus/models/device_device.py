import logging
import random

from odoo import api, fields, models
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.libs.json import loads as json_loads

_logger = logging.getLogger(__name__)


class DeviceDeviceModbus(models.Model):
    _inherit = "device.device"

    comm_protocol = fields.Selection(
        selection_add=[
            ("modbus_tcp", "Modbus TCP"),
            ("modbus_rtu", "Modbus RTU"),
        ],
        ondelete={"modbus_tcp": "set default", "modbus_rtu": "set default"},
    )

    modbus_register_start = fields.Integer(
        default=0,
        help="Starting register address for Modbus reads (device-specific)",
    )
    modbus_register_count = fields.Integer(
        default=10,
        help="Number of registers to read (device-specific)",
    )
    modbus_poll_seconds = fields.Integer(
        default=60,
        help="How often the stream worker reads the registers.",
    )

    _MODBUS_PROTOCOLS = ("modbus_tcp", "modbus_rtu")
    _MODBUS_DEFAULT_PORT = 502
    _MODBUS_MAX_COUNT = 125

    @api.model
    def _persistent_protocols(self) -> list:
        return [*super()._persistent_protocols(), *self._MODBUS_PROTOCOLS]

    @api.model
    def _streamed_protocols(self) -> list:
        return [*super()._streamed_protocols(), *self._MODBUS_PROTOCOLS]

    @api.model
    def _stream_fields(self):
        return super()._stream_fields() | {
            "modbus_register_start",
            "modbus_register_count",
            "modbus_poll_seconds",
        }

    def _protocol_default_port(self):
        self.check_singleton()
        if self.comm_protocol in self._MODBUS_PROTOCOLS:
            return self._MODBUS_DEFAULT_PORT
        return super()._protocol_default_port()

    def _protocol_display_endpoint(self):
        self.check_singleton()
        if self.comm_protocol == "modbus_tcp":
            return f"{self.endpoint}:{self.port or self._MODBUS_DEFAULT_PORT}"
        if self.comm_protocol == "modbus_rtu":
            return f"{self.endpoint} @ {self.port or 9600} baud"
        return super()._protocol_display_endpoint()

    def _modbus_url(self) -> str:
        self.check_singleton()
        if self.comm_protocol == "modbus_rtu":
            return f"modbus+rtu://{self.endpoint}?baudrate={self.port or 9600}"
        return f"modbus://{self.endpoint}:{self.port or self._MODBUS_DEFAULT_PORT}"

    def _stream_vals(self):
        self.check_singleton()
        if self.comm_protocol not in self._MODBUS_PROTOCOLS:
            return super()._stream_vals()
        config = self.config_id
        return {
            "protocol": "modbus",
            "url": self._modbus_url(),
            "credential_id": False,
            "login": False,
            "subscriptions": {
                "unit_id": config.modbus_unit_id if config else 1,
                "registers": [
                    {
                        "type": (config.modbus_register_type if config else None)
                        or "holding",
                        "start": self.modbus_register_start or 0,
                        "count": min(
                            self.modbus_register_count or 10, self._MODBUS_MAX_COUNT
                        ),
                    }
                ],
            },
            "options": {"timeout": (config.http_timeout if config else 0) or 10},
            "heartbeat_seconds": self.modbus_poll_seconds or 60,
        }

    def _on_stream_frame(self, stream, payload, meta) -> None:
        if self.comm_protocol not in self._MODBUS_PROTOCOLS:
            super()._on_stream_frame(stream, payload, meta)
            return
        self.check_singleton()
        text = (
            payload.decode(errors="replace") if isinstance(payload, bytes) else payload
        )
        data = json_loads(text)
        start = data.get("start_address", 0)
        for index, value in enumerate(data.get("values", [])):
            data[f"register_{start + index}"] = value
        self._store_data_point(data, source_topic=self._modbus_url(), raw_payload=text)

    def _modbus_connect(self):
        return self._stream_connect()

    def _modbus_disconnect(self):
        return self._stream_disconnect()

    def _modbus_read_data(self):
        self.check_singleton()
        self._stream_connect()
        point = self.env["device.data.log"].search(
            [("device_id", "=", self.id)], order="id desc", limit=1
        )
        return point.value_json or {}

    def modbus_tcp_connect(self):
        return self._modbus_connect()

    def modbus_tcp_disconnect(self):
        return self._modbus_disconnect()

    def modbus_tcp_read_data(self):
        return self._modbus_read_data()

    def modbus_rtu_connect(self):
        return self._modbus_connect()

    def modbus_rtu_disconnect(self):
        return self._modbus_disconnect()

    def modbus_rtu_read_data(self):
        return self._modbus_read_data()

    def modbus_write(self, address, value, register_type="holding", **meta):
        self.check_singleton()
        config = self.config_id
        frame = {
            "type": register_type,
            "address": address,
            "unit_id": config.modbus_unit_id if config else 1,
        }
        frame["values" if isinstance(value, list) else "value"] = value
        return self._stream_send(json_dumps_bytes(frame), **meta)

    def _demo_generate_modbus_data(self, protocol_label, source_topic):
        self.check_singleton()

        register_count = self.modbus_register_count or 10
        start = self.modbus_register_start or 0
        demo_values = [random.randint(0, 65535) for _ in range(register_count)]

        demo_data = {
            "demo": True,
            "timestamp": fields.Datetime.now().isoformat(),
            "register_type": "holding_registers",
            "start_address": start,
            "count": register_count,
            "values": demo_values,
        }

        for i, value in enumerate(demo_values):
            demo_data[f"register_{start + i}"] = value

        _logger.info(
            "Generating Modbus %s demo data for device %s", protocol_label, self.name
        )

        self._write_state_retry(
            {
                "connection_state": "connected",
                "connection_state_message": "Demo device (mock data)",
            },
            "device: demo modbus connected",
        )

        self._store_data_point(
            demo_data,
            source_topic=source_topic,
            raw_payload=json_dumps(demo_data),
        )

        return demo_data

    def _demo_generate_modbus_tcp_data(self):
        self.check_singleton()
        return self._demo_generate_modbus_data(
            protocol_label="TCP",
            source_topic=f"modbus://{self.endpoint}:{self.port or 502}",
        )

    def _demo_generate_modbus_rtu_data(self):
        self.check_singleton()
        return self._demo_generate_modbus_data(
            protocol_label="RTU",
            source_topic=f"modbus-rtu://{self.endpoint}",
        )
