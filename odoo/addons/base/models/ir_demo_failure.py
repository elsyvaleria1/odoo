from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class IrDemo_Failure(models.TransientModel):
    _name = "ir.demo_failure"
    _description = "Demo failure"

    module_id = fields.Many2one(
        comodel_name="ir.module.module",
        required=True,
    )
    error = fields.Text()
    wizard_id = fields.Many2one(
        comodel_name="wizard.ir.module.module.view.demo.failure"
    )
