import logging
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.libs.json import loads as json_loads

from odoo.addons.base.models.res_partner import _selection_timezones

_logger = logging.getLogger(__name__)

COUNTER_CATEGORY_CODE = "counter_plc"

_TS_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})-(?P<time>\d{2}:\d{2}:\d{2})(?:\.(?P<frac>\d+))?$"
)


class DeviceDevice(models.Model):
    _inherit = "device.device"

    is_counter_device = fields.Boolean(
        compute="_compute_is_counter_device",
        store=True,
        help="True when the device category code is 'counter_plc'.",
    )
    workcenter_id = fields.Many2one(
        comodel_name="mrp.workcenter",
        string="Work Center",
        help="Manufacturing work center this machine belongs to. PLC counts "
        "are attributed to the work order in progress on this work center. "
        "Set directly: nothing cross-checks it against the machinery asset the "
        "work center names, because a PLC need not be a registered asset.",
    )
    counter_timezone = fields.Selection(
        selection=_selection_timezones,
        string="PLC Clock Timezone",
        default="UTC",
        help="Timezone the PLC's own clock runs on. Its payloads carry a bare "
        "timestamp with no offset, so this is what converts it to UTC.",
    )
    counter_reset_dow = fields.Selection(
        selection=[
            ("0", "Monday"),
            ("1", "Tuesday"),
            ("2", "Wednesday"),
            ("3", "Thursday"),
            ("4", "Friday"),
            ("5", "Saturday"),
            ("6", "Sunday"),
        ],
        string="Counter Reset Day",
        default="6",
        help="Weekday on which the PLC resets the cumulative counter to zero.",
    )
    last_count = fields.Integer(
        readonly=True,
        help="Last cumulative counter value seen from the PLC.",
    )
    bucket_ids = fields.One2many(
        comodel_name="device.machine.bucket",
        inverse_name="device_id",
        string="Hourly Buckets",
    )
    bucket_count = fields.Integer(compute="_compute_bucket_count")
    reading_ids = fields.One2many(
        comodel_name="device.machine.reading",
        inverse_name="device_id",
        string="Recent Readings",
    )

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        if not self.env.context.get("counter_machine_default"):
            return defaults
        if "device_category_id" in fields:
            category = self.env["device.kind"].search(
                [("code", "=", COUNTER_CATEGORY_CODE)], limit=1
            )
            if category:
                defaults["device_category_id"] = category.id
        if "config_id" in fields:
            config = self.env.ref(
                "device_machines.config_aws_iot_mqtt", raise_if_not_found=False
            )
            if config:
                defaults["config_id"] = config.id
        if "comm_protocol" in fields:
            defaults["comm_protocol"] = "mqtt"
        return defaults

    @api.model
    def _device_kind_categories(self, kind):
        codes = super()._device_kind_categories(kind)
        if kind == "counter":
            return [*codes, COUNTER_CATEGORY_CODE]
        return codes

    @api.depends("device_category_id", "device_category_id.code")
    def _compute_is_counter_device(self) -> None:
        for record in self:
            record.is_counter_device = record._is_device_kind("counter")

    @api.depends("bucket_ids")
    def _compute_bucket_count(self) -> None:
        data = self.env["device.machine.bucket"]._read_group(
            [("device_id", "in", self.ids)],
            ["device_id"],
            ["__count"],
        )
        mapping = {d.id: c for d, c in data}
        for record in self:
            record.bucket_count = mapping.get(record.id, 0)

    def _parse_plc_timestamp(self, raw):
        if not raw:
            raise ValueError("Empty PLC timestamp")
        match = _TS_RE.match(raw.strip())
        if not match:
            raise ValueError(f"Unrecognised PLC timestamp: {raw!r}")
        date_str = match.group("date")
        time_str = match.group("time")
        frac = (match.group("frac") or "")[:6].ljust(6, "0")
        naive = datetime.fromisoformat(f"{date_str}T{time_str}.{frac}")
        plc_zone = ZoneInfo(self.counter_timezone) if self.counter_timezone else UTC
        return naive.replace(tzinfo=plc_zone).astimezone(UTC)

    def _ingest_counter_payload(self, payload):
        self.check_singleton()
        empty = self.env["device.machine.bucket"]
        if not isinstance(payload, dict) or not payload:
            _logger.warning("device_machines: empty/invalid payload: %r", payload)
            return empty

        key, body = next(iter(payload.items()))
        if not isinstance(body, dict):
            _logger.warning("device_machines: payload body is not a dict: %r", body)
            return empty
        identifier = body.get("Maquina") or key

        if identifier != self.identifier:
            return empty

        try:
            ts = self._parse_plc_timestamp(body.get("Time Stamp"))
            count = int(body.get("Conteo"))
        except ValueError, TypeError:
            _logger.exception(
                "device_machines: bad timestamp/Conteo in payload %r", body
            )
            return empty

        ts_naive = ts.replace(tzinfo=None)
        if self.env["device.machine.reading"].search_count(
            [("device_id", "=", self.id), ("timestamp", "=", ts_naive)],
            limit=1,
        ):
            return empty

        bucket = self.env["device.machine.bucket"]._apply_reading(
            device=self, timestamp=ts, count=count
        )
        self.env["device.machine.reading"]._record(self, ts, count)
        if count == 0 or count >= (self.last_count or 0):
            self.last_count = count
        self._attribute_to_workorder(count, ts)
        return bucket

    def _attribute_to_workorder(self, count, timestamp) -> None:
        self.check_singleton()
        if not self.workcenter_id:
            return
        workorder = self.env["mrp.workorder"].search(
            [
                ("workcenter_id", "=", self.workcenter_id.id),
                ("state", "=", "progress"),
            ],
            limit=1,
        )
        if workorder:
            self.env["device.machine.workorder"]._accumulate(
                self, workorder, count, timestamp
            )

    def _stream_vals(self):
        vals = super()._stream_vals()
        if vals is not None and self.is_counter_device:
            vals["options"] = {**vals.get("options", {}), "qos": 1}
        return vals

    def _on_stream_frame(self, stream, payload, meta) -> None:
        self.check_singleton()
        if not self.is_counter_device:
            super()._on_stream_frame(stream, payload, meta)
            return
        text = (
            payload.decode(errors="replace") if isinstance(payload, bytes) else payload
        )
        try:
            data = json_loads(text)
        except ValueError:
            _logger.warning(
                "device_machines: undecodable payload on topic %r", meta.get("topic")
            )
            return
        bucket = self._ingest_counter_payload(data)
        if bucket:
            _logger.info(
                "device_machines: ingested device=%s topic=%r bucket_id=%s "
                "count_end=%s delta=%s",
                self.name,
                meta.get("topic"),
                bucket.id,
                bucket.count_end,
                bucket.delta,
            )
