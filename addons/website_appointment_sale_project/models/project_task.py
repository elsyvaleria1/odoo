from odoo import fields, models


class ProjectTask(models.Model):
    _name = "project.task"
    _inherit = "project.task"

    calendar_event_id = fields.Many2one(
        comodel_name="calendar.event",
        copy=False,
        help="Linked appointment of this task",
    )

    def action_view_appointment(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Appointment"),
            "res_model": "calendar.event",
            "res_id": self.calendar_event_id.id,
            "view_mode": "form",
            "view_id": self.env.ref("calendar.view_calendar_event_form").id,
            "target": "current",
            "context": {"create": False},
        }
