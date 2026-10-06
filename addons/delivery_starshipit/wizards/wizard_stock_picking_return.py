from odoo import models


class WizardStockPickingReturn(models.TransientModel):
    _inherit = "wizard.stock.picking.return"

    def _reset_carrier_id(self, picking) -> None:
        """For starshipit, we want to keep the provider when generating a return."""
        if (
            picking.carrier_id.delivery_type != "starshipit"
            or not picking.carrier_id.can_generate_return
        ):
            super()._reset_carrier_id(picking)
