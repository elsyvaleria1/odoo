from odoo import fields, models


class ScorecardDimension(models.Model):
    _inherit = "scorecard.dimension"

    code = fields.Selection(
        selection_add=[("commercial_score", "Commercial score of the customer")],
        ondelete={"commercial_score": "cascade"},
    )
