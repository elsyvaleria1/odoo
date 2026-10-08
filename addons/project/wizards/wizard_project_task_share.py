from odoo import api, fields, models


class WizardProjectTaskShare(models.TransientModel):
    _name = "wizard.project.task.share"
    _inherit = ["wizard.mail.message.send.portal.link"]
    _description = "Task Sharing"

    task_id = fields.Many2one(
        comodel_name="project.task",
        compute="_compute_task_id",
    )
    project_privacy_visibility = fields.Selection(
        related="task_id.project_privacy_visibility"
    )

    @api.depends("res_model", "res_id")
    def _compute_task_id(self) -> None:
        for wizard in self:
            wizard.task_id = (
                wizard.res_id if wizard.res_model == "project.task" else False
            )
