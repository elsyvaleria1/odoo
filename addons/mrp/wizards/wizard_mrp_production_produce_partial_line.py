from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardMrpProductionProducePartialLine(models.TransientModel):
    _name = "wizard.mrp.production.produce.partial.line"
    _description = "Backorder Confirmation Line"

    mrp_production_backorder_id = fields.Many2one(
        comodel_name="wizard.mrp.production.produce.partial",
        string="MO Backorder",
        required=True,
        ondelete="cascade",
    )
    mrp_production_id = fields.Many2one(
        comodel_name="mrp.production",
        string="Manufacturing Order",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    to_backorder = fields.Boolean()
