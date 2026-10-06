from datetime import UTC

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class WizardPlanningPlanningPreview(models.TransientModel):
    _name = "wizard.planning.planning.preview"
    _description = "Planning Preview"

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
    )
    slot_count = fields.Integer(compute="_compute_slot_count")

    def _get_datetimes(self) -> tuple:
        start_str = self.env.context.get("default_start_datetime")
        end_str = self.env.context.get("default_end_datetime")

        if not start_str or not end_str:
            raise ValidationError(
                self.env._("Missing start or end datetime in context.")
            )
        return start_str, end_str

    @api.depends("employee_id")
    def _compute_slot_count(self) -> None:
        for record in self:
            employee = record.employee_id
            if not employee:
                record.slot_count = 0
                continue

            # Get start and end datetimes
            start_str, end_str = record._get_datetimes()
            # Search all relevant slots within timeframe
            employee = record.employee_id
            planning_roles = employee.planning_role_ids

            open_shift_domain = Domain(
                [
                    ("resource_id", "=", False),
                    ("end_datetime", ">=", fields.Datetime.now()),
                ]
            )

            # Role filtering: if employee has roles, restrict to those; else, no restriction
            if planning_roles:
                role_domain = Domain(
                    [
                        "|",
                        ("role_id", "in", planning_roles.ids),
                        ("role_id", "=", False),
                    ]
                )
            else:
                role_domain = Domain.TRUE

            open_shift_domain &= role_domain
            request_to_switch_domain = (
                Domain("request_to_switch", "=", True) & role_domain
            )

            domain = Domain(
                [
                    ("state", "in", self.env["planning.slot"]._get_scheduled_states()),
                    ("start_datetime", ">", start_str),
                    ("end_datetime", "<", end_str),
                ]
            )
            domain &= (
                Domain("employee_id", "=", employee.id)
                | open_shift_domain
                | request_to_switch_domain
            )

            slots = self.env["planning.slot"].search(domain)

            # Apply attendance filtering if employee is not flexible
            if employee.resource_calendar_id.schedule_type == "fully_fixed":
                start = fields.Datetime.from_string(start_str).replace(tzinfo=UTC)
                end = fields.Datetime.from_string(end_str).replace(tzinfo=UTC)
                resource_work_intervals, _ = (
                    employee.resource_id._get_valid_work_intervals(start, end)
                )
                attendance_intervals = resource_work_intervals.get(
                    employee.resource_id.id, []
                )
                slots = slots._filtered_assigned_or_during(attendance_intervals._items)
            record.slot_count = len(slots)

    def action_preview_shift(self) -> dict:
        self.check_singleton()
        default_start_str, default_end_str = self._get_datetimes()

        default_start = fields.Datetime.to_datetime(default_start_str)
        default_end = fields.Datetime.to_datetime(default_end_str)
        planning = self.env["planning.planning"]._get_or_create_preview_planning(
            default_start, default_end, True
        )
        planning.is_planning_preview = True
        planning_url = "/planning/%s/%s" % (
            planning._page_token(self.employee_id.resource_id),
            self.employee_id.sudo().employee_token,
        )

        return {
            "type": "ir.actions.act_url",
            "url": planning_url,
            "target": "new",
        }
