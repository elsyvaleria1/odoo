from odoo import fields, models


class WizardHrLeaveCancel(models.TransientModel):
    _name = "wizard.hr.leave.cancel"
    _description = "Cancel Time Off Wizard"

    leave_id = fields.Many2one(
        comodel_name="hr.leave",
        string="Time Off Request",
        required=True,
    )
    reason = fields.Text()

    def action_cancel_leave(self) -> dict:
        self.check_singleton()

        self.leave_id._action_user_cancel(self.reason)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Your time off has been cancelled."),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
