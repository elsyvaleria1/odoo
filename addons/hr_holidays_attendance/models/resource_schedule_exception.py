from datetime import timedelta

from odoo import api, models
from odoo.fields import Domain


class ResourceScheduleException(models.Model):
    _inherit = "resource.schedule.exception"

    @api.model
    def _on_schedule_changed(self, scopes) -> None:
        super()._on_schedule_changed(scopes)
        windows = {
            (
                scope["resource_id"],
                scope["company_id"],
                scope["calendar_id"],
                scope["date_from"].date() - timedelta(days=1),
                scope["date_to"].date() + timedelta(days=1),
            )
            for scope in scopes
        }
        if not windows:
            return
        attendances = (
            self.env["hr.attendance"]
            .sudo()
            .search(
                Domain.OR(
                    (
                        Domain("employee_id.resource_id", "=", resource_id)
                        if resource_id
                        else Domain("employee_id.company_id", "=", company_id)
                        if company_id or not calendar_id
                        else Domain(
                            "employee_id.resource_calendar_id", "=", calendar_id
                        )
                    )
                    & Domain("date", ">=", date_from)
                    & Domain("date", "<=", date_to)
                    for resource_id, company_id, calendar_id, date_from, date_to in windows
                )
            )
        )
        if attendances:
            attendances._update_overtime()
