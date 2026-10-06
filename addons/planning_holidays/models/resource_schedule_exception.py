from datetime import date, datetime, time

from odoo import api, models
from odoo.fields import Domain


class ResourceScheduleException(models.Model):
    _inherit = "resource.schedule.exception"

    @api.model
    def _get_domain_shifts_for_scopes(self, scopes):
        if not scopes:
            return Domain.FALSE
        global_leave_start_date = leave_start_date = datetime.combine(
            date.today(), time.max
        )
        global_leave_end_date = leave_end_date = datetime.combine(
            date(1970, 1, 1), time.min
        )
        resource_ids = set()
        for scope in scopes:
            if scope["resource_id"]:
                leave_start_date = min(leave_start_date, scope["date_from"])
                leave_end_date = max(leave_end_date, scope["date_to"])
                resource_ids.add(scope["resource_id"])
                continue
            global_leave_start_date = min(global_leave_start_date, scope["date_from"])
            global_leave_end_date = max(global_leave_end_date, scope["date_to"])
        domain = [
            ("start_datetime", "<", global_leave_end_date),
            ("end_datetime", ">", global_leave_start_date),
            ("resource_type", "=", "human"),
            ("resource_id", "!=", False),
        ]
        if resource_ids:
            domain = Domain.OR(
                [
                    [
                        ("start_datetime", "<", leave_end_date),
                        ("end_datetime", ">", leave_start_date),
                        ("resource_id", "in", list(resource_ids)),
                    ],
                    domain,
                ]
            )
        return domain

    def _recompute_shifts_in_leave_periods(self, domain=None) -> None:
        if domain is None:
            domain = self._get_domain_shifts_for_scopes(self._get_schedule_scopes())
        shifts = self.env["planning.slot"].search(domain)
        self.env.add_to_compute(
            self.env["planning.slot"]._fields.get("allocated_hours"), shifts
        )

    @api.model
    def _on_schedule_changed(self, scopes) -> None:
        super()._on_schedule_changed(scopes)
        if scopes:
            self._recompute_shifts_in_leave_periods(
                self._get_domain_shifts_for_scopes(scopes)
            )
