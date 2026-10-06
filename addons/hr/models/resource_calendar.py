from odoo import fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResourceCalendar(models.Model):
    _inherit = "resource.calendar"

    def _transfer_leaves_to_calendar(
        self, other_calendar, resources=None, from_date=None
    ) -> None:
        from_date = from_date or fields.Datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        domain = [
            ("calendar_id", "in", self.ids),
            ("date_from", ">=", from_date),
        ]
        domain = (
            Domain.AND([domain, [("resource_id", "in", resources.ids)]])
            if resources
            else domain
        )

        leaves = self.env["resource.schedule.exception"].search(domain)
        _debug.pipeline(
            "leaves_moved",
            calendars=self,
            to_calendar=other_calendar.id,
            leaves=leaves,
            from_date=from_date,
            resources=resources or "all",
        )
        leaves.write(
            {
                "calendar_id": other_calendar.id,
            }
        )
