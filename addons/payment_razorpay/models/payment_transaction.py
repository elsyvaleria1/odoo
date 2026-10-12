import re
import time
from datetime import datetime
from urllib.parse import urlencode as url_encode

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools import consteq
from odoo.tools.urls import urljoin as url_join

from odoo.addons.integration.tools.admission import (
    Acknowledged,
    json_get,
    request_json_object,
)
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_razorpay import const
from odoo.addons.payment_razorpay.const import HANDLED_WEBHOOK_EVENTS
from odoo.addons.payment_razorpay.controllers.main import RazorpayController

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    razorpay_order_id = fields.Char(
        string="Razorpay Order ID",
        copy=False,
        readonly=True,
    )

    @api.model
    def _receiver_for_razorpay_return(self, **path_args) -> tuple:
        data = request.get_http_params()
        if not all(
            f"razorpay_{key}" in data for key in ("order_id", "payment_id", "signature")
        ):
            raise Acknowledged.redirect("/payment/status")
        tx, _extra = self._resolve_notification(
            "razorpay",
            {"description": data.get("reference")},
            Acknowledged.redirect("/payment/status"),
        )
        return tx, {"data": data}

    @api.model
    def _receiver_for_razorpay_webhook(self, **path_args):
        data = request_json_object()
        event_type = data.get("event")
        if event_type not in HANDLED_WEBHOOK_EVENTS:
            raise Acknowledged.json("")
        entity_type = "payment" if "payment" in event_type else "refund"
        entity = json_get(data, "payload", entity_type, "entity")
        entity_data = {
            **(entity if isinstance(entity, dict) else {}),
            "entity_type": entity_type,
        }
        return self._resolve_notification(
            "razorpay", entity_data, Acknowledged.json("")
        )

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        if self.provider_code != "razorpay":
            return super()._is_inbound_request_authentic(headers, body)
        if request.httprequest.method == "POST" and request.httprequest.is_json:
            return self._is_razorpay_signature_valid(
                body, headers.get("X-Razorpay-Signature"), is_redirect=False
            )
        data = request.get_http_params()
        return self._is_razorpay_signature_valid(data, data.get("razorpay_signature"))

    def _is_razorpay_signature_valid(
        self, payment_data, received_signature, is_redirect=True
    ) -> bool:
        self.check_singleton()
        if not received_signature:
            _logger.warning("Received payment data with missing signature.")
            return False
        expected_signature = self.provider_id._get_razorpay_signature(
            payment_data, is_redirect=is_redirect
        )
        if not consteq(received_signature, expected_signature):
            _logger.warning("Received payment data with invalid signature.")
            return False
        return True

    def _prepare_provider_processing_values(self, processing_values):
        if self.provider_code != "razorpay":
            return super()._prepare_provider_processing_values(processing_values)

        if self.operation in ("online_token", "offline"):
            return {}

        customer_id = self._razorpay_create_customer().get("id")
        order_id = self._razorpay_create_order(customer_id).get("id")
        processing_values = {
            "razorpay_key_id": self.provider_id.razorpay_key_id,
            "razorpay_public_token": self.provider_id.razorpay_public_token,
            "razorpay_customer_id": customer_id,
            "is_tokenize_request": self.tokenize,
            "razorpay_order_id": order_id,
        }
        if self.payment_method_id.code in const.REDIRECT_PAYMENT_METHOD_CODES:
            processing_values["callback_url"] = url_join(
                self.provider_id.get_base_url(),
                f"{RazorpayController._return_url}?{url_encode({'reference': self.reference})}",
            )

        return processing_values

    def _razorpay_create_customer(self):
        payload = {
            "name": self.partner_name,
            "email": self.partner_email or "",
            "contact": (
                self.partner_phone and self._format_phone_number(self.partner_phone)
            )
            or "",
            "fail_existing": "0",
        }
        customer_data = {}
        try:
            customer_data = self._send_api_request("POST", "customers", json=payload)
        except ValidationError as e:
            self._set_error(str(e))

        return customer_data

    @api.model
    def _format_phone_number(self, phone):
        if not phone and self.tokenize:
            raise ValidationError(self.env._("The phone number is missing."))

        try:
            phone = self._phone_format(
                number=phone,
                country=self.partner_country_id,
                raise_exception=self.tokenize,
            )
        except Exception as error:
            raise ValidationError(self.env._("The phone number is invalid.")) from error
        return phone

    def _razorpay_create_order(self, customer_id=None):
        payload = self._razorpay_prepare_order_payload(customer_id=customer_id)
        order_data = {}
        try:
            order_data = self._send_api_request("POST", "orders", json=payload)
        except ValidationError as e:
            self._set_error(str(e))
        else:
            self.razorpay_order_id = order_data.get("id")
        return order_data

    def _is_razorpay_payment_of_own_order(self, payment_data) -> bool:
        self.check_singleton()
        return (
            not self.razorpay_order_id
            or payment_data.get("order_id") == self.razorpay_order_id
        )

    def _razorpay_prepare_order_payload(self, customer_id=None):
        converted_amount = payment_utils.major_to_minor_currency_units(
            self.amount, self.currency_id
        )
        pm_code = (
            self.payment_method_id.primary_payment_method_id or self.payment_method_id
        ).code
        payload = {
            "amount": converted_amount,
            "currency": self.currency_id.name,
            **(
                {"method": pm_code}
                if pm_code not in const.FALLBACK_PAYMENT_METHOD_CODES
                else {}
            ),
        }
        if self.operation in ["online_direct", "validation"]:
            payload["customer_id"] = customer_id
            if self.tokenize:
                payload["token"] = {
                    "max_amount": payment_utils.major_to_minor_currency_units(
                        self._razorpay_get_mandate_max_amount(), self.currency_id
                    ),
                    "expire_at": time.mktime(
                        (datetime.today() + relativedelta(years=10)).timetuple()
                    ),
                    "frequency": "as_presented",
                }
        else:
            payload["payment_capture"] = not self.provider_id.capture_manually
        if self.provider_id.capture_manually:
            payload.update(
                {
                    "payment": {
                        "capture": "manual",
                        "capture_options": {
                            "manual_expiry_period": 7200,
                            "refund_speed": "normal",
                        },
                    },
                }
            )
        return payload

    def _razorpay_get_mandate_max_amount(self):
        pm_code = (
            self.payment_method_id.primary_payment_method_id or self.payment_method_id
        ).code
        pm_max_amount_INR = const.MANDATE_MAX_AMOUNT.get(pm_code, 100000)
        pm_max_amount = self._razorpay_convert_inr_to_currency(
            pm_max_amount_INR, self.currency_id
        )
        mandate_values = self._prepare_mandate_data()
        if "amount" in mandate_values and "MRR" in mandate_values:
            max_amount = min(
                pm_max_amount,
                max(mandate_values["amount"] * 1.5, mandate_values["MRR"] * 5),
            )
        else:
            max_amount = pm_max_amount
        return max_amount

    @api.model
    def _razorpay_convert_inr_to_currency(self, amount, currency_id):
        inr_currency = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search(
                [
                    ("name", "=", "INR"),
                ],
                limit=1,
            )
        )
        return inr_currency._convert(amount, currency_id)

    def _send_payment_request(self):
        if self.provider_code != "razorpay":
            return super()._send_payment_request()

        reference_prefix = re.sub(r"-(?!.*-).*$", "", self.reference) or self.reference
        earlier_pending_tx = self.search(
            [
                ("provider_code", "=", "razorpay"),
                ("state", "=", "pending"),
                ("token_id", "=", self.token_id.id),
                ("operation", "in", ["online_token", "offline"]),
                ("reference", "=like", f"{reference_prefix}%"),
                ("create_date", ">=", fields.Datetime.now() - relativedelta(hours=36)),
                ("id", "!=", self.id),
            ],
            limit=1,
        )
        if earlier_pending_tx:
            self._set_error(
                self.env._(
                    "Your last payment %s will soon be processed. Please wait up to 24 hours before"
                    " trying again, or use another payment method.",
                    earlier_pending_tx.reference,
                )
            )
            return None

        try:
            order_data = self._razorpay_create_order()
            phone = self._format_phone_number(self.partner_phone)
            customer_id, token_id = self.token_id.provider_ref.split(",")
            payload = {
                "email": self.partner_email,
                "contact": phone,
                "amount": order_data["amount"],
                "currency": self.currency_id.name,
                "order_id": order_data["id"],
                "customer_id": customer_id,
                "token": token_id,
                "description": self.reference,
                "recurring": "1",
            }
            recurring_payment_data = self._send_api_request(
                "POST", "payments/create/recurring", json=payload
            )
        except ValidationError as e:
            self._set_error(str(e))
        else:
            self._process("razorpay", recurring_payment_data)

    def _send_refund_request(self):
        if self.provider_code != "razorpay":
            return super()._send_refund_request()

        converted_amount = payment_utils.major_to_minor_currency_units(
            -self.amount, self.currency_id
        )
        payload = {
            "amount": converted_amount,
            "notes": {
                "reference": self.reference,
            },
        }
        response_content = self._send_api_request(
            "POST", f"payments/{self.provider_reference}/refund", json=payload
        )
        response_content.update(entity_type="refund")
        self._process("razorpay", response_content)
        return None

    def _send_capture_request(self):
        if self.provider_code != "razorpay":
            return super()._send_capture_request()

        converted_amount = payment_utils.major_to_minor_currency_units(
            self.amount, self.currency_id
        )
        payload = {"amount": converted_amount, "currency": self.currency_id.name}
        response_content = self._send_api_request(
            "POST", f"payments/{self.provider_reference}/capture", json=payload
        )

        self._process("razorpay", response_content)
        return None

    def _send_void_request(self):
        if self.provider_code != "razorpay":
            return super()._send_void_request()

        raise UserError(
            self.env._(
                "Transactions processed by Razorpay can't be manually voided from Odoo."
            )
        )

    @api.model
    def _search_by_reference(self, provider_code, payment_data):
        if provider_code != "razorpay":
            return super()._search_by_reference(provider_code, payment_data)

        field_name, value = self._razorpay_notified_lookup(payment_data)
        if not value:
            _logger.warning("Received data with missing reference.")
            return self
        tx = self._search_by_notified_value("razorpay", field_name, value)
        if (
            len(tx) == 1
            and payment_data.get("entity_type", "payment") == "payment"
            and not tx._is_razorpay_payment_of_own_order(payment_data)
        ):
            _logger.warning(
                "Payment %s of order %s is not of the order of transaction %s.",
                payment_data.get("id"),
                payment_data.get("order_id"),
                tx.reference,
            )
            return self.browse()
        if tx and field_name == "provider_reference":
            tx = self._search_by_notified_value(
                "razorpay", "provider_reference", payment_data.get("id")
            ) or self._razorpay_create_refund_tx_from_payment_data(tx, payment_data)
        return tx

    @api.model
    def _search_notification_subject(self, provider_code, payment_data):
        if provider_code != "razorpay":
            return super()._search_notification_subject(provider_code, payment_data)
        return self._search_by_notified_value(
            "razorpay", *self._razorpay_notified_lookup(payment_data)
        )

    @api.model
    def _razorpay_notified_lookup(self, payment_data):
        if payment_data.get("entity_type", "payment") == "payment":
            return "reference", payment_data.get("description")
        notes = payment_data.get("notes")
        reference = isinstance(notes, dict) and notes.get("reference")
        if reference:
            return "reference", reference
        return "provider_reference", payment_data.get("payment_id")

    def _razorpay_create_refund_tx_from_payment_data(self, source_tx, payment_data):
        refund_provider_reference = payment_data.get("id")
        amount_to_refund = payment_data.get("amount")
        if not refund_provider_reference or not amount_to_refund:
            raise ValidationError(self.env._("Received incomplete refund data."))

        converted_amount = payment_utils.minor_to_major_currency_units(
            amount_to_refund, source_tx.currency_id
        )
        return source_tx._create_child_transaction(
            converted_amount,
            is_refund=True,
            provider_reference=refund_provider_reference,
        )

    def _extract_amount_data(self, payment_data) -> dict | None:
        if self.provider_code != "razorpay":
            return super()._extract_amount_data(payment_data)

        if "amount" not in payment_data or "currency" not in payment_data:
            return None

        amount = payment_utils.minor_to_major_currency_units(
            payment_data["amount"], self.currency_id
        )
        return {
            "amount": amount,
            "currency_code": payment_data["currency"],
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != "razorpay":
            return super()._apply_updates(payment_data)

        if "id" in payment_data:
            entity_data = payment_data
        else:
            try:
                entity_data = self._send_api_request(
                    "GET", f"payments/{payment_data['razorpay_payment_id']}"
                )
            except ValidationError as e:
                self._set_error(str(e))
                return None

        entity_id = entity_data.get("id")
        if not entity_id:
            self._set_error(self.env._("Received data with missing entity id."))
            return None

        allowed_to_modify = self.state not in ("done", "authorized")
        if allowed_to_modify:
            self.provider_reference = entity_id

        payment_method_type = entity_data.get("method", "")
        if payment_method_type == "card":
            payment_method_type = entity_data.get("card", {}).get("network", "").lower()
        payment_method = self.env["payment.method"]._get_from_code(
            payment_method_type, mapping=const.PAYMENT_METHODS_MAPPING
        )
        if allowed_to_modify and payment_method:
            self.payment_method_id = payment_method

        entity_status = entity_data.get("status")
        if not entity_status:
            self._set_error(self.env._("Received data with missing status."))

        if entity_status in const.PAYMENT_STATUS_MAPPING["pending"]:
            self._set_pending()
        elif entity_status in const.PAYMENT_STATUS_MAPPING["authorized"]:
            if self.provider_id.capture_manually:
                self._set_authorized()
        elif entity_status in const.PAYMENT_STATUS_MAPPING["done"]:
            if (
                not self.token_id
                and entity_data.get("token_id")
                and self.provider_id.allow_tokenization
            ):
                self.tokenize = True
            self._set_done()

            if self.operation == "refund":
                self.env["ir.cron"]._trigger_ref("payment.cron_post_process_payment_tx")
        elif entity_status in const.PAYMENT_STATUS_MAPPING["error"]:
            _logger.warning(
                "The transaction %s underwent an error. Reason: %s",
                self.reference,
                entity_data.get("error_description"),
            )
            self._set_error(
                self.env._(
                    "An error occurred during the processing of your payment. Please try again."
                )
            )
        else:
            _logger.warning(
                "Received data for transaction %s with invalid payment status: %s.",
                self.reference,
                entity_status,
            )
            self._set_error(
                "Razorpay: "
                + self.env._("Received data with invalid status: %s", entity_status)
            )
        return None

    def _extract_token_values(self, payment_data) -> dict:
        if self.provider_code != "razorpay":
            return super()._extract_token_values(payment_data)

        has_token_data = payment_data.get("token_id")
        if (
            self.token_id
            or not self.provider_id.allow_tokenization
            or not has_token_data
        ):
            return {}

        pm_code = (
            self.payment_method_id.primary_payment_method_id or self.payment_method_id
        ).code
        if pm_code == "card":
            details = payment_data.get("card", {}).get("last4")
        elif pm_code == "upi":
            temp_vpa = payment_data.get("vpa")
            details = temp_vpa[temp_vpa.find("@") - 1 :]
        else:
            details = pm_code
        return {
            "payment_details": details,
            "provider_ref": f"{payment_data['customer_id']},{payment_data['token_id']}",
        }
