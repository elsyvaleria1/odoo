from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    is_delivery_payment = fields.Boolean(
        string="Delivery Payment",
        help="Check this if this payment method is used for online delivery orders.",
    )
    delivery_provider_id = fields.Many2one(
        comodel_name="pos.delivery.provider",
        help="Responsible delivery provider for online order, e.g., UberEats, Zomato.",
    )
