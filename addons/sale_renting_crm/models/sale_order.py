from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # same field as sale_crm, one will possibly override the other so their definition should stay in sync
    opportunity_id = fields.Many2one(
        comodel_name="crm.lead",
        domain="[('type', '=', 'opportunity'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
    )
