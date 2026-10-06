import logging

from odoo import fields, models, modules, tools
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

_logger = logging.getLogger("odoo.addons.product.merge")


def _can_commit() -> bool:
    return not (tools.config["test_enable"] or modules.module.current_test)


class WizardProductTemplateMergeLine(models.TransientModel):
    _name = "wizard.product.template.merge.line"
    _description = "Merge Product Line"
    _order = "min_id asc"

    wizard_id = fields.Many2one(comodel_name="wizard.product.template.merge")
    min_id = fields.Integer(string="MinID")
    aggr_ids = fields.Char(
        string="Ids",
        required=True,
    )
