from odoo import fields, models


class PaymentToken(models.Model):
    _inherit = "payment.token"

    mercado_pago_customer_id = fields.Char(readonly=True)
