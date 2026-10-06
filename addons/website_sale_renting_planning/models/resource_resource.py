from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import models
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals

_debug = DebugLog(__name__)


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    def _unavailable_intervals_by_resource(self, start_utc, end_utc):
        closed_days_per_calendar = defaultdict(Intervals)
        date = start_utc + relativedelta(hour=0, minute=0, second=0, microsecond=0)
        while date < end_utc + relativedelta(days=1):
            for calendar in self.calendar_id:
                if not calendar._is_working_day(date):
                    day_end = date + relativedelta(days=1)
                    closed_days_per_calendar[calendar.id] |= Intervals(
                        [(date, day_end, calendar)]
                    )
            date += relativedelta(days=1)

        unavailable_per_resource_id = defaultdict(list)
        for calendar, workers in self.grouped("calendar_id").items():
            leaves_per_resource_id = calendar.sudo()._leave_intervals_batch(
                start_utc, end_utc, workers
            )
            for resource_id, leaves in leaves_per_resource_id.items():
                if not resource_id:
                    continue
                unavailable_per_resource_id[resource_id] = (
                    leaves | closed_days_per_calendar[calendar.id]
                )
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "unavailable_intervals",
                resources=self,
                calendars=self.calendar_id,
                closed_calendars=sum(
                    1 for days in closed_days_per_calendar.values() if days
                ),
                resources_keyed=len(unavailable_per_resource_id),
                resources_unavailable=sum(
                    1 for intervals in unavailable_per_resource_id.values() if intervals
                ),
            )
        return unavailable_per_resource_id
