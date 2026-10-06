from odoo import api, fields, models


class WizardHelpdeskTicketCreateFsmTask(models.TransientModel):
    _inherit = "wizard.helpdesk.ticket.create.fsm.task"

    allow_worksheets = fields.Boolean(related="project_id.allow_worksheets")
    worksheet_template_id = fields.Many2one(
        comodel_name="worksheet.template",
        export_string_translation=False,
        compute="_compute_worksheet_template_id",
        store=True,
        readonly=False,
        domain="[('res_model', '=', 'project.task')]",
    )

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        project_id = defaults.get("project_id")
        if project_id:
            project = self.env["project.project"].browse(project_id)
            defaults["worksheet_template_id"] = project.worksheet_template_id.id
        return defaults

    def _generate_task_values(self):
        values = super()._generate_task_values()
        if self.allow_worksheets:
            values.update({"worksheet_template_id": self.worksheet_template_id.id})
        return values

    @api.depends("project_id")
    def _compute_worksheet_template_id(self) -> None:
        with_projects = self.filtered("project_id")
        (self - with_projects).worksheet_template_id = False
        for wizard in with_projects:
            wizard.worksheet_template_id = wizard.project_id.worksheet_template_id
