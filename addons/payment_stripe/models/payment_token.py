from odoo import fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class PaymentToken(models.Model):
    _inherit = "payment.token"

    stripe_payment_method = fields.Char(
        string="Stripe Payment Method ID",
        readonly=True,
    )
    stripe_mandate = fields.Char(readonly=True)

    def _stripe_sca_migrate_customer(self) -> None:
        self.check_singleton()

        response_content = self.provider_id._send_api_request(
            "GET",
            "payment_methods",
            data={
                "customer": self.provider_ref,
                "type": "card",
                "limit": 1,
            },
        )

        payment_methods = response_content.get("data", [])
        payment_method_id = payment_methods and payment_methods[0].get("id")
        if not payment_method_id:
            raise ValidationError(
                self.env._("Unable to convert payment token to new API.")
            )
        self.stripe_payment_method = payment_method_id
        _logger.info("converted token with id %s to new API", self.id)
