from odoo import fields, models


class WizardSaleOrderCancel(models.TransientModel):
    _name = "wizard.sale.order.cancel"
    _inherit = "mixin.order.mass.cancel"
    _description = "Cancel multiple quotations"

    order_ids = fields.Many2many(
        comodel_name="sale.order",
        relation="sale_order_mass_cancel_wizard_rel",
        string="Sale orders to cancel",
        default=lambda self: self.env.context.get("active_ids"),
    )
