from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardStockPickingValidatePartialLine(models.TransientModel):
    _name = "wizard.stock.picking.validate.partial.line"
    _description = "Backorder Confirmation Line"

    backorder_confirmation_id = fields.Many2one(
        comodel_name="wizard.stock.picking.validate.partial"
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Transfer",
    )
    to_backorder = fields.Boolean()
