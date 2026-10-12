from datetime import timedelta
from urllib.parse import urlencode

from odoo import api, fields, models
from odoo.exceptions import RedirectWarning, ValidationError
from odoo.fields import Command
from odoo.libs.json import dumps as json_dumps
from odoo.tools.urls import urljoin

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.const import REPORT_REASONS_MAPPING
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_mercado_pago import const

_logger = get_payment_logger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"
    _CREDENTIAL_FIELDS = {
        "mercado_pago_access_token": "mercado_pago_access_token",
        "mercado_pago_refresh_token": "mercado_pago_refresh_token",
    }

    code = fields.Selection(
        selection_add=[("mercado_pago", "Mercado Pago")],
        ondelete={"mercado_pago": "set default"},
    )
    mercado_pago_account_country_id = fields.Many2one(
        comodel_name="res.country",
        inverse="_inverse_mercado_pago_account_country_id",
        copy=False,
        domain=[("code", "in", list(const.SUPPORTED_COUNTRIES))],
        required_if_provider="mercado_pago",
        help="The country of the Mercado Pago account. The currency will be updated to match the"
        " country of the Mercado Pago account.",
    )
    mercado_pago_is_oauth_supported = fields.Boolean(
        compute="_compute_mercado_pago_is_oauth_supported"
    )

    mercado_pago_access_token = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        groups="base.group_system",
    )
    mercado_pago_access_token_expiry = fields.Datetime(
        copy=False,
        groups="base.group_system",
    )
    mercado_pago_refresh_token = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        groups="base.group_system",
    )
    mercado_pago_public_key = fields.Char(
        copy=False,
        groups="base.group_system",
    )

    def _compute_feature_support_fields(self) -> None:
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "mercado_pago").update(
            {
                "support_tokenization": True,
            }
        )

    def _inverse_mercado_pago_account_country_id(self) -> None:
        for provider in self.filtered(
            lambda p: p.code == "mercado_pago" and p.mercado_pago_account_country_id
        ):
            currency_code = const.CURRENCY_MAPPING.get(
                self.mercado_pago_account_country_id.code
            )
            currency = (
                self.env["res.currency"]  # noqa: E8507 -- one lookup per provider, on its own account country
                .with_context(
                    active_test=False,
                )
                .search([("name", "=", currency_code)], limit=1)
            )
            provider.available_currency_ids = [Command.set(currency.ids)]

    def _compute_mercado_pago_is_oauth_supported(self) -> None:
        self.mercado_pago_is_oauth_supported = False

    @api.constrains("state", "mercado_pago_access_token")
    def _check_mercado_pago_credentials_are_set_before_enabling(self) -> None:
        for provider in self.filtered(
            lambda p: p.code == "mercado_pago" and p.state != "disabled"
        ):
            if not provider.mercado_pago_access_token:
                raise ValidationError(
                    self.env._(
                        'Mercado Pago credentials are missing. Click the "Connect" button to set up'
                        " your account."
                    )
                )

    @api.constrains("allow_tokenization", "mercado_pago_public_key")
    def _check_mercado_pago_credentials_are_set_before_allowing_tokenization(
        self,
    ) -> None:
        if any(
            p.code == "mercado_pago"
            and p.allow_tokenization
            and not p.mercado_pago_public_key
            for p in self
        ):
            raise ValidationError(
                self.env._("Connect your account before enabling tokenization.")
            )

    def _get_default_payment_method_codes(self):
        self.check_singleton()
        if self.code != "mercado_pago":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def action_start_onboarding(self, menu_id=None):
        self.check_singleton()

        if self.code != "mercado_pago":
            return super().action_start_onboarding(menu_id=menu_id)

        if self.company_id.country_id.code not in const.SUPPORTED_COUNTRIES:
            raise RedirectWarning(
                self.env._(
                    "Mercado Pago is not available in your country; please use another payment"
                    " provider."
                ),
                self.env.ref("payment.action_payment_provider").id,
                self.env._("Other Payment Providers"),
            )

        if not self.mercado_pago_account_country_id:
            raise ValidationError(
                self.env._("Set the account country before connecting the account.")
            )

        return_url_params = {"state": self._issue_onboarding_state()}
        return_url = urljoin(self.get_base_url(), const.OAUTH_RETURN_ROUTE)
        proxy_url_params = {
            "return_url": f"{return_url}?{urlencode(return_url_params)}",
            "account_country_code": self.mercado_pago_account_country_id.code.lower(),
        }
        proxy_url = self._prepare_request_url("/authorize", is_proxy_request=True)
        return {
            "type": "ir.actions.act_url",
            "url": f"{proxy_url}?{urlencode(proxy_url_params)}",
            "target": "self",
        }

    def _prepare_credential_reset_vals(self) -> dict:
        if self.code != "mercado_pago":
            return super()._prepare_credential_reset_vals()

        return {
            "mercado_pago_access_token": None,
            "mercado_pago_access_token_expiry": None,
            "mercado_pago_public_key": None,
            "mercado_pago_refresh_token": None,
            "allow_tokenization": False,
        }

    @api.model
    def _get_compatible_providers(
        self, *args, is_validation=False, report=None, **kwargs
    ):
        providers = super()._get_compatible_providers(
            *args, is_validation=is_validation, report=report, **kwargs
        )

        if is_validation:
            unfiltered_providers = providers
            providers = providers.filtered(lambda p: p.code != "mercado_pago")
            payment_utils.add_to_report(
                report,
                unfiltered_providers - providers,
                available=False,
                reason=REPORT_REASONS_MAPPING["validation_not_supported"],
            )

        return providers

    def _mercado_pago_get_inline_form_values(self, partner_id):
        self.check_singleton()

        partner = self.env["res.partner"].browse(partner_id).exists()
        inline_form_values = {
            "email": partner.email,
            "public_key": self.mercado_pago_public_key,
        }
        return json_dumps(inline_form_values)

    def _prepare_request_url(self, endpoint, *, is_proxy_request=False, **kwargs):
        if self.code != "mercado_pago":
            return super()._prepare_request_url(
                endpoint, is_proxy_request=is_proxy_request, **kwargs
            )

        if is_proxy_request:
            return urljoin(f"{const.PROXY_URL}/1", endpoint)

        return urljoin("https://api.mercadopago.com", endpoint)

    def _prepare_request_headers(
        self,
        method,
        *args,
        idempotency_key=None,
        is_proxy_request=False,
        is_refresh_token_request=False,
        **kwargs,
    ):
        if self.code != "mercado_pago":
            return super()._prepare_request_headers(
                method,
                *args,
                idempotency_key=idempotency_key,
                is_proxy_request=is_proxy_request,
                **kwargs,
            )

        headers = {
            "X-Platform-Id": "dev_cdf1cfac242111ef9fdebe8d845d0987",
        }
        if method == "POST" and idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        if not is_proxy_request and not is_refresh_token_request:
            access_token = self._mercado_pago_get_access_token()
            headers["Authorization"] = f"Bearer {access_token}"
        return headers

    def _mercado_pago_get_access_token(self):
        self.check_singleton()

        if self.mercado_pago_access_token and (
            not self.mercado_pago_access_token_expiry
            or self.mercado_pago_access_token_expiry >= fields.Datetime.now()
        ):
            return self.mercado_pago_access_token
        else:
            proxy_payload = self._prepare_json_rpc_payload(
                {
                    "refresh_token": self.mercado_pago_refresh_token,
                    "account_country_code": self.mercado_pago_account_country_id.code.lower(),
                }
            )
            response_content = self._send_api_request(
                "POST",
                "/refresh_access_token",
                json=proxy_payload,
                is_proxy_request=True,
                is_refresh_token_request=True,
            )
            expires_in = (
                fields.Datetime.now()
                + timedelta(seconds=int(response_content["expires_in"]))
                - timedelta(days=31)
            )
            self.write(
                {
                    "mercado_pago_access_token": response_content["access_token"],
                    "mercado_pago_access_token_expiry": expires_in,
                    "mercado_pago_refresh_token": response_content["refresh_token"],
                }
            )
            return self.mercado_pago_access_token

    def _parse_response_content(self, response, *, is_proxy_request=False, **kwargs):
        if self.code != "mercado_pago" or not is_proxy_request:
            return super()._parse_response_content(
                response, is_proxy_request=is_proxy_request, **kwargs
            )
        return self._parse_proxy_response(response)

    def _parse_response_error(self, response):
        if self.code != "mercado_pago":
            return super()._parse_response_error(response)
        return response.json().get("message", "")
