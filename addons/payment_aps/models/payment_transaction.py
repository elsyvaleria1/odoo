from odoo import api, models
from odoo.http import request
from odoo.tools import consteq, urls

from odoo.addons.integration.tools.admission import Acknowledged
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_aps import utils as aps_utils
from odoo.addons.payment_aps.const import PAYMENT_STATUS_MAPPING
from odoo.addons.payment_aps.controllers.main import APSController

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model
    def _receiver_for_aps_return(self, **path_args):
        return self._resolve_notification(
            "aps", request.get_http_params(), Acknowledged.redirect("/payment/status")
        )

    @api.model
    def _receiver_for_aps_webhook(self, **path_args):
        return self._resolve_notification(
            "aps", request.get_http_params(), Acknowledged("")
        )

    def _is_notification_signature_valid(self, payment_data) -> bool:
        if self.provider_code != "aps":
            return super()._is_notification_signature_valid(payment_data)
        received_signature = payment_data.get("signature")
        if not received_signature:
            _logger.warning("Received payment data with missing signature.")
            return False
        expected_signature = self.provider_id._get_aps_signature(
            payment_data, incoming=True
        )
        if not consteq(received_signature, expected_signature):
            _logger.warning("Received payment data with invalid signature.")
            return False
        return True

    @api.model
    def _get_unique_reference(
        self,
        provider_code,
        prefix=None,
        separator="-",
        references_in_use: set[str] | None = None,
        **kwargs,
    ) -> str:
        if provider_code == "aps":
            prefix = payment_utils.singularize_reference_prefix()

        return super()._get_unique_reference(
            provider_code,
            prefix=prefix,
            separator=separator,
            references_in_use=references_in_use,
            **kwargs,
        )

    def _prepare_redirect_form_values(self, processing_values):
        if self.provider_code != "aps":
            return super()._prepare_redirect_form_values(processing_values)

        converted_amount = payment_utils.major_to_minor_currency_units(
            self.amount, self.currency_id
        )
        base_url = self.provider_id.get_base_url()
        payment_option = aps_utils.get_payment_option(self.payment_method_id.code)
        rendering_values = {
            "command": "PURCHASE",
            "access_code": self.provider_id.aps_access_code,
            "merchant_identifier": self.provider_id.aps_merchant_identifier,
            "merchant_reference": self.reference,
            "amount": str(converted_amount),
            "currency": self.currency_id.name,
            "language": self.partner_lang[:2],
            "customer_email": self.partner_id.email_normalized,
            "return_url": urls.urljoin(base_url, APSController._return_url),
        }
        if payment_option:
            rendering_values["payment_option"] = payment_option
        rendering_values.update(
            {
                "signature": self.provider_id._get_aps_signature(
                    rendering_values, incoming=False
                ),
                "api_url": self.provider_id._aps_get_api_url(),
            }
        )
        return rendering_values

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code != "aps":
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get("merchant_reference")

    def _extract_amount_data(self, payment_data) -> dict | None:
        if self.provider_code != "aps":
            return super()._extract_amount_data(payment_data)

        amount = payment_utils.minor_to_major_currency_units(
            float(payment_data.get("amount", 0)), self.currency_id
        )
        return {
            "amount": amount,
            "currency_code": payment_data.get("currency"),
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != "aps":
            return super()._apply_updates(payment_data)

        self.provider_reference = payment_data.get("fort_id")

        payment_option = payment_data.get("payment_option", "")
        payment_method = self.env["payment.method"]._get_from_code(
            payment_option.lower()
        )
        self.payment_method_id = payment_method or self.payment_method_id

        status = payment_data.get("status")
        if not status:
            self._set_error(self.env._("Received data with missing payment state."))
        elif status in PAYMENT_STATUS_MAPPING["pending"]:
            self._set_pending()
        elif status in PAYMENT_STATUS_MAPPING["done"]:
            self._set_done()
        else:
            status_description = payment_data.get("response_message")
            _logger.info(
                "Received data with invalid payment status (%(status)s) and reason '%(reason)s' "
                "for transaction %(ref)s.",
                {"status": status, "reason": status_description, "ref": self.reference},
            )
            self._set_error(
                self.env._(
                    "Received invalid transaction status %(status)s and reason '%(reason)s'.",
                    status=status,
                    reason=status_description,
                )
            )
        return None
