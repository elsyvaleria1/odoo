from odoo import models


class WizardStockPickingReturnLine(models.TransientModel):
    _inherit = "wizard.stock.picking.return.line"

    def _prepare_move_default_values(self, new_picking):
        vals = super()._prepare_move_default_values(new_picking)
        if self.move_id.is_subcontract and new_picking.picking_type_code == "outgoing":
            vals["location_dest_id"] = new_picking.partner_id.with_company(
                new_picking.company_id
            ).property_stock_subcontractor.id
        vals["is_subcontract"] = False
        return vals
