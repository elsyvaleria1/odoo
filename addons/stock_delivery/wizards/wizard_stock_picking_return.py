from odoo import models


class WizardStockPickingReturn(models.TransientModel):
    _inherit = "wizard.stock.picking.return"

    def _create_return(self):
        new_picking = super()._create_return()
        self._reset_carrier_id(new_picking)
        return new_picking

    def _reset_carrier_id(self, picking) -> None:
        picking.write(
            {
                "carrier_id": False,
                "carrier_price": 0.0,
            }
        )
