import logging
from datetime import timedelta

from odoo import api, fields, models

from .device_gps_speed_event import EVENT_GAP

_logger = logging.getLogger(__name__)

# A burst older than this when first seen is history, not news: after an
# outage the cron does not raise a day of stale alerts at once.
ALERT_LOOKBACK = timedelta(hours=24)


class DeviceGpsSpeedAlert(models.Model):
    """One alert per critical speeding burst, raised once.

    device.gps.speed.event is a view with no memory; this table is what
    remembers which bursts were already reported, and who was told.
    """

    _name = "device.gps.speed.alert"
    _description = "Critical Speed Alert"
    _order = "start desc"
    _rec_name = "start"

    device_id = fields.Many2one(
        comodel_name="device.device",
        index=True,
        required=True,
        ondelete="cascade",
    )
    operator_id = fields.Many2one(comodel_name="hr.employee")
    asset_id = fields.Many2one(
        comodel_name="resource.asset",
        string="Vehicle",
    )
    company_id = fields.Many2one(comodel_name="res.company")
    start = fields.Datetime(required=True)
    end = fields.Datetime(required=True)
    speed_max = fields.Float(
        string="Max Speed (km/h)",
        digits=(6, 0),
    )
    speed_limit = fields.Float(
        string="Critical Limit (km/h)",
        digits=(6, 0),
    )
    duration_min = fields.Float(
        string="Duration (min)",
        digits=(6, 1),
    )
    place = fields.Char()
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Notified",
        help="Who received the activity: the operator's manager, else the "
        "fallback user of the unmapped-stop notification.",
    )
    activity_id = fields.Many2one(
        comodel_name="mail.activity",
        ondelete="set null",
    )

    _device_start_uniq = models.Constraint(
        "UNIQUE(device_id, start)",
        "A burst is alerted once.",
    )

    @api.model
    def _cron_raise_critical(self):
        now = fields.Datetime.now()
        events = (
            self.env["device.gps.speed.event"]
            ._get_recent_events(now - ALERT_LOOKBACK)
            .filtered(
                lambda event: (
                    event.level == "critical"
                    # the burst is over: its peak is final
                    and event.end < now - EVENT_GAP
                )
            )
        )
        if not events:
            return self.browse()
        already = {
            (alert.device_id.id, alert.start)
            for alert in self.search(
                [
                    ("device_id", "in", events.device_id.ids),
                    ("start", ">=", now - ALERT_LOOKBACK),
                ]
            )
        }
        alerts = self.browse()
        for event in events:
            if (event.device_id.id, event.start) in already:
                continue
            alerts |= self._raise(event)
        return alerts

    def _raise(self, event):
        recipient = self._recipient(event)
        alert = self.create(
            {
                "device_id": event.device_id.id,
                "operator_id": event.operator_id.id,
                "asset_id": event.asset_id.id,
                "company_id": event.company_id.id,
                "start": event.start,
                "end": event.end,
                "speed_max": event.speed_max,
                "speed_limit": event.speed_limit,
                "duration_min": event.duration_min,
                "place": event.place,
                "user_id": recipient.id,
            }
        )
        if not recipient:
            _logger.warning(
                "%s drove %s km/h over a %s km/h critical limit and there is "
                "nobody to tell: the operator has no manager with a user and "
                "no fallback user is configured.",
                event.device_id.display_name,
                round(event.speed_max),
                round(event.speed_limit),
            )
            return alert
        who = event.operator_id.name or event.device_id.display_name
        what = event.asset_id.display_name or event.device_id.display_name
        summary = self.env._(
            "%(who)s at %(speed)s km/h, critical limit %(limit)s",
            who=who,
            speed=round(event.speed_max),
            limit=round(event.speed_limit),
        )
        note = self.env._(
            "%(who)s drove %(what)s at up to %(speed)s km/h for %(minutes)s "
            "minutes from %(start)s, over the critical limit of %(limit)s km/h. "
            "Where: %(place)s.",
            who=who,
            what=what,
            speed=round(event.speed_max),
            minutes=round(event.duration_min, 1),
            # context_timestamp reads the ENVIRONMENT's timezone, not the
            # record's, and this runs in the cron user's environment. Passing
            # the recipient alone would stamp the note with the cron user's
            # clock -- UTC, for a fleet that reads its own six hours earlier.
            start=fields.Datetime.context_timestamp(
                recipient.with_context(tz=recipient.tz or "UTC"), event.start
            ).strftime("%d/%m/%Y %H:%M"),
            limit=round(event.speed_limit),
            place=event.place,
        )
        activity = event.device_id.activity_schedule(
            "mail.mail_activity_data_todo",
            summary=summary,
            note=note,
            user_id=recipient.id,
        )
        alert.activity_id = activity
        return alert

    def _recipient(self, event):
        manager = event.operator_id.parent_id.user_id
        if manager:
            return manager
        return event.device_id._dwell_fallback_user()
