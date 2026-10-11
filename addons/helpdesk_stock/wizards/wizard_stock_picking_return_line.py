from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardStockPickingReturnLine(models.TransientModel):
    _inherit = "wizard.stock.picking.return.line"

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        related="wizard_id.picking_id",
        export_string_translation=False,
    )
