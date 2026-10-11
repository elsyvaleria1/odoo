from urllib.parse import urlencode

from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.tools import consteq, float_round
from odoo.tools.urls import urljoin

from odoo.addons.integration.tools.admission import (
    Acknowledged,
    request_json_object,
)
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_xendit import const
from odoo.addons.payment_xendit.controllers.main import XenditController

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model
    def _receiver_for_xendit_webhook(self, **path_args):
        return self._resolve_notification(
            "xendit", request_json_object(), Acknowledged.json(["accepted"])
        )

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        if self.provider_code != "xendit":
            return super()._is_inbound_request_authentic(headers, body)
        return self._is_xendit_token_valid(headers.get("x-callback-token"))

    def _is_xendit_token_valid(self, received_token) -> bool:
        self.check_singleton()
        if not received_token:
            _logger.warning("Received payment data with missing token.")
            return False
        if not consteq(self.provider_id.xendit_webhook_token, received_token):
            _logger.warning(
                "Received payment data with invalid callback token %r.", received_token
            )
            return False
        return True

    def _prepare_provider_processing_values(self, processing_values):
        if self.provider_code != "xendit":
            return super()._prepare_provider_processing_values(processing_values)

        return {
            "rounded_amount": self._get_rounded_amount(),
        }

    def _prepare_redirect_form_values(self, processing_values):
        res = super()._prepare_redirect_form_values(processing_values)
        if self.provider_code != "xendit" or self.payment_method_code == "card":
            return res

        payload = self._xendit_prepare_invoice_request_payload()
        try:
            invoice_data = self._send_api_request("POST", "v2/invoices", json=payload)
        except ValidationError as error:
            self._set_error(str(error))
            return {}

        return {"api_url": invoice_data.get("invoice_url")}

    def _xendit_prepare_invoice_request_payload(self):
        base_url = self.provider_id.get_base_url()
        redirect_url = urljoin(base_url, XenditController._return_url)
        access_token = payment_utils.generate_access_token(self.reference, self.amount)
        success_url_params = urlencode(
            {
                "tx_ref": self.reference,
                "access_token": access_token,
                "success": "true",
            }
        )
        payload = {
            "external_id": self.reference,
            "amount": self._get_rounded_amount(),
            "description": self.reference,
            "customer": {
                "given_names": self.partner_name,
            },
            "success_redirect_url": f"{redirect_url}?{success_url_params}",
            "failure_redirect_url": redirect_url,
            "payment_methods": [
                const.PAYMENT_METHODS_MAPPING.get(
                    self.payment_method_code, self.payment_method_code.upper()
                )
            ],
            "currency": self.currency_id.name,
        }
        if self.payment_method_code == "fpx":
            payload["payment_methods"] = const.FPX_METHODS
        if self.partner_email:
            payload["customer"]["email"] = self.partner_email
        if phone := self.partner_phone:
            payload["customer"]["mobile_number"] = phone
        address_details = {}
        if self.partner_city:
            address_details["city"] = self.partner_city
        if self.partner_country_id.name:
            address_details["country"] = self.partner_country_id.name
        if self.partner_zip:
            address_details["postal_code"] = self.partner_zip
        if self.partner_state_id.name:
            address_details["state"] = self.partner_state_id.name
        if self.partner_address:
            address_details["street_line1"] = self.partner_address
        if address_details:
            payload["customer"]["addresses"] = [address_details]

        return payload

    def _send_payment_request(self):
        if self.provider_code != "xendit":
            return super()._send_payment_request()

        self._xendit_create_charge(self.token_id.provider_ref)
        return None

    def _xendit_create_charge(self, token_ref, auth_id=None) -> None:
        payload = {
            "token_id": token_ref,
            "external_id": self.reference,
            "amount": self._get_rounded_amount(),
            "currency": self.currency_id.name,
        }
        if auth_id:
            payload["authentication_id"] = auth_id

        if self.token_id or self.tokenize:
            payload["is_recurring"] = (
                True
            )

        try:
            charge_payment_data = self._send_api_request(
                "POST", "credit_card_charges", json=payload
            )
        except ValidationError as error:
            self._set_error(str(error))
        else:
            self._process("xendit", charge_payment_data)

    def _get_rounded_amount(self):
        decimal_places = const.CURRENCY_DECIMALS.get(
            self.currency_id.name, self.currency_id.decimal_places
        )
        return float_round(self.amount, decimal_places, rounding_method="DOWN")

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code != "xendit":
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get("external_id")

    def _extract_amount_data(self, payment_data) -> dict | None:
        if self.provider_code != "xendit":
            return super()._extract_amount_data(payment_data)

        amount = payment_data.get("amount") or payment_data.get("authorized_amount")
        currency_code = payment_data.get("currency")
        return {
            "amount": float(amount),
            "currency_code": currency_code,
            "precision_digits": const.CURRENCY_DECIMALS.get(currency_code),
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != "xendit":
            return super()._apply_updates(payment_data)

        self.provider_reference = payment_data.get("id")

        payment_method_code = payment_data.get("payment_method", "")
        if payment_method_code in const.FPX_METHODS:
            payment_method_code = "fpx"

        payment_method = self.env["payment.method"]._get_from_code(
            payment_method_code, mapping=const.PAYMENT_METHODS_MAPPING
        )
        self.payment_method_id = payment_method or self.payment_method_id

        payment_status = payment_data.get("status")
        if payment_status in const.PAYMENT_STATUS_MAPPING["pending"]:
            self._set_pending()
        elif payment_status in const.PAYMENT_STATUS_MAPPING["done"]:
            self._set_done()
        elif payment_status in const.PAYMENT_STATUS_MAPPING["cancel"]:
            self._set_canceled()
        elif payment_status in const.PAYMENT_STATUS_MAPPING["error"]:
            failure_reason = payment_data.get("failure_reason")
            self._set_error(
                self.env._(
                    "An error occurred during the processing of your payment (%s). Please try again.",
                    failure_reason,
                )
            )
        return None

    def _extract_token_values(self, payment_data) -> dict:
        if self.provider_code != "xendit":
            return super()._extract_token_values(payment_data)

        card_info = payment_data["masked_card_number"][
            -4:
        ]

        return {
            "payment_details": card_info,
            "provider_ref": payment_data["credit_card_token_id"],
        }
