from odoo import fields, models


class WizardQualityCheckDecide(models.TransientModel):
    _inherit = "wizard.quality.check.decide"

    ip = fields.Char(related="current_check_id.ip")
    identifier = fields.Char(related="current_check_id.identifier")
    iot_box_id = fields.Many2one(
        related="current_check_id.iot_box_id",
        store=False,
    )
