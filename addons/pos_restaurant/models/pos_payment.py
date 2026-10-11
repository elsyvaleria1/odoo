from odoo import models


class PosPayment(models.Model):
    _inherit = "pos.payment"

    def _update_payment_line_for_tip(self, tip_amount):
        self.check_singleton()
        self.write(
            {
                "amount": self.amount + tip_amount,
            }
        )
