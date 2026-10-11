from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    allow_worksheets = fields.Boolean(
        related="project_id.allow_worksheets",
        export_string_translation=False,
        readonly=True,
    )
    worksheet_template_id = fields.Many2one(
        comodel_name="worksheet.template",
        company_dependent=True,
        domain="[('res_model', '=', 'project.task')]",
    )

    def _update_worksheet_template_id(self, keep_template=False) -> None:
        for template in self:
            if (
                not template.allow_worksheets
                or template.service_tracking
                not in ["task_global_project", "task_new_project"]
                or not template.project_id.is_fsm
            ):
                template.worksheet_template_id = False
            else:
                old_template = (
                    template.worksheet_template_id if keep_template else False
                )
                template.worksheet_template_id = (
                    old_template or template.project_id.worksheet_template_id
                )

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res.filtered(
            lambda t: not t.worksheet_template_id
        )._update_worksheet_template_id()
        return res

    def write(self, vals):
        res = super().write(vals)
        if "service_tracking" in vals or "project_id" in vals:
            self._update_worksheet_template_id(
                keep_template=("worksheet_template_id" in vals)
            )
        return res

    @api.onchange("project_id")
    def _onchange_project(self) -> None:
        if self.project_id.worksheet_template_id:
            self.worksheet_template_id = self.project_id.worksheet_template_id
