import logging

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

_logger = logging.getLogger("odoo.addons.base.partner.merge")

SIMILAR_NAME_PAIR_BATCH = 5000


class WizardResPartnerMergeLine(models.TransientModel):
    _name = "wizard.res.partner.merge.line"

    _description = "Merge Partner Line"
    _order = "min_id asc"

    wizard_id = fields.Many2one(comodel_name="wizard.res.partner.merge")
    min_id = fields.Integer(string="MinID")
    aggr_ids = fields.Char(
        string="Ids",
        required=True,
    )
