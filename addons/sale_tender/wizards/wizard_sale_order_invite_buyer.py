from odoo import fields, models


class WizardSaleOrderInviteBuyer(models.TransientModel):
    _name = "wizard.sale.order.invite.buyer"
    _inherit = ["mixin.tender.invite"]
    _description = "Invite buyers to a sale tender"

    origin_order_id = fields.Many2one(comodel_name="sale.order")
    tender_id = fields.Many2one(comodel_name="sale.tender")
    partner_ids = fields.Many2many(
        string="Buyers",
        help="The buyers to invite: each receives a quotation to bid on.",
    )
