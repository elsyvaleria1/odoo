from odoo import fields, models


class QualityCheck(models.Model):
    _inherit = "quality.check"

    batch_id = fields.Many2one(related="picking_id.batch_id")
