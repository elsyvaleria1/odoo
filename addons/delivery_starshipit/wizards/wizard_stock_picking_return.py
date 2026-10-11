from odoo import models


class WizardStockPickingReturn(models.TransientModel):
    _inherit = "wizard.stock.picking.return"

    def _reset_carrier_id(self, picking) -> None:
        if (
            picking.carrier_id.delivery_type != "starshipit"
            or not picking.carrier_id.can_generate_return
        ):
            super()._reset_carrier_id(picking)
