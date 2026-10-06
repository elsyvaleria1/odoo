from odoo import fields, models


class WizardProjectTaskValidateRunningTimer(models.TransientModel):
    _name = "wizard.project.task.validate.running.timer"
    _description = "Task stop running timers confirmation wizard"

    line_ids = fields.One2many(
        comodel_name="wizard.project.task.validate.running.timer.line",
        inverse_name="wizard_id",
        required=True,
    )

    def action_confirm(self):
        self.line_ids.task_id.action_fsm_validate(stop_running_timers=True)
