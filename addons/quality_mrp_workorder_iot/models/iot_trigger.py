from odoo import fields, models


class IotTrigger(models.Model):
    _inherit = "iot.trigger"

    action = fields.Selection(
        selection_add=[("pass", "Pass"), ("fail", "Fail"), ("measure", "Take Measure")]
    )
