from odoo import api, models
from odoo.libs.intervals import Intervals


class ResourceCalendar(models.Model):
    _inherit = "resource.calendar"

    @api.depends("attendance_ids.work_entry_type_id.is_leave")
    def _compute_hours_per_week(self) -> None:
        super()._compute_hours_per_week()

    def _get_global_attendances(self):
        return (
            super()
            ._get_global_attendances()
            .filtered(lambda a: not a.work_entry_type_id.is_leave)
        )

    def _work_intervals_batch(
        self,
        start_dt,
        end_dt,
        resources=None,
        domain=None,
        tz=None,
        compute_leaves=True,
        exclude_bookings=False,
    ):
        intervals_per_resource = super()._work_intervals_batch(
            start_dt,
            end_dt,
            resources=resources,
            domain=domain,
            tz=tz,
            compute_leaves=compute_leaves,
            exclude_bookings=exclude_bookings,
        )
        attendances = self.env["resource.calendar.attendance"].union(
            *(
                interval[2]
                for intervals in intervals_per_resource.values()
                for interval in intervals
            )
        )
        leave_ids = set(attendances.sudo().filtered("work_entry_type_id.is_leave").ids)
        return {
            resource_id: Intervals(
                [
                    interval
                    for interval in intervals
                    if leave_ids.isdisjoint(interval[2].ids)
                ],
                keep_distinct=True,
            )
            for resource_id, intervals in intervals_per_resource.items()
        }
