from odoo import fields, models


class CreditReview(models.Model):
    _inherit = "credit.review"

    tier_id = fields.Many2one(
        related="profile_id.tier_id",
        string="Commercial Tier",
    )
