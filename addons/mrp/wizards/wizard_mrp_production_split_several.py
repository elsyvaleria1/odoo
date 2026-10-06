from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardMrpProductionSplitSeveral(models.TransientModel):
    _name = "wizard.mrp.production.split.several"
    _description = "Wizard to Split Multiple Productions"

    production_ids = fields.One2many(
        comodel_name="wizard.mrp.production.split",
        inverse_name="production_split_multi_id",
        string="Productions To Split",
    )
