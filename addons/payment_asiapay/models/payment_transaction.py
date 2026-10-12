from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools import consteq, urls

from odoo.addons.integration.tools.admission import Acknowledged
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_asiapay import const
from odoo.addons.payment_asiapay.controllers.main import AsiaPayController

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model
    def _receiver_for_asiapay_webhook(self, **path_args):
        return self._resolve_notification(
            "asiapay", request.get_http_params(), Acknowledged("OK")
        )

    def _is_notification_signature_valid(self, payment_data) -> bool:
        if self.provider_code != "asiapay":
            return super()._is_notification_signature_valid(payment_data)
        received_signature = payment_data.get("secureHash")
        if not received_signature:
            _logger.warning("Received payment data with missing signature.")
            return False
        expected_signature = self.provider_id._get_asiapay_signature(
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
        if provider_code != "asiapay":
            return super()._get_unique_reference(
                provider_code,
                prefix=prefix,
                separator=separator,
                references_in_use=references_in_use,
                **kwargs,
            )

        if not prefix:
            prefix = self.sudo()._get_reference_prefix(separator, **kwargs) or None
        prefix = payment_utils.singularize_reference_prefix(
            prefix=prefix, max_length=35
        )
        return super()._get_unique_reference(
            provider_code,
            prefix=prefix,
            separator=separator,
            references_in_use=references_in_use,
            **kwargs,
        )

    def _prepare_redirect_form_values(self, processing_values):

        def get_language_code(lang_):
            language_code_ = const.LANGUAGE_CODES_MAPPING.get(lang_)
            if not language_code_:
                country_code_ = lang_.split("_")[0]
                language_code_ = const.LANGUAGE_CODES_MAPPING.get(country_code_)
            if not language_code_:
                language_code_ = const.LANGUAGE_CODES_MAPPING["en"]
            return language_code_

        if self.provider_code != "asiapay":
            return super()._prepare_redirect_form_values(processing_values)

        base_url = self.provider_id.get_base_url()
        lang = self.env.context.get("lang") or "en_US"
        rendering_values = {
            "merchant_id": self.provider_id.asiapay_merchant_id,
            "amount": self.amount,
            "reference": self.reference,
            "currency_code": const.CURRENCY_MAPPING[
                self.provider_id.available_currency_ids[0].name
            ],
            "mps_mode": "SCP",
            "return_url": urls.urljoin(base_url, AsiaPayController._return_url),
            "payment_type": "N",
            "language": get_language_code(lang),
            "payment_method": const.PAYMENT_METHODS_MAPPING.get(
                self.payment_method_id.code, "ALL"
            ),
        }
        rendering_values.update(
            {
                "secure_hash": self.provider_id._get_asiapay_signature(
                    rendering_values, incoming=False
                ),
                "api_url": self.provider_id._asiapay_get_api_url(),
            }
        )
        return rendering_values

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code != "asiapay":
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get("Ref")

    def _extract_amount_data(self, payment_data) -> dict | None:
        if self.provider_code != "asiapay":
            return super()._extract_amount_data(payment_data)

        amount = payment_data.get("Amt")
        currency = self.provider_id.available_currency_ids
        return {
            "amount": float(amount),
            "currency_code": currency.name,
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != "asiapay":
            return super()._apply_updates(payment_data)

        self.provider_reference = payment_data.get("PayRef")

        payment_method_code = payment_data.get("payMethod")
        payment_method = self.env["payment.method"]._get_from_code(
            payment_method_code, mapping=const.PAYMENT_METHODS_MAPPING
        )
        self.payment_method_id = payment_method or self.payment_method_id

        success_code = payment_data.get("successcode")
        primary_response_code = payment_data.get("prc")
        if not success_code:
            raise ValidationError(
                self.env._("Received data with missing success code.")
            )
        if success_code in const.SUCCESS_CODE_MAPPING["done"]:
            self._set_done()
        elif success_code in const.SUCCESS_CODE_MAPPING["error"]:
            self._set_error(
                self.env._(
                    "An error occurred during the processing of your payment (success code %(success_code)s; primary "
                    "response code %(response_code)s). Please try again.",
                    success_code=success_code,
                    response_code=primary_response_code,
                )
            )
        else:
            _logger.warning(
                "Received data with invalid success code (%s) for transaction with primary response"
                " code %s and reference %s.",
                success_code,
                primary_response_code,
                self.reference,
            )
            self._set_error(self.env._("Unknown success code: %s", success_code))
        return None
