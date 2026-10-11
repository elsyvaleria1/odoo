import hashlib
import hmac
import re
from datetime import UTC, datetime
from urllib.parse import urlencode as url_encode

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools import consteq
from odoo.tools.urls import urljoin as url_join

from odoo.addons.integration.tools.admission import (
    Acknowledged,
    Resolution,
    json_object,
    request_json_object,
)
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_stripe import const
from odoo.addons.payment_stripe import utils as stripe_utils
from odoo.addons.payment_stripe.controllers.main import StripeController

_logger = get_payment_logger(__name__, const.SENSITIVE_KEYS)

_SIGNATURE_TIMESTAMP_RE = re.compile(r"[1-9][0-9]{0,15}")


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    WEBHOOK_AGE_TOLERANCE = 10 * 60

    @api.model
    def _receiver_for_stripe_notification(self, **path_args):
        event = request_json_object()
        if event.get("type") not in const.HANDLED_WEBHOOK_EVENTS:
            raise Acknowledged
        stripe_object = json_object(
            json_object(event.get("data"), "data").get("object"), "data.object"
        )
        data = {
            "reference": stripe_object.get("description"),
            "event_type": event["type"],
            "object_id": stripe_object.get("id"),
        }
        tx = self.sudo()._search_by_reference("stripe", data)
        if not tx:
            raise Acknowledged
        return Resolution(
            tx,
            {"event": event, "stripe_object": stripe_object, "data": data},
            event_id=event.get("id") or None,
        )

    @api.model
    def _refuse_stripe_notification(self, refused):
        if refused.error_code == "duplicate_event":
            return request.prepare_response("", status=200)
        return refused._problem_response()

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        if self.provider_code != "stripe":
            return super()._is_inbound_request_authentic(headers, body)
        webhook_secret = stripe_utils.get_webhook_secret(self.provider_id)
        if not webhook_secret:
            _logger.warning(
                "refused a webhook event: provider %s has no webhook secret to check it",
                self.provider_id.name,
            )
            return False
        signature_header = headers.get("Stripe-Signature") or ""
        signature_data = dict(
            entry.split("=", 1) for entry in signature_header.split(",") if "=" in entry
        )
        event_timestamp = signature_data.get("t", "")
        if not _SIGNATURE_TIMESTAMP_RE.fullmatch(event_timestamp):
            _logger.warning("Received payment data with missing or malformed timestamp")
            return False
        if (
            datetime.now(UTC).timestamp() - int(event_timestamp)
            > self.WEBHOOK_AGE_TOLERANCE
        ):
            _logger.warning(
                "Received payment data with outdated timestamp: %s", event_timestamp
            )
            return False
        received_signature = signature_data.get("v1")
        if not received_signature:
            _logger.warning("Received payment data with missing signature")
            return False
        payload = body.decode("utf-8") if isinstance(body, bytes) else (body or "")
        expected_signature = hmac.new(
            webhook_secret.encode("utf-8"),
            f"{event_timestamp}.{payload}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not consteq(received_signature, expected_signature):
            _logger.warning("Received payment data with invalid signature")
            return False
        return True

    def _prepare_provider_processing_values(self, processing_values):
        if self.provider_code != "stripe" or self.operation == "online_token":
            return super()._prepare_provider_processing_values(processing_values)

        intent = self._stripe_create_intent()
        base_url = self.provider_id.get_base_url()
        return {
            "client_secret": intent["client_secret"] if intent else "",
            "return_url": url_join(
                base_url,
                f"{StripeController._return_url}?{url_encode({'reference': self.reference})}",
            ),
        }

    def _send_payment_request(self):
        if self.provider_code != "stripe":
            return super()._send_payment_request()

        payment_intent = self._stripe_create_intent()

        if not payment_intent:
            return None

        payment_data = {"reference": self.reference}
        StripeController._include_payment_intent_in_payment_data(
            payment_intent, payment_data
        )
        self._process("stripe", payment_data)
        return None

    def _stripe_create_intent(self):
        try:
            if self.operation == "validation":
                response = self._send_api_request(
                    "POST",
                    "setup_intents",
                    data=self._stripe_prepare_setup_intent_payload(),
                )
            else:
                response = self._send_api_request(
                    "POST",
                    "payment_intents",
                    data=self._stripe_prepare_payment_intent_payload(),
                    offline=self.operation == "offline",
                    idempotency_key=payment_utils.generate_idempotency_key(
                        self, scope="payment_intents"
                    ),
                )
        except ValidationError as error:
            self._set_error(str(error))
            intent = None
        else:
            intent = response

        return intent

    def _stripe_prepare_setup_intent_payload(self):
        customer = self._stripe_create_customer()
        setup_intent_payload = {
            "customer": customer["id"],
            "description": self.reference,
            "payment_method_types[]": const.PAYMENT_METHODS_MAPPING.get(
                self.payment_method_code, self.payment_method_code
            ),
        }
        if self.currency_id.name in const.INDIAN_MANDATES_SUPPORTED_CURRENCIES:
            setup_intent_payload.update(**self._stripe_prepare_mandate_options())
        return setup_intent_payload

    def _stripe_prepare_payment_intent_payload(self):
        ppm_code = self.payment_method_id.primary_payment_method_id.code
        payment_method_type = ppm_code or self.payment_method_code
        payment_intent_payload = {
            "amount": payment_utils.major_to_minor_currency_units(
                self.amount,
                self.currency_id,
                arbitrary_decimal_number=const.CURRENCY_DECIMALS.get(
                    self.currency_id.name
                ),
            ),
            "currency": self.currency_id.name.lower(),
            "description": self.reference,
            "capture_method": "manual"
            if self.provider_id.capture_manually
            else "automatic",
            "payment_method_types[]": const.PAYMENT_METHODS_MAPPING.get(
                payment_method_type, payment_method_type
            ),
            "expand[]": "payment_method",
            **stripe_utils.include_shipping_address(self),
        }
        if self.operation in ["online_token", "offline"]:
            if not self.token_id.stripe_payment_method:
                self.token_id._stripe_sca_migrate_customer()

            payment_intent_payload.update(
                {
                    "confirm": True,
                    "customer": self.token_id.provider_ref,
                    "off_session": True,
                    "payment_method": self.token_id.stripe_payment_method,
                    "mandate": self.token_id.stripe_mandate or None,
                }
            )
        else:
            customer = self._stripe_create_customer()
            payment_intent_payload["customer"] = customer["id"]
            if self.tokenize:
                payment_intent_payload["setup_future_usage"] = "off_session"
                if self.currency_id.name in const.INDIAN_MANDATES_SUPPORTED_CURRENCIES:
                    payment_intent_payload.update(
                        **self._stripe_prepare_mandate_options()
                    )
        return payment_intent_payload

    def _stripe_create_customer(self):
        return self._send_api_request(
            "POST",
            "customers",
            data={
                "address[city]": self.partner_city or None,
                "address[country]": self.partner_country_id.code or None,
                "address[line1]": self.partner_address or None,
                "address[postal_code]": self.partner_zip or None,
                "address[state]": self.partner_state_id.name or None,
                "description": f"Odoo Partner: {self.partner_id.name} (id: {self.partner_id.id})",
                "email": self.partner_email or None,
                "name": self.partner_name,
                "phone": (self.partner_phone and self.partner_phone[:20]) or None,
            },
        )

    def _stripe_prepare_mandate_options(self):
        mandate_values = self._prepare_mandate_data()

        OPTION_PATH_PREFIX = "payment_method_options[card][mandate_options]"
        mandate_options = {
            f"{OPTION_PATH_PREFIX}[reference]": self.reference,
            f"{OPTION_PATH_PREFIX}[amount_type]": "maximum",
            f"{OPTION_PATH_PREFIX}[amount]": payment_utils.major_to_minor_currency_units(
                mandate_values.get("amount", 15000),
                self.currency_id,
                arbitrary_decimal_number=const.CURRENCY_DECIMALS.get(
                    self.currency_id.name
                ),
            ),
            f"{OPTION_PATH_PREFIX}[start_date]": round(
                (
                    mandate_values.get("start_datetime") or fields.Datetime.now()
                ).timestamp()
            ),
            f"{OPTION_PATH_PREFIX}[interval]": "sporadic",
            f"{OPTION_PATH_PREFIX}[supported_types][]": "india",
        }
        if mandate_values.get("end_datetime"):
            mandate_options[f"{OPTION_PATH_PREFIX}[end_date]"] = round(
                mandate_values["end_datetime"].timestamp()
            )
        if mandate_values.get("recurrence_unit") and mandate_values.get(
            "recurrence_duration"
        ):
            mandate_options.update(
                {
                    f"{OPTION_PATH_PREFIX}[interval]": mandate_values[
                        "recurrence_unit"
                    ],
                    f"{OPTION_PATH_PREFIX}[interval_count]": mandate_values[
                        "recurrence_duration"
                    ],
                }
            )
        if self.operation == "validation":
            currency_name = (
                self.provider_id.with_context(
                    validation_pm=self.payment_method_id
                )
                ._get_validation_currency()
                .name.lower()
            )
            mandate_options[f"{OPTION_PATH_PREFIX}[currency]"] = currency_name

        return mandate_options

    def _send_refund_request(self):
        if self.provider_code != "stripe":
            return super()._send_refund_request()

        data = self._send_api_request(
            "POST",
            "refunds",
            data={
                "payment_intent": self.source_transaction_id.provider_reference,
                "amount": payment_utils.major_to_minor_currency_units(
                    -self.amount,
                    self.currency_id,
                    arbitrary_decimal_number=const.CURRENCY_DECIMALS.get(
                        self.currency_id.name
                    ),
                ),
            },
        )

        payment_data = {}
        StripeController._include_refund_in_payment_data(data, payment_data)
        self._process("stripe", payment_data)
        return None

    def _send_capture_request(self):
        if self.provider_code != "stripe":
            return super()._send_capture_request()

        payment_intent = self._send_api_request(
            "POST",
            f"payment_intents/{self.source_transaction_id.provider_reference}/capture",
        )

        payment_data = {"reference": self.reference}
        StripeController._include_payment_intent_in_payment_data(
            payment_intent, payment_data
        )
        self._process("stripe", payment_data)
        return None

    def _send_void_request(self):
        if self.provider_code != "stripe":
            return super()._send_void_request()

        payment_intent = self._send_api_request(
            "POST",
            f"payment_intents/{self.source_transaction_id.provider_reference}/cancel",
        )

        payment_data = {"reference": self.reference}
        StripeController._include_payment_intent_in_payment_data(
            payment_intent, payment_data
        )
        self._process("stripe", payment_data)
        return None

    @api.model
    def _search_by_reference(self, provider_code, payment_data):
        if provider_code != "stripe":
            return super()._search_by_reference(provider_code, payment_data)

        reference = payment_data.get("reference")
        if reference:
            tx = self._search_by_notified_value("stripe", "reference", reference)
        elif payment_data.get("event_type") == "charge.refund.updated":
            tx = self._search_by_notified_value(
                "stripe", "provider_reference", payment_data.get("object_id")
            )
        else:
            _logger.warning("Received data with missing merchant reference")
            tx = self

        if not tx:
            _logger.warning("No transaction found matching reference %s.", reference)

        return tx

    def _extract_amount_data(self, payment_data) -> dict | None:
        if self.provider_code != "stripe":
            return super()._extract_amount_data(payment_data)

        if self.operation == "refund":
            payment_data = payment_data["refund"]
        else:
            payment_data = payment_data["payment_intent"]
        amount = payment_utils.minor_to_major_currency_units(
            payment_data.get("amount", 0),
            self.currency_id,
            arbitrary_decimal_number=const.CURRENCY_DECIMALS.get(self.currency_id.name),
        )
        currency_code = payment_data.get("currency", "").upper()
        return {
            "amount": amount,
            "currency_code": currency_code,
            "precision_digits": const.CURRENCY_DECIMALS.get(self.currency_id.name),
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != "stripe":
            return super()._apply_updates(payment_data)

        payment_method = payment_data.get("payment_method")
        if isinstance(
            payment_method, dict
        ):
            payment_method_type = payment_method.get("type")
            if self.payment_method_id.code == payment_method_type == "card":
                payment_method_type = payment_data["payment_method"]["card"]["brand"]
            payment_method = self.env["payment.method"]._get_from_code(
                payment_method_type, mapping=const.PAYMENT_METHODS_MAPPING
            )
            self.payment_method_id = payment_method or self.payment_method_id

        if self.operation == "validation":
            self.provider_reference = payment_data["setup_intent"]["id"]
            status = payment_data["setup_intent"]["status"]
        elif self.operation == "refund":
            self.provider_reference = payment_data["refund"]["id"]
            status = payment_data["refund"]["status"]
        else:
            self.provider_reference = payment_data["payment_intent"]["id"]
            status = payment_data["payment_intent"]["status"]
        if not status:
            self._set_error(self.env._("Received data with missing intent status."))
        elif status in const.STATUS_MAPPING["draft"]:
            pass
        elif status in const.STATUS_MAPPING["pending"]:
            self._set_pending()
        elif status in const.STATUS_MAPPING["authorized"]:
            self._set_authorized()
        elif status in const.STATUS_MAPPING["done"]:
            self._set_done()

            if self.operation == "refund":
                self.env["ir.cron"]._trigger_ref("payment.cron_post_process_payment_tx")
        elif status in const.STATUS_MAPPING["cancel"]:
            self._set_canceled()
        elif status in const.STATUS_MAPPING["error"]:
            if self.operation != "refund":
                last_payment_error = payment_data.get("payment_intent", {}).get(
                    "last_payment_error"
                )
                if last_payment_error:
                    message = last_payment_error.get("message", {})
                else:
                    message = self.env._("The customer left the payment page.")
                self._set_error(message)
            else:
                self._set_error(
                    self.env._(
                        "The refund did not go through. Please log into your Stripe Dashboard to get "
                        "more information on that matter, and address any accounting discrepancies."
                    ),
                    extra_allowed_states=("done",),
                )
        else:
            _logger.warning(
                "Received invalid payment status (%s) for transaction %s.",
                status,
                self.reference,
            )
            self._set_error(
                self.env._("Received data with invalid intent status: %s.", status)
            )
        return None

    def _extract_token_values(self, payment_data) -> dict:
        if self.provider_code != "stripe":
            return super()._extract_token_values(payment_data)

        payment_method = payment_data.get("payment_method")
        if not payment_method:
            _logger.warning(
                "requested tokenization from payment data with missing payment method"
            )
            return {}

        mandate = None
        if self.operation == "online_direct":
            customer_id = payment_data["payment_intent"]["customer"]
            charges_data = payment_data["payment_intent"]["charges"]
            payment_method_details = charges_data["data"][0].get(
                "payment_method_details"
            )
            if payment_method_details:
                mandate = payment_method_details[payment_method_details["type"]].get(
                    "mandate"
                )
        else:
            customer_id = payment_data["setup_intent"]["customer"]
        if not payment_method[payment_method["type"]]:
            try:
                payment_methods = self._send_api_request(
                    "GET", f"customers/{customer_id}/payment_methods"
                )
            except ValidationError as e:
                self._set_error(str(e))
                return {}
            payment_method = payment_methods["data"][0]

        return {
            "payment_details": payment_method[payment_method["type"]].get("last4"),
            "provider_ref": customer_id,
            "stripe_payment_method": payment_method["id"],
            "stripe_mandate": mandate,
        }
