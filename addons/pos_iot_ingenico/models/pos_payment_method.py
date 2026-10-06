from odoo import models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _selection_payment_terminals(self):
        return super()._selection_payment_terminals() + [("ingenico", "Ingenico")]
