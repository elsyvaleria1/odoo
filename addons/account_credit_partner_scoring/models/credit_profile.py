from odoo import fields, models


class CreditProfile(models.Model):
    _inherit = "credit.profile"

    tier_id = fields.Many2one(
        related="partner_id.tier_id",
        string="Commercial Tier",
    )

    def _score_observe_commercial_score(self, dimension):
        self.check_singleton()
        partner = self.partner_id.commercial_partner_id
        # A tier means a measurement was taken; a customer nobody scored has
        # no commercial score to weigh, and the dimension leaves the denominator.
        return partner.score if partner.score_line_count else None
