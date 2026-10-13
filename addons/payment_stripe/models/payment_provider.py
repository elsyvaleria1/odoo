from urllib.parse import urlencode as url_encode
from urllib.parse import urlsplit as url_parse

from odoo import api, fields, models
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.libs.json import dumps as json_dumps
from odoo.tools.urls import urljoin as url_join

from odoo.addons.payment import const as payment_const
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_stripe import const
from odoo.addons.payment_stripe import utils as stripe_utils
from odoo.addons.payment_stripe.controllers.main import StripeController
from odoo.addons.payment_stripe.controllers.onboarding import OnboardingController

_logger = get_payment_logger(__name__, const.SENSITIVE_KEYS)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"
    _CREDENTIAL_FIELDS = {
        "stripe_secret_key": "stripe_secret_key",
        "stripe_webhook_secret": "stripe_webhook_secret",
    }

    code = fields.Selection(
        selection_add=[("stripe", "Stripe")],
        ondelete={"stripe": "set default"},
    )
    stripe_publishable_key = fields.Char(
        string="Publishable Key",
        copy=False,
        required_if_provider="stripe",
        help="The key solely used to identify the account with Stripe",
    )
    stripe_secret_key = fields.Char(
        string="Secret Key",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        required_if_provider="stripe",
        groups="base.group_system",
    )
    stripe_webhook_secret = fields.Char(
        string="Webhook Signing Secret",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        groups="base.group_system",
        help="If a webhook is enabled on your Stripe account, this signing secret must be set to "
        "authenticate the messages sent from Stripe to Odoo.",
    )

    def _compute_feature_support_fields(self) -> None:
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "stripe").update(
            {
                "support_express_checkout": True,
                "support_manual_capture": "full_only",
                "support_refund": "partial",
                "support_tokenization": True,
            }
        )

    @api.constrains("state", "stripe_publishable_key", "stripe_secret_key")
    def _check_state_of_connected_account_is_never_test(self) -> None:
        for provider in self:
            if provider.state == "test" and provider._stripe_has_connected_account():
                raise ValidationError(
                    self.env._(
                        "You cannot set the provider to Test Mode while it is linked with your Stripe "
                        "account."
                    )
                )

    def _stripe_has_connected_account(self) -> bool:
        self.check_singleton()
        return False

    @api.constrains("state")
    def _check_onboarding_of_enabled_provider_is_completed(self) -> None:
        for provider in self:
            if provider.state == "enabled" and provider._stripe_onboarding_is_ongoing():
                raise ValidationError(
                    self.env._(
                        "You cannot set the provider state to Enabled until your onboarding to Stripe "
                        "is completed."
                    )
                )

    def _stripe_onboarding_is_ongoing(self) -> bool:
        self.check_singleton()
        return False

    def _get_default_payment_method_codes(self):
        self.check_singleton()
        if self.code != "stripe":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def action_start_onboarding(self, menu_id=None):
        self.check_singleton()

        if self.code != "stripe":
            return super().action_start_onboarding(menu_id=menu_id)

        if (
            self._stripe_get_country(self.env.company.country_id.code)
            not in payment_const.STRIPE_SUPPORTED_COUNTRIES
        ):
            raise RedirectWarning(
                self.env._(
                    "Stripe Connect is not available in your country, please use another payment"
                    " provider."
                ),
                self.env.ref("payment.action_payment_provider").id,
                self.env._("Other Payment Providers"),
            )

        if self.state == "enabled":
            action = {"type": "ir.actions.act_window_close"}
        else:
            connected_account = self._stripe_get_or_create_connected_account()

            if not menu_id:
                menu = self.env.ref(
                    "account_payment_provider.payment_provider_menu", False
                )
                menu_id = menu and menu.id

            account_link_url = self._stripe_create_account_link(
                connected_account["id"], menu_id
            )
            if account_link_url:
                action = {
                    "type": "ir.actions.act_url",
                    "url": account_link_url,
                    "target": "self",
                }
            else:
                action = {
                    "type": "ir.actions.act_window",
                    "model": "payment.provider",
                    "views": [[False, "form"]],
                    "res_id": self.id,
                }
        return action

    def action_stripe_create_webhook(self) -> dict:
        self.check_singleton()

        if self.stripe_webhook_secret:
            message = self.env._("Your Stripe Webhook is already set up.")
            notification_type = "warning"
        elif not self.stripe_secret_key:
            message = self.env._(
                "You cannot create a Stripe Webhook if your Stripe Secret Key is not set."
            )
            notification_type = "danger"
        else:
            webhook = self._send_api_request(
                "POST",
                "webhook_endpoints",
                data={
                    "url": self._get_stripe_webhook_url(),
                    "enabled_events[]": const.HANDLED_WEBHOOK_EVENTS,
                    "api_version": const.API_VERSION,
                },
            )
            self.stripe_webhook_secret = webhook.get("secret")
            message = self.env._("You Stripe Webhook was successfully set up!")
            notification_type = "info"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": message,
                "sticky": False,
                "type": notification_type,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_stripe_verify_apple_pay_domain(self) -> dict:
        self.check_singleton()

        web_domain = url_parse(self.get_base_url()).netloc
        response_content = self._send_api_request(
            "POST", "apple_pay/domains", data={"domain_name": web_domain}
        )
        if not response_content["livemode"]:
            raise UserError(
                self.env._("Please use live credentials to enable Apple Pay.")
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": self.env._("Your web domain was successfully verified."),
                "type": "success",
            },
        }

    def _get_stripe_webhook_url(self):
        return url_join(self.get_base_url(), StripeController._webhook_url)

    def _stripe_get_publishable_key(self):
        self.check_singleton()
        return stripe_utils.get_publishable_key(self.sudo())

    def _stripe_get_inline_form_values(
        self,
        amount,
        currency,
        partner_id,
        is_validation,
        payment_method_sudo=None,
        **kwargs,
    ):
        self.check_singleton()

        if not is_validation:
            currency_name = currency and currency.name.lower()
        else:
            currency_name = (
                self.with_context(validation_pm=payment_method_sudo)
                ._get_validation_currency()
                .name.lower()
            )
        partner = (
            self.env["res.partner"]
            .with_context(show_address=1)
            .browse(partner_id)
            .exists()
        )
        inline_form_values = {
            "publishable_key": self._stripe_get_publishable_key(),
            "currency_name": currency_name,
            "minor_amount": amount
            and payment_utils.major_to_minor_currency_units(
                amount,
                currency,
                arbitrary_decimal_number=const.CURRENCY_DECIMALS.get(currency.name),
            ),
            "capture_method": "manual" if self.capture_manually else "automatic",
            "billing_details": {
                "name": partner.name or "",
                "email": partner.email or "",
                "phone": partner._phone_get_number().number or "",
                "address": {
                    "line1": partner.street or "",
                    "line2": partner.street2 or "",
                    "city": partner.city or "",
                    "state": partner.state_id.code or "",
                    "country": partner.country_id.code or "",
                    "postal_code": partner.zip or "",
                },
            },
            "is_tokenization_required": (
                self.allow_tokenization
                and self._is_tokenization_required(**kwargs)
                and payment_method_sudo.support_tokenization
            ),
            "payment_methods_mapping": const.PAYMENT_METHODS_MAPPING,
        }
        return json_dumps(inline_form_values)

    def _stripe_get_country(self, country_code):
        return payment_const.STRIPE_COUNTRY_MAPPING.get(country_code, country_code)

    def _stripe_get_or_create_connected_account(self):
        proxy_payload = self._prepare_json_rpc_payload(
            self._stripe_prepare_connect_account_payload()
        )
        return self._send_api_request(
            "POST", "accounts", json=proxy_payload, is_proxy_request=True
        )

    def _stripe_prepare_connect_account_payload(self) -> dict:
        self.check_singleton()

        return {
            "type": "standard",
            "country": self._stripe_get_country(self.company_id.country_id.code),
            "email": self.company_id.email,
            "business_type": "company",
            "company[address][city]": self.company_id.city or "",
            "company[address][country]": self._stripe_get_country(
                self.company_id.country_id.code
            ),
            "company[address][line1]": self.company_id.street or "",
            "company[address][line2]": self.company_id.street2 or "",
            "company[address][postal_code]": self.company_id.zip or "",
            "company[address][state]": self.company_id.state_id.name or "",
            "company[name]": self.company_id.name,
            "business_profile[name]": self.company_id.name,
        }

    def _stripe_create_account_link(self, connected_account_id, menu_id):
        self.check_singleton()

        base_url = self.company_id.get_base_url()
        return_url = OnboardingController._onboarding_return_url
        refresh_url = OnboardingController._onboarding_refresh_url
        return_params = {"provider_id": self.id, "menu_id": menu_id}
        refresh_params = dict(**return_params, account_id=connected_account_id)

        payload = {
            "account": connected_account_id,
            "return_url": f"{url_join(base_url, return_url)}?{url_encode(return_params)}",
            "refresh_url": f"{url_join(base_url, refresh_url)}?{url_encode(refresh_params)}",
            "type": "account_onboarding",
        }
        proxy_payload = self._prepare_json_rpc_payload(payload)

        account_link = self._send_api_request(
            "POST", "account_links", json=proxy_payload, is_proxy_request=True
        )
        return account_link["url"]

    def _prepare_json_rpc_payload(self, data):
        res = super()._prepare_json_rpc_payload(data)
        if self.code != "stripe":
            return res
        res["params"] = {
            "payload": data,
            "proxy_data": self._stripe_prepare_proxy_data(stripe_payload=data),
        }
        return res

    def _stripe_prepare_proxy_data(self, stripe_payload=None) -> dict:
        self.check_singleton()

        return {}

    def _prepare_request_url(
        self, endpoint, *, is_proxy_request=False, version=1, **kwargs
    ):
        if self.code != "stripe":
            return super()._prepare_request_url(
                endpoint, is_proxy_request=is_proxy_request, version=version, **kwargs
            )
        if is_proxy_request:
            return url_join(const.PROXY_URL, f"{version}/{endpoint}")
        return url_join("https://api.stripe.com/v1/", endpoint)

    def _prepare_request_headers(
        self, method, *args, idempotency_key=None, is_proxy_request=False, **kwargs
    ):
        if self.code != "stripe":
            return super()._prepare_request_headers(
                method,
                *args,
                idempotency_key=idempotency_key,
                is_proxy_request=is_proxy_request,
                **kwargs,
            )

        if is_proxy_request:
            return {}

        headers = {
            "AUTHORIZATION": f"Bearer {stripe_utils.get_secret_key(self)}",
            "Stripe-Version": const.API_VERSION,
            **self._get_stripe_extra_request_headers(),
        }
        if method == "POST" and idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _parse_response_error(self, response):
        if self.code != "stripe":
            return super()._parse_response_error(response)
        return response.json().get("error", {}).get("message", "")

    def _parse_response_content(self, response, *, is_proxy_request=False, **kwargs):
        if self.code != "stripe" or not is_proxy_request:
            return super()._parse_response_content(
                response, is_proxy_request=is_proxy_request, **kwargs
            )
        return self._parse_proxy_response(response)

    def _get_stripe_extra_request_headers(self) -> dict:
        return {}
