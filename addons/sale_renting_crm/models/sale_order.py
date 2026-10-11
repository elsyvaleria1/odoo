from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    opportunity_id = fields.Many2one(
        comodel_name="crm.lead",
        domain="[('type', '=', 'opportunity'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
    )
