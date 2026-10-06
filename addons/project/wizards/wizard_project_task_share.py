from odoo import fields, models


class WizardProjectTaskShare(models.TransientModel):
    _name = "wizard.project.task.share"
    _inherit = ["wizard.mail.message.send.portal.link"]
    _description = "Task Sharing"

    task_id = fields.Many2one(
        comodel_name="project.task",
        default=lambda self: self.res_id,
    )
    project_privacy_visibility = fields.Selection(
        related="task_id.project_privacy_visibility"
    )
