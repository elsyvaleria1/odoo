from odoo import models


class WizardStockPickingReturn(models.TransientModel):
    _inherit = "wizard.stock.picking.return"

    def _create_return(self):
        picking = super()._create_return()
        if (
            len(picking.move_ids.partner_id) == 1
            and picking.partner_id != picking.move_ids.partner_id
        ):
            picking.partner_id = picking.move_ids.partner_id
        return picking
