from datetime import UTC

from odoo import fields, models
from odoo.libs.datetime import timezone, wall_at


class WizardResourceScheduleExceptionCreate(models.TransientModel):
    _name = "wizard.resource.schedule.exception.create"
    _description = "Add or remove leaves from appointments"

    def _default_time(self, hours):
        user_timezone = timezone(
            self.env.user.tz or self.env.context.get("tz") or "UTC"
        )
        user_time = wall_at(fields.Date.today(), hours).replace(tzinfo=user_timezone)
        return user_time.astimezone(UTC).replace(tzinfo=None)

    resource_ids = fields.Many2many(
        comodel_name="resource.resource",
        string="Resources",
        required=True,
    )
    leave_start_dt = fields.Datetime(
        string="Start Date",
        default=lambda self: self._default_time(0.0),
        required=True,
    )
    leave_end_dt = fields.Datetime(
        string="End Date",
        default=lambda self: self._default_time(24.0),
        required=True,
    )
    reason = fields.Char()

    def action_create_leave(self) -> dict:
        self.env["resource.schedule.exception"].create(
            [
                {
                    "calendar_id": resource.calendar_id.id,
                    "date_from": wizard.leave_start_dt,
                    "date_to": wizard.leave_end_dt,
                    "name": wizard.reason,
                    "resource_id": resource.id,
                }
                for wizard in self
                for resource in wizard.resource_ids
            ]
        )
        return {"type": "ir.actions.act_window_close"}
