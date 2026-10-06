from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardMrpProductionSplitLine(models.TransientModel):
    _name = "wizard.mrp.production.split.line"
    _description = "Split Production Detail"

    mrp_production_split_id = fields.Many2one(
        comodel_name="wizard.mrp.production.split",
        string="Split Production",
        required=True,
        ondelete="cascade",
    )
    quantity = fields.Float(
        string="Quantity To Produce",
        digits="Product Unit",
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        domain=lambda self: [
            ("all_group_ids", "in", self.env.ref("mrp.group_mrp_user").id)
        ],
    )
    date = fields.Datetime(string="Schedule Date")
