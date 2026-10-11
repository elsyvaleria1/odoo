from odoo import api, models, release
from odoo.http import request
from odoo.tools import format_amount

from odoo.addons.integration.tools.admission import Acknowledged
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_adyen import const
from odoo.addons.payment_adyen import utils as adyen_utils

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model
    def _receiver_for_adyen_return(self, **path_args) -> tuple:
        data = request.get_http_params()
        if not data.get("redirectResult"):
            raise Acknowledged.redirect("/payment/status")
        tx = self.sudo()._search_by_notified_value(
            "adyen", "reference", data.get("merchantReference")
        )
        return tx, {"data": data}

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        if self.provider_code != "adyen":
            return super()._is_inbound_request_authentic(headers, body)
        return True

    def _prepare_provider_processing_values(self, processing_values):
        if self.provider_code != "adyen":
            return super()._prepare_provider_processing_values(processing_values)

        converted_amount = payment_utils.major_to_minor_currency_units(
            self.amount,
            self.currency_id,
            const.CURRENCY_DECIMALS.get(self.currency_id.name),
        )
        return {
            "converted_amount": converted_amount,
            "access_token": payment_utils.generate_access_token(
                processing_values["reference"],
                converted_amount,
                self.currency_id.id,
                processing_values["partner_id"],
            ),
        }

    def _send_payment_request(self):
        if self.provider_code != "adyen":
            return super()._send_payment_request()

        converted_amount = payment_utils.major_to_minor_currency_units(
            self.amount,
            self.currency_id,
            const.CURRENCY_DECIMALS.get(self.currency_id.name),
        )
        partner_country_code = (
            self.partner_country_id.code
            or self.provider_id.company_id.country_id.code
            or "NL"
        )
        data = {
            "merchantAccount": self.provider_id.adyen_merchant_account,
            "amount": {
                "value": converted_amount,
                "currency": self.currency_id.name,
            },
            "applicationInfo": {
                "externalPlatform": {
                    "name": "Odoo",
                    "version": release.version,
                    "integrator": "Odoo SA",
                }
            },
            "countryCode": partner_country_code,
            "reference": self.reference,
            "paymentMethod": {
                "storedPaymentMethodId": self.token_id.provider_ref,
            },
            "shopperReference": self.token_id.adyen_shopper_reference,
            "recurringProcessingModel": "Subscription",
            "shopperIP": payment_utils.get_customer_ip_address(),
            "shopperInteraction": "ContAuth",
            "shopperEmail": self.partner_email,
            "shopperName": adyen_utils.format_partner_name(self.partner_name),
            "telephoneNumber": self.partner_phone,
            **adyen_utils.include_partner_addresses(self),
            "lineItems": [
                {
                    "amountIncludingTax": converted_amount,
                    "quantity": "1",
                    "description": self.reference,
                }
            ],
        }

        if not self.provider_id.capture_manually:
            data.update(captureDelayHours=0)

        response_content = self._send_api_request(
            "POST",
            "/payments",
            json=data,
            idempotency_key=payment_utils.generate_idempotency_key(
                self, scope="payment_request_token"
            ),
        )
        self._process("adyen", response_content)
        return None

    def _send_capture_request(self):
        if self.provider_code != "adyen":
            return super()._send_capture_request()

        converted_amount = payment_utils.major_to_minor_currency_units(
            self.amount,
            self.currency_id,
            const.CURRENCY_DECIMALS.get(self.currency_id.name),
        )
        data = {
            "merchantAccount": self.provider_id.adyen_merchant_account,
            "amount": {
                "value": converted_amount,
                "currency": self.currency_id.name,
            },
            "reference": self.reference,
        }

        response_content = self._send_api_request(
            "POST",
            "/payments/{}/captures",
            json=data,
            endpoint_param=self.provider_reference,
        )

        status = response_content.get("status")
        formatted_amount = format_amount(self.env, self.amount, self.currency_id)
        if status == "received":
            self._log_message_on_linked_documents(
                self.env._(
                    "The capture request of %(amount)s for transaction %(ref)s has been sent.",
                    amount=formatted_amount,
                    ref=self.reference,
                )
            )

        self.provider_reference = response_content.get("pspReference")
        return None

    def _send_void_request(self):
        if self.provider_code != "adyen":
            return super()._send_void_request()

        data = {
            "merchantAccount": self.provider_id.adyen_merchant_account,
            "reference": self.reference,
        }
        response_content = self._send_api_request(
            "POST",
            "/payments/{}/cancels",
            json=data,
            endpoint_param=self.provider_reference,
        )

        status = response_content.get("status")
        if status == "received":
            self._log_message_on_linked_documents(
                self.env._(
                    "A request was sent to void the transaction %(reference)s.",
                    reference=self.reference,
                )
            )

        self.provider_reference = response_content.get("pspReference")
        return None

    def _send_refund_request(self):
        if self.provider_code != "adyen":
            return super()._send_refund_request()

        converted_amount = payment_utils.major_to_minor_currency_units(
            -self.amount,
            self.currency_id,
            arbitrary_decimal_number=const.CURRENCY_DECIMALS.get(self.currency_id.name),
        )
        data = {
            "merchantAccount": self.provider_id.adyen_merchant_account,
            "amount": {
                "value": converted_amount,
                "currency": self.currency_id.name,
            },
            "reference": self.reference,
        }
        response_content = self._send_api_request(
            "POST",
            "/payments/{}/refunds",
            json=data,
            endpoint_param=self.source_transaction_id.provider_reference,
        )

        psp_reference = response_content.get("pspReference")
        status = response_content.get("status")
        if psp_reference and status == "received":
            self.provider_reference = psp_reference
        return None

    @api.model
    def _search_by_reference(self, provider_code, payment_data):
        if provider_code != "adyen":
            return super()._search_by_reference(provider_code, payment_data)

        tx = self
        reference = payment_data.get("merchantReference")
        if not reference or not isinstance(reference, str):
            _logger.warning("Received data with missing or malformed reference.")
            return tx

        event_code = payment_data.get("eventCode", "AUTHORISATION")
        provider_reference = payment_data.get("pspReference")
        source_reference = payment_data.get("originalReference")
        if event_code == "AUTHORISATION":
            tx = self._search_by_notified_value("adyen", "reference", reference)
        elif event_code in const.CHILD_OPERATION_EVENT_CODES:
            source_tx = self._search_by_notified_value(
                "adyen", "provider_reference", source_reference
            )
            minor_amount = adyen_utils.get_minor_amount(payment_data)
            if source_tx and minor_amount is None:
                _logger.warning("Received data with missing or malformed amount.")
            elif source_tx:
                converted_notification_amount = (
                    payment_utils.minor_to_major_currency_units(
                        minor_amount,
                        source_tx.currency_id,
                        arbitrary_decimal_number=const.CURRENCY_DECIMALS.get(
                            source_tx.currency_id.name
                        ),
                    )
                )
                if source_tx.amount == converted_notification_amount:
                    tx = source_tx
                else:
                    tx = self._search_by_notified_value(
                        "adyen", "provider_reference", provider_reference
                    )
                    if tx and tx.amount != converted_notification_amount:
                        tx._set_error(
                            self.env._(
                                "The amount processed by Adyen for the transaction %s is different than"
                                " the one requested. Another transaction is created with the correct"
                                " amount.",
                                tx.reference,
                            )
                        )
                        tx = self.env["payment.transaction"]
                    if not tx:
                        tx = self._adyen_create_child_tx(source_tx, payment_data)
        else:
            tx = self._search_by_notified_value(
                "adyen", "provider_reference", provider_reference
            )
            if not tx:
                source_tx = self._search_by_notified_value(
                    "adyen", "provider_reference", source_reference
                )
                if source_tx:
                    tx = self._adyen_create_child_tx(
                        source_tx, payment_data, is_refund=True
                    )
        if not tx:
            _logger.warning("No transaction found matching reference %s.", reference)
        return tx

    @api.model
    def _search_notification_subject(self, provider_code, payment_data):
        if provider_code != "adyen":
            return super()._search_notification_subject(provider_code, payment_data)
        reference = payment_data.get("merchantReference")
        if not reference or not isinstance(reference, str):
            return self.browse()
        event_code = payment_data.get("eventCode", "AUTHORISATION")
        if event_code == "AUTHORISATION":
            return self._search_by_notified_value("adyen", "reference", reference)
        if event_code not in const.CHILD_OPERATION_EVENT_CODES:
            refund_tx = self._search_by_notified_value(
                "adyen", "provider_reference", payment_data.get("pspReference")
            )
            if refund_tx:
                return refund_tx
        return self._search_by_notified_value(
            "adyen", "provider_reference", payment_data.get("originalReference")
        )

    def _adyen_create_child_tx(self, source_tx, payment_data, is_refund=False):
        provider_reference = payment_data.get("pspReference")
        amount = adyen_utils.get_minor_amount(payment_data)
        if (
            not provider_reference
            or not isinstance(provider_reference, str)
            or amount is None
        ):
            _logger.warning(
                "Received data for child transaction with missing transaction values."
            )
            return self.env["payment.transaction"]

        converted_amount = payment_utils.minor_to_major_currency_units(
            amount,
            source_tx.currency_id,
            arbitrary_decimal_number=const.CURRENCY_DECIMALS.get(
                source_tx.currency_id.name
            ),
        )
        return source_tx._create_child_transaction(
            converted_amount, is_refund=is_refund, provider_reference=provider_reference
        )

    def _extract_amount_data(self, payment_data) -> dict | None:
        if self.provider_code != "adyen":
            return super()._extract_amount_data(payment_data)

        if (
            payment_data.get("action", {}).get("type") in ["redirect", "threeDS2"]
            or payment_data.get("resultCode") in const.RESULT_CODES_MAPPING["refused"]
        ):
            return None

        amount_data = payment_data.get("amount", {})
        amount = payment_utils.minor_to_major_currency_units(
            amount_data.get("value", 0),
            self.currency_id,
            arbitrary_decimal_number=const.CURRENCY_DECIMALS.get(self.currency_id.name),
        )
        currency_code = amount_data.get("currency")
        return {
            "amount": amount,
            "currency_code": currency_code,
            "precision_digits": const.CURRENCY_DECIMALS.get(self.currency_id.name),
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != "adyen":
            return super()._apply_updates(payment_data)

        event_code = payment_data.get("eventCode", "AUTHORISATION")

        if "pspReference" in payment_data and event_code in ["AUTHORISATION", "REFUND"]:
            self.provider_reference = payment_data.get("pspReference")

        payment_method_data = payment_data.get("paymentMethod", "")
        if isinstance(payment_method_data, dict):
            payment_method_type = payment_method_data["type"]
            if payment_method_type == "scheme":
                payment_method_code = payment_method_data["brand"]
            else:
                payment_method_code = payment_method_type
        else:
            payment_method_code = payment_method_data

        payment_method = self.env["payment.method"]._get_from_code(
            payment_method_code, mapping=const.PAYMENT_METHODS_MAPPING
        )
        self.payment_method_id = payment_method or self.payment_method_id

        payment_state = payment_data.get("resultCode")
        refusal_reason = payment_data.get("refusalReason") or payment_data.get("reason")
        if not payment_state:
            self._set_error(self.env._("Received data with missing payment state."))
        elif payment_state in const.RESULT_CODES_MAPPING["pending"]:
            self._set_pending()
        elif payment_state in const.RESULT_CODES_MAPPING["done"]:
            if not self.provider_id.capture_manually:
                self._set_done()
            elif event_code == "AUTHORISATION":
                self._set_authorized()
            else:
                self._set_done()

            if self.operation == "refund":
                self.env["ir.cron"]._trigger_ref("payment.cron_post_process_payment_tx")
        elif payment_state in const.RESULT_CODES_MAPPING["cancel"]:
            self._set_canceled()
        elif payment_state in const.RESULT_CODES_MAPPING["error"]:
            if event_code in ["AUTHORISATION", "REFUND"]:
                _logger.warning(
                    "The transaction %s underwent an error. reason: %s.",
                    self.reference,
                    refusal_reason,
                )
                self._set_error(
                    self.env._(
                        "An error occurred during the processing of your payment. Please try again."
                    )
                )
            elif event_code == "CANCELLATION":
                _logger.warning(
                    "The void of the transaction %s failed. reason: %s.",
                    self.reference,
                    refusal_reason,
                )
                if self.source_transaction_id:
                    self._set_error(
                        self.env._(
                            "The void of the transaction %s failed.", self.reference
                        )
                    )
                else:
                    self._log_message_on_linked_documents(
                        self.env._(
                            "The void of the transaction %s failed.", self.reference
                        )
                    )
            else:
                _logger.warning(
                    "The capture of the transaction %s failed. reason: %s.",
                    self.reference,
                    refusal_reason,
                )
                if self.source_transaction_id:
                    self._set_error(
                        self.env._(
                            "The capture of the transaction %s failed.", self.reference
                        )
                    )
                else:
                    self._log_message_on_linked_documents(
                        self.env._(
                            "The capture of the transaction %s failed.", self.reference
                        )
                    )
        elif payment_state in const.RESULT_CODES_MAPPING["refused"]:
            _logger.warning(
                "the transaction %s was refused. reason: %s",
                self.reference,
                refusal_reason,
            )
            self._set_error(self.env._("Your payment was refused. Please try again."))
        else:
            _logger.warning(
                "received data for transaction %s with invalid payment state: %s",
                self.reference,
                payment_state,
            )
            self._set_error(
                "Adyen: "
                + self.env._(
                    "Received data with invalid payment state: %s", payment_state
                )
            )
        return None

    def _extract_token_values(self, payment_data) -> dict:
        if self.provider_code != "adyen":
            return super()._extract_token_values(payment_data)

        additional_data = payment_data["additionalData"]

        if "recurring.recurringDetailReference" not in additional_data:
            return {}

        return {
            "provider_ref": additional_data["recurring.recurringDetailReference"],
            "payment_details": additional_data.get("cardSummary"),
            "adyen_shopper_reference": additional_data["recurring.shopperReference"],
        }
