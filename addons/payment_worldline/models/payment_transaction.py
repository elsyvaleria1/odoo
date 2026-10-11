import hashlib
import hmac
from base64 import b64encode
from urllib.parse import urlencode as url_encode

from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.tools import urls

from odoo.addons.integration.tools.admission import (
    Acknowledged,
    json_get,
    request_json_object,
)
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_worldline import const
from odoo.addons.payment_worldline.controllers.main import WorldlineController

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model
    def _receiver_for_worldline_webhook(self, **path_args):
        return self._resolve_notification(
            "worldline", request_json_object(), Acknowledged.json("")
        )

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        if self.provider_code != "worldline":
            return super()._is_inbound_request_authentic(headers, body)
        return self._is_worldline_signature_valid(body, headers.get("X-GCS-Signature"))

    def _is_worldline_signature_valid(self, request_data, received_signature) -> bool:
        self.check_singleton()
        if not received_signature:
            _logger.warning("Received payment data with missing signature.")
            return False
        if isinstance(received_signature, str):
            received_signature = received_signature.encode()
        webhook_secret = self.provider_id.worldline_webhook_secret
        expected_signature = b64encode(
            hmac.new(webhook_secret.encode(), request_data, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(received_signature, expected_signature):
            _logger.warning("Received payment data with invalid signature.")
            return False
        return True

    def _get_unique_reference(
        self,
        provider_code,
        prefix=None,
        separator="-",
        references_in_use: set[str] | None = None,
        **kwargs,
    ) -> str:
        reference = super()._get_unique_reference(
            provider_code,
            prefix=prefix,
            separator=separator,
            references_in_use=references_in_use,
            **kwargs,
        )
        if provider_code != "worldline":
            return reference

        if (
            len(reference) <= 30
        ):
            return reference

        prefix = payment_utils.singularize_reference_prefix(prefix="WL")
        return super()._get_unique_reference(
            provider_code,
            prefix=prefix,
            separator=separator,
            references_in_use=references_in_use,
            **kwargs,
        )

    def _prepare_provider_processing_values(self, processing_values):
        if (
            self.provider_code == "worldline"
            and self.operation == "online_token"
            and self.state == "error"
            and self.state_message.endswith("AUTHORIZATION_REQUESTED")
        ):
            self.write(
                {
                    "state": "draft",
                    "operation": "online_redirect",
                }
            )
            return {"force_flow": "redirect"}
        return super()._prepare_provider_processing_values(processing_values)

    def _prepare_redirect_form_values(self, processing_values):
        if self.provider_code != "worldline":
            return super()._prepare_redirect_form_values(processing_values)

        checkout_session_data = self._worldline_create_checkout_session()
        return {"api_url": checkout_session_data["redirectUrl"]}

    def _worldline_create_checkout_session(self):
        self.check_singleton()

        base_url = self.provider_id.get_base_url()
        return_route = WorldlineController._return_url
        return_url_params = url_encode({"provider_id": str(self.provider_id.id)})
        return_url = f"{urls.urljoin(base_url, return_route)}?{return_url_params}"
        first_name, last_name = payment_utils.split_partner_name(self.partner_name)
        payload = {
            "hostedCheckoutSpecificInput": {
                "locale": self.partner_lang or "",
                "returnUrl": return_url,
                "showResultPage": False,
            },
            "order": {
                "amountOfMoney": {
                    "amount": payment_utils.major_to_minor_currency_units(
                        self.amount, self.currency_id
                    ),
                    "currencyCode": self.currency_id.name,
                },
                "customer": {
                    "billingAddress": {
                        "city": self.partner_city or "",
                        "countryCode": self.partner_country_id.code or "",
                        "state": self.partner_state_id.name or "",
                        "street": self.partner_address or "",
                        "zip": self.partner_zip or "",
                    },
                    "contactDetails": {
                        "emailAddress": self.partner_email or "",
                        "phoneNumber": self.partner_phone or "",
                    },
                    "personalInformation": {
                        "name": {
                            "firstName": first_name or "",
                            "surname": last_name or "",
                        },
                    },
                },
                "references": {
                    "descriptor": self.reference,
                    "merchantReference": self.reference,
                },
            },
        }
        if self.payment_method_id.code in const.REDIRECT_PAYMENT_METHODS:
            payload["redirectPaymentMethodSpecificInput"] = {
                "requiresApproval": False,
                "paymentProductId": const.PAYMENT_METHODS_MAPPING[
                    self.payment_method_id.code
                ],
                "redirectionData": {
                    "returnUrl": return_url,
                },
            }
        else:
            payload["cardPaymentMethodSpecificInput"] = {
                "authorizationMode": "SALE",
                "tokenize": self.tokenize,
            }
            if (
                not self.payment_method_id.brand_ids
                and self.payment_method_id.code != "card"
            ):
                worldline_code = const.PAYMENT_METHODS_MAPPING.get(
                    self.payment_method_id.code, 0
                )
                payload["cardPaymentMethodSpecificInput"]["paymentProductId"] = (
                    worldline_code
                )
            else:
                payload["hostedCheckoutSpecificInput"]["paymentProductFilters"] = {
                    "restrictTo": {
                        "groups": ["cards"],
                    },
                }

        return self._send_api_request("POST", "hostedcheckouts", json=payload)

    def _send_payment_request(self):
        if self.provider_code != "worldline":
            return super()._send_payment_request()

        payload = {
            "cardPaymentMethodSpecificInput": {
                "authorizationMode": "SALE",
                "token": self.token_id.provider_ref,
                "unscheduledCardOnFileRequestor": "merchantInitiated",
                "unscheduledCardOnFileSequenceIndicator": "subsequent",
            },
            "order": {
                "amountOfMoney": {
                    "amount": payment_utils.major_to_minor_currency_units(
                        self.amount, self.currency_id
                    ),
                    "currencyCode": self.currency_id.name,
                },
                "references": {
                    "merchantReference": self.reference,
                },
            },
        }

        try:
            response_content = self._send_api_request(
                "POST",
                "payments",
                json=payload,
                idempotency_key=payment_utils.generate_idempotency_key(
                    self, scope="payment_request_token"
                ),
            )
        except ValidationError as e:
            self._set_error(str(e))
        else:
            self._process("worldline", response_content)

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code != "worldline":
            return super()._extract_reference(provider_code, payment_data)

        payment_result = payment_data.get("paymentResult", payment_data)
        return (
            json_get(
                payment_result,
                "payment",
                "paymentOutput",
                "references",
                "merchantReference",
            )
            or ""
        )

    def _extract_amount_data(self, payment_data) -> dict | None:
        if self.provider_code != "worldline":
            return super()._extract_amount_data(payment_data)

        payment_result = payment_data.get("paymentResult", payment_data)
        amount_of_money = (
            payment_result.get("payment", {})
            .get("paymentOutput", {})
            .get("amountOfMoney", {})
        )
        amount = payment_utils.minor_to_major_currency_units(
            amount_of_money.get("amount", 0), self.currency_id
        )
        currency_code = amount_of_money.get("currencyCode")
        return {
            "amount": amount,
            "currency_code": currency_code,
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != "worldline":
            return super()._apply_updates(payment_data)

        payment_result = payment_data.get("paymentResult", payment_data)
        payment_data = payment_result.get("payment", {})

        self.provider_reference = payment_data.get("id", "").rsplit("_", 1)[0]

        payment_method_data = self._worldline_extract_payment_method_data(payment_data)
        payment_method_code = payment_method_data.get("paymentProductId", "")
        payment_method = self.env["payment.method"]._get_from_code(
            payment_method_code, mapping=const.PAYMENT_METHODS_MAPPING
        )
        self.payment_method_id = payment_method or self.payment_method_id

        status = payment_data.get("status")
        has_token_data = "token" in payment_method_data
        if not status:
            self._set_error(self.env._("Received data with missing payment state."))
        elif status in const.PAYMENT_STATUS_MAPPING["pending"]:
            if status == "AUTHORIZATION_REQUESTED" and self.operation in (
                "online_token",
                "offline",
            ):
                self._set_error(status)
            elif (
                self.operation == "validation"
                and status in {"PENDING_CAPTURE", "CAPTURE_REQUESTED"}
                and has_token_data
            ):
                self._set_done()
            else:
                self._set_pending()
        elif status in const.PAYMENT_STATUS_MAPPING["done"]:
            self._set_done()
        else:
            error_code = None
            if errors := payment_data.get("statusOutput", {}).get("errors"):
                error_code = errors[0].get("errorCode")
            if status in const.PAYMENT_STATUS_MAPPING["cancel"]:
                self._set_canceled(
                    self.env._(
                        "Transaction cancelled with error code %(error_code)s.",
                        error_code=error_code,
                    )
                )
            elif status in const.PAYMENT_STATUS_MAPPING["declined"]:
                self._set_error(
                    self.env._(
                        "Transaction declined with error code %(error_code)s.",
                        error_code=error_code,
                    )
                )
            else:
                _logger.info(
                    "Received data with invalid payment status (%(status)s) for transaction with "
                    "reference %(ref)s.",
                    {"status": status, "ref": self.reference},
                )
                self._set_error(
                    self.env._(
                        "Received invalid transaction status %(status)s with error code "
                        "%(error_code)s.",
                        status=status,
                        error_code=error_code,
                    )
                )
        return None

    @staticmethod
    def _worldline_extract_payment_method_data(payment_data):
        payment_output = payment_data.get("paymentOutput", {})
        if "cardPaymentMethodSpecificOutput" in payment_output:
            payment_method_data = payment_output["cardPaymentMethodSpecificOutput"]
        else:
            payment_method_data = payment_output.get(
                "redirectPaymentMethodSpecificOutput", {}
            )
        return payment_method_data

    def _extract_token_values(self, payment_data) -> dict:
        if self.provider_code != "worldline":
            return super()._extract_token_values(payment_data)

        payment_data = payment_data.get("payment", {})
        payment_method_data = self._worldline_extract_payment_method_data(payment_data)
        if "token" not in payment_method_data:
            return {}

        payment_details = payment_method_data.get("card", {}).get("cardNumber", "")[-4:]
        return {
            "payment_details": payment_details,
            "provider_ref": payment_method_data["token"],
        }
