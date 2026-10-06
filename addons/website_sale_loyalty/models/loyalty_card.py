from odoo import models


class LoyaltyCard(models.Model):
    _inherit = "loyalty.card"

    def action_coupon_share(self):
        self.check_singleton()
        return self.env["wizard.loyalty.program.share"].create_share_action(coupon=self)
