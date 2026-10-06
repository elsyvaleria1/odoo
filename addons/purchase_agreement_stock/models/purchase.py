from odoo import api, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    @api.onchange("agreement_id")
    def _onchange_agreement_id(self) -> None:
        super()._onchange_agreement_id()
        if self.agreement_id:
            self.picking_type_id = self.agreement_id.picking_type_id.id
