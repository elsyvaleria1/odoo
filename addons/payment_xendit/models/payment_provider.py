from odoo import fields, models

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_xendit import const

_logger = get_payment_logger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"
    _CREDENTIAL_FIELDS = {
        "xendit_secret_key": "xendit_secret_key",
        "xendit_webhook_token": "xendit_webhook_token",
    }

    code = fields.Selection(
        selection_add=[("xendit", "Xendit")],
        ondelete={"xendit": "set default"},
    )
    xendit_public_key = fields.Char(
        copy=False,
        required_if_provider="xendit",
        groups="base.group_system",
    )
    xendit_secret_key = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="xendit",
        groups="base.group_system",
    )
    xendit_webhook_token = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="xendit",
        groups="base.group_system",
    )

    def _compute_feature_support_fields(self) -> None:
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "xendit").support_tokenization = True

    def _get_supported_currencies(self):
        supported_currencies = super()._get_supported_currencies()
        if self.code == "xendit":
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        self.check_singleton()
        if self.code != "xendit":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _get_redirect_form_view(self, is_validation=False):
        self.check_singleton()

        if self.code == "xendit" and is_validation:
            return None
        return super()._get_redirect_form_view(is_validation)

    def _prepare_request_url(self, endpoint, **kwargs):
        if self.code != "xendit":
            return super()._prepare_request_url(endpoint, **kwargs)
        return f"https://api.xendit.co/{endpoint}"

    def _prepare_request_auth(self, **kwargs):
        if self.code != "xendit":
            return super()._prepare_request_auth(**kwargs)
        return self.xendit_secret_key, ""

    def _parse_response_error(self, response):
        if self.code != "xendit":
            return super()._parse_response_error(response)
        return response.json().get("message")
