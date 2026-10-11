from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads

_debug = DebugLog(__name__)


class DeviceDeviceStream(models.Model):
    _inherit = "device.device"

    stream_id = fields.Many2one(
        comodel_name="integration.stream",
        copy=False,
        readonly=True,
        ondelete="set null",
        help="The connection the stream worker holds for this device, for a "
        "protocol that keeps one open.",
    )

    @api.model
    def _streamed_protocols(self) -> list:
        return []

    @api.model
    def _stream_fields(self):
        return frozenset(
            {
                "name",
                "active",
                "comm_protocol",
                "company_id",
                "endpoint",
                "port",
                "config_id",
                "certificate_id",
            }
        )

    def _stream_vals(self):
        self.check_singleton()

    @_debug.perf.timed
    def _sync_stream(self, active=None) -> None:
        for device in self:
            vals = device._stream_vals()
            managed_device = device.sudo()
            stream = managed_device.stream_id
            if vals is None:
                if stream:
                    stream.write({"active": False})
                continue
            vals.update(
                name=f"{device.name} ({vals['protocol']})",
                res_model=device._name,
                res_id=device.id,
                company_id=device.company_id.id or False,
                certificate_id=device.certificate_id.id,
                ca_certificate_id=device.config_id.ca_certificate_id.id,
            )
            if active is not None:
                vals["active"] = active
            elif not device.active:
                vals["active"] = False
            if stream:
                stream.write(vals)
            else:
                vals.setdefault("active", device.active)
                managed_device.stream_id = managed_device.env[
                    "integration.stream"
                ].create(vals)

    @_debug.perf.timed
    def _stream_connect(self) -> bool:
        self.check_singleton()
        self.check_access("write")
        self._sync_stream(active=True)
        return True

    @_debug.perf.timed
    def _stream_disconnect(self) -> bool:
        self.check_singleton()
        self.check_access("write")
        self._sync_stream(active=False)
        self._write_state_retry(
            {
                "connection_state": "disconnected",
                "connection_state_message": "Disconnected",
            },
            f"device: {self.comm_protocol} disconnect action",
        )
        return True

    @_debug.perf.timed
    def _stream_read_status(self) -> dict:
        self.check_singleton()
        self.check_access("write")
        self._sync_stream(active=True)
        stream = self.sudo().stream_id
        return {
            "state": stream.state,
            "date_last_frame": stream.date_last_frame,
            "frames_in": stream.frames_in,
        }

    @_debug.perf.timed
    def _stream_send(self, payload, **meta):
        self.check_singleton()
        self.check_access("write")
        if not self.stream_id:
            self._sync_stream()
        return self.sudo().stream_id.send(payload, **meta)

    @_debug.perf.timed
    def _on_stream_frame(self, stream, payload, meta) -> None:
        self.check_singleton()
        text = (
            payload.decode(errors="replace") if isinstance(payload, bytes) else payload
        )
        try:
            data = json_loads(text)
        except ValueError:
            data = {"raw": text, "topic": meta.get("topic")}
        self._store_data_point(data, source_topic=meta.get("topic"), raw_payload=text)

    _STREAM_STATES = {
        "open": "connected",
        "connecting": "disconnected",
        "stopped": "disconnected",
        "backoff": "error",
        "error": "error",
    }

    def _on_stream_state(self, stream, state, message) -> None:
        self.check_singleton()
        connection_state = self._STREAM_STATES.get(state, "error")
        self._set_connection_state(connection_state, message or False)
