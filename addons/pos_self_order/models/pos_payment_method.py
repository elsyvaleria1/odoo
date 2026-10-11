from odoo import api, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _payment_request_from_kiosk(self, order):
        pass

    @api.model
    def _load_pos_self_data_domain(self, data, config):
        return [("id", "=", False)]
