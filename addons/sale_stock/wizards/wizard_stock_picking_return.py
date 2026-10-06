from odoo import models


class WizardStockPickingReturn(models.TransientModel):
    _inherit = "wizard.stock.picking.return"

    def _prepare_procurement_vals(self, line):
        sol = line.move_id.sale_line_id
        if sol:
            return sol._prepare_procurement_vals()
        return super()._prepare_procurement_vals(line)
