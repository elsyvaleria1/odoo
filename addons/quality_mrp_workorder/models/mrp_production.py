from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    check_ids = fields.One2many(
        comodel_name="quality.check",
        domain=[("workorder_id", "=", False)],
    )
