from odoo import fields, models


class WizardSaleOrderMarkLost(models.TransientModel):
    _name = "wizard.sale.order.mark.lost"
    _inherit = "mixin.order.loss"
    _description = "Mark quotations as lost"

    order_ids = fields.Many2many(
        comodel_name="sale.order",
        relation="sale_order_loss_wizard_rel",
        string="Quotations",
        default=lambda self: self.env.context.get("active_ids"),
    )
