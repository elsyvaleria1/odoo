from odoo import api, models


class WizardMrpProductionUpdateQuantity(models.TransientModel):
    _inherit = "wizard.mrp.production.update.quantity"

    @api.model
    def _is_quantity_propagation_required(self, move, qty) -> bool:
        res = super()._is_quantity_propagation_required(move, qty)
        return bool(res and not any(m.is_subcontract for m in move.move_dest_ids))
