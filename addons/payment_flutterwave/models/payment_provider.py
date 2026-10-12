from odoo import api, fields, models
from odoo.tools.urls import urljoin as url_join

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.const import REPORT_REASONS_MAPPING
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_flutterwave import const

_logger = get_payment_logger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"
    _CREDENTIAL_FIELDS = {
        "flutterwave_secret_key": "flutterwave_secret_key",
        "flutterwave_webhook_secret": "flutterwave_webhook_secret",
    }

    code = fields.Selection(
        selection_add=[("flutterwave", "Flutterwave")],
        ondelete={"flutterwave": "set default"},
    )
    flutterwave_public_key = fields.Char(
        copy=False,
        required_if_provider="flutterwave",
        help="The key solely used to identify the account with Flutterwave.",
    )
    flutterwave_secret_key = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="flutterwave",
        groups="base.group_system",
    )
    flutterwave_webhook_secret = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="flutterwave",
        groups="base.group_system",
    )

    def _compute_feature_support_fields(self) -> None:
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "flutterwave").update(
            {
                "support_tokenization": True,
            }
        )

    def _get_supported_currencies(self):
        supported_currencies = super()._get_supported_currencies()
        if self.code == "flutterwave":
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        self.check_singleton()
        if self.code != "flutterwave":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    @api.model
    def _get_compatible_providers(
        self, *args, is_validation=False, report=None, **kwargs
    ):
        providers = super()._get_compatible_providers(
            *args, is_validation=is_validation, report=report, **kwargs
        )

        if is_validation:
            unfiltered_providers = providers
            providers = providers.filtered(lambda p: p.code != "flutterwave")
            payment_utils.add_to_report(
                report,
                unfiltered_providers - providers,
                available=False,
                reason=REPORT_REASONS_MAPPING["validation_not_supported"],
            )

        return providers

    def _prepare_request_url(self, endpoint, **kwargs):
        if self.code != "flutterwave":
            return super()._prepare_request_url(endpoint, **kwargs)
        return url_join("https://api.flutterwave.com/v3/", endpoint)

    def _prepare_request_headers(self, *args, **kwargs):
        if self.code != "flutterwave":
            return super()._prepare_request_headers(*args, **kwargs)
        return {"Authorization": f"Bearer {self.flutterwave_secret_key}"}

    def _parse_response_error(self, response):
        if self.code != "flutterwave":
            return super()._parse_response_error(response)
        return response.json().get("message", "")

    def _parse_response_content(self, response, **kwargs):
        if self.code != "flutterwave":
            return super()._parse_response_content(response, **kwargs)
        return response.json()["data"]
