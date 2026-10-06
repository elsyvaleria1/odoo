from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardMrpProductionProduceConsumptionMismatchLine(models.TransientModel):
    _name = "wizard.mrp.production.produce.consumption.mismatch.line"
    _description = "Line of issue consumption"

    mrp_consumption_warning_id = fields.Many2one(
        comodel_name="wizard.mrp.production.produce.consumption.mismatch",
        string="Parent Wizard",
        readonly=True,
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
    consumption = fields.Selection(related="mrp_production_id.consumption")

    product_id = fields.Many2one(
        comodel_name="product.product",
        readonly=True,
        required=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        related="product_id.uom_id",
        string="Unit",
        readonly=True,
    )
    product_consumed_qty_uom = fields.Float(
        string="Consumed",
        readonly=True,
    )
    product_expected_qty_uom = fields.Float(
        string="To Consume",
        readonly=True,
    )
