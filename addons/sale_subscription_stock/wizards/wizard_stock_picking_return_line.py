from odoo import models


class WizardStockPickingReturnLine(models.TransientModel):
    _inherit = "wizard.stock.picking.return.line"

    def _prepare_move_default_values(self, new_picking):
        vals = super()._prepare_move_default_values(new_picking)
        if self.move_id.sale_line_id.recurring_invoice:
            vals["date"] = self.move_id.date
        return vals
