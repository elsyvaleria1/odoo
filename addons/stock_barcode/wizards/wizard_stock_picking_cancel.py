from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardStockPickingCancel(models.TransientModel):
    _name = "wizard.stock.picking.cancel"
    _description = "Cancel Operation"

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Transfer",
        readonly=True,
    )
    picking_name = fields.Char(
        related="picking_id.display_name",
        string="Transfer Name",
        readonly=True,
    )

    def action_cancel_operation(self) -> dict:
        _debug.lifecycle("barcode_operation_cancel", wizards=self)
        res = self.picking_id.action_cancel()
        return {"type": "ir.actions.act_window_close", "infos": {"cancelled": res}}
