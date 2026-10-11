from odoo import models


class WizardStockPickingReturnLine(models.TransientModel):
    _inherit = "wizard.stock.picking.return.line"

    def _prepare_move_default_values(self, new_picking):
        vals = super()._prepare_move_default_values(new_picking)
        location_dest = self.env["stock.location"].browse(vals["location_dest_id"])
        if location_dest.usage == "supplier":
            purchase_line_id, partner_id = (
                self.move_id._get_purchase_line_and_partner_from_chain()
            )
            if purchase_line_id:
                vals["purchase_line_id"] = purchase_line_id
                vals["partner_id"] = partner_id
        return vals
