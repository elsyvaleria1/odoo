from odoo import models
from odoo.tools.date_utils import get_intervals_hours, localized


class MixinResourceSchedulingTools(models.AbstractModel):
    _name = "mixin.resource.scheduling.tools"
    _description = "Resource Scheduling Helpers"

    def _scheduling_get_work_hours(
        self,
        date_start,
        date_end,
        resource=None,
        calendar=None,
        compute_leaves=True,
        leave_domain=None,
    ):
        self.check_singleton()
        if not date_start or not date_end or date_end <= date_start:
            return 0.0

        start_utc = localized(date_start)
        end_utc = localized(date_end)

        if not resource:
            cal = calendar or self._scheduling_resolve_calendar()
            if cal:
                return cal.get_work_hours_count(
                    start_utc,
                    end_utc,
                    compute_leaves=compute_leaves,
                    domain=leave_domain,
                )
            return (end_utc - start_utc).total_seconds() / 3600.0

        if calendar and calendar != resource.calendar_id:
            # A flexible resource reads any schedule through its own rules, so
            # a schedule imposed on it is read whole, without the resource.
            if calendar.schedule_type != "fully_fixed" or resource._is_flexible():
                return calendar.get_work_hours_count(
                    start_utc,
                    end_utc,
                    compute_leaves=compute_leaves,
                    domain=leave_domain,
                )
            return get_intervals_hours(
                calendar._work_intervals_batch(
                    start_utc,
                    end_utc,
                    resource,
                    domain=leave_domain,
                    compute_leaves=compute_leaves,
                )[resource.id]
            )
        schedule = resource._get_work_schedule(
            start_utc,
            end_utc,
            compute_leaves=compute_leaves,
            leave_domain=leave_domain,
        )
        return schedule.work_hours(resource)

    def _scheduling_resolve_calendar(self):
        self.check_singleton()
        if "resource_calendar_id" in self._fields and self.resource_calendar_id:
            return self.resource_calendar_id
        if "company_id" in self._fields and self.company_id:
            return self.company_id.resource_calendar_id
        return self.env.company.resource_calendar_id
