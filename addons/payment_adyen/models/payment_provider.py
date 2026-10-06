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

    # === CRUD METHODS === #

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
        """Override of `payment` to return the default payment method codes."""
        self.check_singleton()
        if self.code != "adyen":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    @api.model
    def _adyen_extract_prefix_from_api_url(self, values) -> None:
        """Update the create or write values with the prefix extracted from the API URL.

        :param dict values: The create or write values.
        :return: None
        """
        if values.get("adyen_api_url_prefix"):  # Test if we're duplicating a provider.
            values["adyen_api_url_prefix"] = re.sub(
                r"(?:https://)?(\w+-\w+).*", r"\1", values["adyen_api_url_prefix"]
            )

    # === COMPUTE METHODS === #

    def _compute_feature_support_fields(self) -> None:
        """Override of `payment` to enable additional features."""
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "adyen").update(
            {
                "support_manual_capture": "partial",
                "support_refund": "partial",
                "support_tokenization": True,
            }
        )

    # === BUSINESS METHODS === #

    def _adyen_get_inline_form_values(self, pm_code, amount=None, currency=None):
        """Return a serialized JSON of the required values to render the inline form.

        Note: `self.check_singleton()`

        :param str pm_code: The code of the payment method whose inline form to render.
        :param float amount: The transaction amount.
        :param res.currency currency: The transaction currency.
        :return: The JSON serial of the required values to render the inline form.
        :rtype: str
        """
        self.check_singleton()

        inline_form_values = {
            "client_key": self.adyen_client_key,
            "adyen_pm_code": const.PAYMENT_METHODS_MAPPING.get(pm_code, pm_code),
            "formatted_amount": self._adyen_get_formatted_amount(amount, currency),
        }
        return json_dumps(inline_form_values)

    def _adyen_get_formatted_amount(self, amount=None, currency=None) -> dict:
        """Return the amount in the format required by Adyen.

        The formatted amount is a dict with keys 'value' and 'currency'.

        :param float amount: The transaction amount.
        :param res.currency currency: The transaction currency.
        :return: The Adyen-formatted amount.
        :rtype: dict
        """
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
        """Compute a unique reference of the partner for Adyen.

        This is used for the `shopperReference` field in communications with Adyen and stored in the
        `adyen_shopper_reference` field on `payment.token` if the payment method is tokenized.

        :param recordset partner_id: The partner making the transaction, as a `res.partner` id
        :return: The unique reference for the partner
        :rtype: str
        """
        return f"ODOO_PARTNER_{partner_id}"

    # === REQUEST HELPERS === #

    def _prepare_request_url(self, endpoint, *, endpoint_param=None, **kwargs):
        """Override of `payment` to build the request URL based on the API URL prefix.

        The final URL follows the pattern `<_base>/V<_version>/<_endpoint>`.
        """
        if self.code != "adyen":
            return super()._prepare_request_url(
                endpoint, endpoint_param=endpoint_param, **kwargs
            )

        version = const.API_ENDPOINT_VERSIONS[endpoint]
        endpoint = endpoint if not endpoint_param else endpoint.format(endpoint_param)
        prefix_ = self.adyen_api_url_prefix.rstrip(
            "/"
        )  # Remove potential trailing slash.
        endpoint = endpoint.lstrip("/")  # Remove potential leading slash.
        test_mode_ = self.state == "test"
        prefix_ = (
            f"{prefix_}.adyen"
            if test_mode_
            else f"{prefix_}-checkout-live.adyenpayments"
        )
        return f"https://{prefix_}.com/checkout/V{version}/{endpoint}"

    def _prepare_request_headers(self, method, *args, idempotency_key=None, **kwargs):
        """Override of `payment` to include the API key and idempotency key in the headers."""
        if self.code != "adyen":
            return super()._prepare_request_headers(
                method, *args, idempotency_key=idempotency_key, **kwargs
            )

        headers = {"X-API-Key": self.adyen_api_key}
        if method == "POST" and idempotency_key:
            headers["idempotency-key"] = idempotency_key
        return headers

    def _parse_response_error(self, response):
        """Override of `payment` to extract the error message from the response."""
        if self.code != "adyen":
            return super()._parse_response_error(response)
        return response.json().get("message", "")
