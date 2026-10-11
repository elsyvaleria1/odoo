import re

from odoo import api, fields, models
from odoo.libs.json import dumps as json_dumps
from odoo.tools import consteq

from odoo.addons.integration.tools.admission import (
    Acknowledged,
    Refused,
    json_object,
    request_json_object,
)
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_adyen import const
from odoo.addons.payment_adyen import utils as adyen_utils

_logger = get_payment_logger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"
    _CREDENTIAL_FIELDS = {
        "adyen_api_key": "adyen_api_key",
        "adyen_hmac_key": "adyen_hmac_key",
    }

    code = fields.Selection(
        selection_add=[("adyen", "Adyen")],
        ondelete={"adyen": "set default"},
    )
    adyen_merchant_account = fields.Char(
        string="Merchant Account",
        copy=False,
        required_if_provider="adyen",
        groups="base.group_system",
        help="The code of the merchant account to use with this provider",
    )
    adyen_api_key = fields.Char(
        string="API Key",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="adyen",
        groups="base.group_system",
        help="The API key of the webservice user",
    )
    adyen_client_key = fields.Char(
        string="Client Key",
        copy=False,
        required_if_provider="adyen",
        help="The client key of the webservice user",
    )
    adyen_hmac_key = fields.Char(
        string="HMAC Key",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="adyen",
        groups="base.group_system",
        help="The HMAC key of the webhook",
    )
    adyen_api_url_prefix = fields.Char(
        string="API URL Prefix",
        copy=False,
        required_if_provider="adyen",
        help="The base URL for the API endpoints",
    )


    @api.model
    def _adyen_notification_items(self):
        items = request_json_object().get("notificationItems", [])
        if not isinstance(items, list):
            raise Refused(400, "notificationItems is not a JSON array", "invalid_json")
        return [
            json_object(
                json_object(item, "a notification item").get("NotificationRequestItem"),
                "NotificationRequestItem",
            )
            for item in items
        ]

    @api.model
    def _receiver_for_adyen_webhook(self, **path_args) -> tuple:
        items = []
        for payment_data in self._adyen_notification_items():
            tx = (
                self.env["payment.transaction"]
                .sudo()
                ._search_notification_subject("adyen", payment_data)
            )
            if tx:
                items.append((tx.provider_id, payment_data))
        if not items:
            raise Acknowledged.json("[accepted]")
        provider = items[0][0]
        own = [
            payment_data
            for item_provider, payment_data in items
            if item_provider == provider
        ]
        if len(own) != len(items):
            _logger.warning(
                "an Adyen notification batch names transactions of %d providers; "
                "only %s's are processed",
                len({item_provider for item_provider, _ in items}),
                provider.name,
            )
        return provider, {"items": own}

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        if self.code != "adyen":
            return super()._is_inbound_request_authentic(headers, body)
        verified = 0
        for payment_data in self._adyen_notification_items():
            tx = (
                self.env["payment.transaction"]
                .sudo()
                ._search_notification_subject("adyen", payment_data)
            )
            if tx.provider_id != self:
                continue
            if not self._is_adyen_notification_item_signature_valid(payment_data):
                return False
            verified += 1
        return verified > 0

    def _is_adyen_notification_item_signature_valid(self, payment_data) -> bool:
        self.check_singleton()
        additional_data = payment_data.get("additionalData")
        received_signature = isinstance(additional_data, dict) and additional_data.get(
            "hmacSignature"
        )
        if not received_signature:
            _logger.warning("received payment data with missing signature")
            return False
        expected_signature = adyen_utils.compute_notification_signature(
            payment_data, self.adyen_hmac_key
        )
        if not consteq(received_signature, expected_signature):
            _logger.warning("received payment data with invalid signature")
            return False
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self._adyen_extract_prefix_from_api_url(values)
        return super().create(vals_list)

    def write(self, vals):
        self._adyen_extract_prefix_from_api_url(vals)
        return super().write(vals)

    def _get_default_payment_method_codes(self):
        self.check_singleton()
        if self.code != "adyen":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    @api.model
    def _adyen_extract_prefix_from_api_url(self, values) -> None:
        if values.get("adyen_api_url_prefix"):
            values["adyen_api_url_prefix"] = re.sub(
                r"(?:https://)?(\w+-\w+).*", r"\1", values["adyen_api_url_prefix"]
            )


    def _compute_feature_support_fields(self) -> None:
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "adyen").update(
            {
                "support_manual_capture": "partial",
                "support_refund": "partial",
                "support_tokenization": True,
            }
        )


    def _adyen_get_inline_form_values(self, pm_code, amount=None, currency=None):
        self.check_singleton()

        inline_form_values = {
            "client_key": self.adyen_client_key,
            "adyen_pm_code": const.PAYMENT_METHODS_MAPPING.get(pm_code, pm_code),
            "formatted_amount": self._adyen_get_formatted_amount(amount, currency),
        }
        return json_dumps(inline_form_values)

    def _adyen_get_formatted_amount(self, amount=None, currency=None) -> dict:
        currency_code = currency and currency.name
        converted_amount = (
            amount
            and currency_code
            and payment_utils.major_to_minor_currency_units(
                amount, currency, const.CURRENCY_DECIMALS.get(currency_code)
            )
        )
        return {
            "value": converted_amount,
            "currency": currency_code,
        }

    def _adyen_compute_shopper_reference(self, partner_id) -> str:
        return f"ODOO_PARTNER_{partner_id}"


    def _prepare_request_url(self, endpoint, *, endpoint_param=None, **kwargs):
        if self.code != "adyen":
            return super()._prepare_request_url(
                endpoint, endpoint_param=endpoint_param, **kwargs
            )

        version = const.API_ENDPOINT_VERSIONS[endpoint]
        endpoint = endpoint if not endpoint_param else endpoint.format(endpoint_param)
        prefix_ = self.adyen_api_url_prefix.rstrip(
            "/"
        )
        endpoint = endpoint.lstrip("/")
        test_mode_ = self.state == "test"
        prefix_ = (
            f"{prefix_}.adyen"
            if test_mode_
            else f"{prefix_}-checkout-live.adyenpayments"
        )
        return f"https://{prefix_}.com/checkout/V{version}/{endpoint}"

    def _prepare_request_headers(self, method, *args, idempotency_key=None, **kwargs):
        if self.code != "adyen":
            return super()._prepare_request_headers(
                method, *args, idempotency_key=idempotency_key, **kwargs
            )

        headers = {"X-API-Key": self.adyen_api_key}
        if method == "POST" and idempotency_key:
            headers["idempotency-key"] = idempotency_key
        return headers

    def _parse_response_error(self, response):
        if self.code != "adyen":
            return super()._parse_response_error(response)
        return response.json().get("message", "")
