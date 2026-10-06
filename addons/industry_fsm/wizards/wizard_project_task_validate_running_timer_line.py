from odoo import fields, models


class WizardProjectTaskValidateRunningTimerLine(models.TransientModel):
    _name = "wizard.project.task.validate.running.timer.line"
    _description = "Task stop running timers confirmation wizard line"

    wizard_id = fields.Many2one(
        comodel_name="wizard.project.task.validate.running.timer"
    )
    task_id = fields.Many2one(
        comodel_name="project.task",
        required=True,
    )
