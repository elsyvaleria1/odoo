from datetime import datetime, timedelta

from odoo import api, models
from odoo.libs.datetime import timezone, wall_to_utc
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResourceScheduleException(models.Model):
    _inherit = "resource.schedule.exception"

    @api.depends("date_from")
    def _compute_calendar_id(self) -> None:
        def date_to_datetime(date, tz):
            dt = datetime.fromordinal(date.toordinal())
            return wall_to_utc(dt, tz)

        leaves_by_contract = self.grouped(
            lambda leave: leave.resource_id.employee_id[:1].version_id
        )
        remaining = leaves_by_contract.pop(
            self.env["hr.version"],
            self.env["resource.schedule.exception"],
        )
        _debug.logic(
            "calendar_computed",
            exceptions=self,
            contract_groups=len(leaves_by_contract),
            without_contract=remaining,
        )
        for contract, leaves in leaves_by_contract.items():
            tz = timezone(
                contract.employee_id.tz or contract.resource_calendar_id.tz or "UTC"
            )
            start_dt = date_to_datetime(contract.date_start, tz)
            end_dt = (
                date_to_datetime(contract.date_end + timedelta(days=1), tz)
                if contract.date_end
                else datetime.max  # noqa: DTZ901 -- Odoo stores UTC datetimes without tzinfo; this is a naive bound.
            )
            in_contract = leaves.filtered_domain(
                [("date_from", ">=", start_dt), ("date_from", "<", end_dt)]
            )
            _debug.logic(
                "calendar_from_version",
                version=contract.id,
                in_contract=in_contract,
                leaves=leaves,
                start=start_dt,
                stop=end_dt,
                calendar=contract.resource_calendar_id.id,
            )
            in_contract.calendar_id = contract.resource_calendar_id

        super(ResourceScheduleException, remaining)._compute_calendar_id()
