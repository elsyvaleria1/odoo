import logging

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

_logger = logging.getLogger("odoo.addons.product.merge")


class WizardProductTemplateMergeLine(models.TransientModel):
    _name = "wizard.product.template.merge.line"
    _description = "Merge Product Line"
    _order = "min_id asc"

    wizard_id = fields.Many2one(comodel_name="wizard.product.template.merge")
    min_id = fields.Integer(string="MinID")
    aggr_ids = fields.Json(
        string="Ids",
        required=True,
    )
