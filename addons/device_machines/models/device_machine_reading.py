from datetime import UTC

from odoo import api, fields, models

MONITOR_KEEP = 50


class DeviceMachineReading(models.Model):
    _name = "device.machine.reading"
    _description = "Remote Machine Raw Reading (monitor buffer)"
    _order = "id desc"

    device_id = fields.Many2one(
        comodel_name="device.device",
        index=True,
        required=True,
        domain="[('is_counter_device', '=', True)]",
        ondelete="cascade",
    )
    timestamp = fields.Datetime(
        required=True,
        help="PLC timestamp parsed from the payload (Time Stamp).",
    )
    count = fields.Integer(
        help="Cumulative counter value (Conteo) reported in this reading."
    )
    received_at = fields.Datetime(
        default=fields.Datetime.now,
        help="When Odoo ingested the reading.",
    )

    @api.model
    def _record(self, device, timestamp, count):
        naive_utc = (
            timestamp.astimezone(UTC).replace(tzinfo=None)
            if timestamp.tzinfo
            else timestamp
        )
        reading = self.create(
            {
                "device_id": device.id,
                "timestamp": naive_utc,
                "count": count,
            }
        )
        stale = self.search(
            [("device_id", "=", device.id)], order="id desc", offset=MONITOR_KEEP
        )
        stale.unlink()
        return reading
