from odoo import fields, models

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class PaymentToken(models.Model):
    _inherit = "payment.token"

    authorize_profile = fields.Char(
        string="Authorize.Net Profile ID",
        help="The unique reference for the partner/token combination in the Authorize.net backend.",
    )
