from odoo import api, fields, models


class PlanningSlotTemplate(models.Model):
    _inherit = "planning.slot.template"

    project_id = fields.Many2one(
        comodel_name="project.project",
        copy=True,
        domain=[("is_template", "=", False)],
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="project_id.company_id",
    )

    @api.depends("project_id")
    def _compute_display_name(self):
        super()._compute_display_name()
        for shift_template in self:
            if shift_template.project_id:
                name = f"{shift_template.display_name} [{shift_template.project_id.display_name[:30]}]"
            else:
                name = shift_template.display_name
            shift_template.display_name = name
