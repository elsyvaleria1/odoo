import datetime

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class EventEvent(models.Model):
    _inherit = "event.event"

    track_gantt_initial_date = fields.Date(compute="_compute_track_gantt_information")
    track_gantt_scale = fields.Char(compute="_compute_track_gantt_information")

    @api.depends("track_ids.date", "track_ids.date_end", "date_begin", "date_end")
    def _compute_track_gantt_information(self) -> None:
        for event in self:
            first_date = (
                min(
                    [event.date_begin]
                    + [track.date for track in event.track_ids if track.date]
                )
                if event.date_begin
                else None
            )
            last_date = (
                max(
                    [event.date_end]
                    + [track.date_end for track in event.track_ids if track.date_end]
                )
                if event.date_end
                else None
            )

            if first_date and last_date:
                duration = last_date - first_date
                if duration / datetime.timedelta(days=30) > 1:
                    event.track_gantt_scale = "year"
                elif duration / datetime.timedelta(weeks=1) > 1:
                    event.track_gantt_scale = "month"
                elif duration / datetime.timedelta(days=1) > 1:
                    event.track_gantt_scale = "week"
                else:
                    event.track_gantt_scale = "day"

                event.track_gantt_initial_date = first_date
                _debug.logic(
                    "gantt_scale",
                    event=event,
                    scale=event.track_gantt_scale,
                    first_date=first_date,
                    days=duration.days,
                    tracks=len(event.track_ids),
                )
            else:
                _debug.logic(
                    "gantt_scale_undefined",
                    event=event,
                    has_begin=bool(event.date_begin),
                    has_end=bool(event.date_end),
                )
                event.track_gantt_scale = False
                event.track_gantt_initial_date = False
