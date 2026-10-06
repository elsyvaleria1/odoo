from odoo import fields, models


class MaintenancePlan(models.Model):
    _inherit = "maintenance.plan"

    worksheet_template_id = fields.Many2one(
        comodel_name="worksheet.template",
        domain="[('res_model', '=', 'maintenance.order'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="The worksheet each order of this plan is filled in on.",
    )

    def _prepare_order_vals(self, occurrence, previous=None):
        vals = super()._prepare_order_vals(occurrence, previous)
        if self.worksheet_template_id:
            vals["worksheet_template_id"] = self.worksheet_template_id.id
        return vals
