from odoo import fields, models


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["mixin.order.agreement", "sale.order"]

    agreement_id = fields.Many2one(
        comodel_name="sale.agreement",
        string="Agreement",
        index="btree_not_null",
        copy=False,
        domain="[('state', '=', 'confirmed'), '|', ('partner_id', '=', False), ('partner_id.commercial_partner_id', '=', commercial_partner_id), ('company_id', '=', company_id)]",
        check_company=True,
    )
    agreement_type = fields.Selection(related="agreement_id.agreement_type")
