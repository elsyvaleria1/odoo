from odoo import models


class WizardStockPickingReturn(models.TransientModel):
    _inherit = "wizard.stock.picking.return"

    def _prepare_picking_default_values(self):
        vals = super()._prepare_picking_default_values()
        if all(
            return_line.quantity > 0 and return_line.move_id.is_subcontract
            for return_line in self.product_return_moves
        ):
            vals["location_dest_id"] = self.picking_id.partner_id.with_company(
                self.picking_id.company_id
            ).property_stock_subcontractor.id
        return vals
