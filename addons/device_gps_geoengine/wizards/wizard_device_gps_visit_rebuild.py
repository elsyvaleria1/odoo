from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.datetime import all_timezones, start_of


class WizardDeviceGpsVisitRebuild(models.TransientModel):
    _name = "wizard.device.gps.visit.rebuild"
    _description = "Rebuild GPS Parcel Visits"

    date_from = fields.Date(
        default=lambda self: self._today() - timedelta(days=7),
        required=True,
    )
    date_to = fields.Date(
        default=lambda self: self._today(),
        required=True,
        help="Inclusive.",
    )
    tz = fields.Selection(
        selection=[(zone, zone) for zone in all_timezones()],
        string="Calendar Timezone",
        default=lambda self: self._default_tz(),
        required=True,
        help="The selected dates are calendar days in this timezone.",
    )
    device_ids = fields.Many2many(
        comodel_name="device.device",
        string="Devices",
        domain=[("is_gps_device", "=", True)],
        help="Empty means every GPS device.",
    )

    def _today(self):
        zone = self.env.context.get("default_tz") or self._default_tz()
        return fields.Date.context_today(self.with_context(tz=zone))

    def _default_tz(self):
        return self.env.user.tz or "UTC"

    def action_rebuild(self) -> dict:
        self.check_singleton()
        self.check_access("write")
        if self.date_from > self.date_to:
            raise UserError(
                self.env._("The start date must not be after the end date.")
            )
        devices = self.device_ids or self.env["device.device"].search(
            [("is_gps_device", "=", True)]
        )
        zone = ZoneInfo(self.tz)
        date_from = (
            start_of(datetime.combine(self.date_from, time.min, zone), "day")
            .astimezone(UTC)
            .replace(tzinfo=None)
        )
        date_to = (
            start_of(
                datetime.combine(self.date_to + timedelta(days=1), time.min, zone),
                "day",
            )
            .astimezone(UTC)
            .replace(tzinfo=None)
        )
        created = self.env["device.client.visit"]._rebuild_from_gps_logs(
            devices.ids, date_from, date_to
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._(
                    "%(count)s client visit(s) rebuilt.", count=created
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
