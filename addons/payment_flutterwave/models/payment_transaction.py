from typing import Self

from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.tools import consteq, urls

from odoo.addons.integration.tools.admission import (
    Acknowledged,
    json_object,
    request_json_object,
)
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_flutterwave import const
from odoo.addons.payment_flutterwave.controllers.main import FlutterwaveController

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model
    def _receiver_for_flutterwave_webhook(self, **path_args):
        data = request_json_object()
        if data.get("event") != "charge.completed":
            raise Acknowledged.json("")
        return self._resolve_notification(
            "flutterwave",
            json_object(data.get("data") or {}, "data"),
            Acknowledged.json(""),
        )

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        if self.provider_code != "flutterwave":
            return super()._is_inbound_request_authentic(headers, body)
        return self._is_flutterwave_signature_valid(headers.get("verif-hash"))

    def _is_flutterwave_signature_valid(self, received_signature) -> bool:
        self.check_singleton()
        if not received_signature:
            _logger.warning("Received payment data with missing signature.")
            return False
        expected_signature = self.provider_id.flutterwave_webhook_secret
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
        if provider_code == "flutterwave":
            if not prefix:
                prefix = self.sudo()._get_reference_prefix(separator, **kwargs) or None
            prefix = payment_utils.singularize_reference_prefix(
                prefix=prefix, separator=separator
            )
        return super()._get_unique_reference(
            provider_code,
            prefix=prefix,
            separator=separator,
            references_in_use=references_in_use,
            **kwargs,
        )

    def _prepare_provider_processing_values(self, processing_values):
        if not self._filtered_flutterwave_pending_authorizations():
            return super()._prepare_provider_processing_values(processing_values)

        return {
            "redirect_form_html": self.env["ir.qweb"]._render(
                self.provider_id.redirect_form_view_id.id,
                {"auth_url": self.provider_reference},
            )
        }

    def _prepare_redirect_form_values(self, processing_values):
        res = super()._prepare_redirect_form_values(processing_values)
        if self.provider_code != "flutterwave":
            return res

        base_url = self.provider_id.get_base_url()
        payload = {
            "tx_ref": self.reference,
            "amount": self.amount,
            "currency": self.currency_id.name,
            "redirect_url": urls.urljoin(base_url, FlutterwaveController._return_url),
            "customer": {
                "email": self.partner_email,
                "name": self.partner_name,
                "phonenumber": self.partner_phone,
            },
            "customizations": {
                "title": self.company_id.name,
                "logo": urls.urljoin(
                    base_url, f"web/image/res.company/{self.company_id.id}/image_1920"
                ),
            },
            "payment_options": const.PAYMENT_METHODS_MAPPING.get(
                self.payment_method_code, self.payment_method_code
            ),
        }
        try:
            payment_link_data = self._send_api_request("POST", "payments", json=payload)
        except ValidationError as error:
            self._set_error(str(error))
            return {}

        return {"api_url": payment_link_data["link"]}

    def _send_payment_request(self):
        if self.provider_code != "flutterwave":
            return super()._send_payment_request()

        first_name, last_name = payment_utils.split_partner_name(self.partner_name)
        base_url = self.provider_id.get_base_url()
        data = {
            "token": self.token_id.provider_ref,
            "email": self.token_id.flutterwave_customer_email,
            "amount": self.amount,
            "currency": self.currency_id.name,
            "country": self.company_id.country_id.code,
            "tx_ref": self.reference,
            "first_name": first_name,
            "last_name": last_name,
            "ip": payment_utils.get_customer_ip_address(),
            "redirect_url": urls.urljoin(
                base_url, FlutterwaveController._auth_return_url
            ),
        }

        try:
            response_content = self._send_api_request(
                "POST", "tokenized-charges", json=data
            )
        except ValidationError as error:
            self._set_error(str(error))
        else:
            self._process("flutterwave", response_content)

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code != "flutterwave":
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get("tx_ref") or payment_data.get("txRef")

    def _extract_amount_data(self, payment_data) -> dict | None:
        if self.provider_code != "flutterwave":
            return super()._extract_amount_data(payment_data)

        amount = payment_data.get("amount")
        currency_code = payment_data.get("currency")
        return {
            "amount": float(amount),
            "currency_code": currency_code,
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != "flutterwave":
            return super()._apply_updates(payment_data)

        self.provider_reference = payment_data["id"]

        payment_method_type = payment_data.get("payment_type", "")
        if payment_method_type == "card":
            payment_method_type = payment_data.get("card", {}).get("type").lower()
        payment_method = self.env["payment.method"]._get_from_code(
            payment_method_type, mapping=const.PAYMENT_METHODS_MAPPING
        )
        self.payment_method_id = payment_method or self.payment_method_id

        payment_status = payment_data["status"].lower()
        if payment_status in const.PAYMENT_STATUS_MAPPING["pending"]:
            auth_url = (
                payment_data.get("meta", {}).get("authorization", {}).get("redirect")
            )
            if auth_url:
                self.provider_reference = auth_url
            self._set_pending()
        elif payment_status in const.PAYMENT_STATUS_MAPPING["done"]:
            self._set_done()
        elif payment_status in const.PAYMENT_STATUS_MAPPING["cancel"]:
            self._set_canceled()
        elif payment_status in const.PAYMENT_STATUS_MAPPING["error"]:
            self._set_error(
                self.env._(
                    "An error occurred during the processing of your payment (status %s). Please try "
                    "again.",
                    payment_status,
                )
            )
        else:
            _logger.warning(
                "Received data with invalid payment status (%s) for transaction %s.",
                payment_status,
                self.reference,
            )
            self._set_error(self.env._("Unknown payment status: %s", payment_status))
        return None

    def _extract_token_values(self, payment_data) -> dict:
        if self.provider_code != "flutterwave":
            return super()._extract_token_values(payment_data)

        if "token" not in payment_data.get("card", {}):
            return {}

        return {
            "payment_details": payment_data["card"]["last_4digits"],
            "provider_ref": payment_data["card"]["token"],
            "flutterwave_customer_email": payment_data["customer"]["email"],
        }

    def _filtered_flutterwave_pending_authorizations(self) -> Self:
        return self.filtered_domain(
            [
                ("provider_code", "=", "flutterwave"),
                ("operation", "=", "online_token"),
                ("state", "=", "pending"),
                ("provider_reference", "ilike", "https"),
            ]
        )
