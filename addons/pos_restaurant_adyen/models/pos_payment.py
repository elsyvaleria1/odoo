from odoo import models
from odoo.tools import float_round

TIMEOUT = 10


class PosPayment(models.Model):
    _inherit = "pos.payment"

    def _update_payment_line_for_tip(self, tip_amount):
        res = super()._update_payment_line_for_tip(tip_amount)
        if self.payment_method_id.use_payment_terminal == "adyen":
            self._adyen_capture()
        return res

    def _adyen_capture(self):
        data = {
            "originalReference": self.transaction_id,
            "modificationAmount": {
                "value": int(
                    float_round(
                        self.amount * 10**self.currency_id.decimal_places,
                        precision_digits=0,
                    )
                ),
                "currency": self.currency_id.name,
            },
            "merchantAccount": self.payment_method_id.adyen_merchant_account,
        }

        return self.payment_method_id.proxy_adyen_request(data, "capture")
