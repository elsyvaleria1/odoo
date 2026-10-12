import uuid
from json.decoder import JSONDecodeError
from pprint import pformat

import requests

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tools import (
    consume_session_state,
    issue_session_state,
    register_signed_scope,
)
from odoo.tools.mail import is_html_empty

from odoo.addons.integration.tools.connection_gate import ConnectionUnavailable
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.const import REPORT_REASONS_MAPPING, SENSITIVE_KEYS
from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__, sensitive_keys=SENSITIVE_KEYS)
_debug = DebugLog(__name__)

ONBOARDING_STATE_MAX_AGE_SECONDS = 3600

ONBOARDING_STATE_SCOPE = register_signed_scope(
    "payment.onboarding_state",
    purpose="the state an onboarding carries through the provider's OAuth proxy back "
    "to its return route: the provider and company the authorization connects, bound "
    "to the database, the user and the browser session that started it",
    lifetime=f"its expiry: the return route refuses a state older than "
    f"{ONBOARDING_STATE_MAX_AGE_SECONDS} seconds, or one already consumed",
)


class PaymentProvider(models.Model):
    _name = "payment.provider"
    _inherit = ["mixin.credential.holder", "mixin.integration.connected"]
    _description = "Payment Provider"
    _order = "module_state, state desc, sequence, name"
    _check_company_auto = True
    _check_company_domain = models.check_company_domain_parent_of
    _credential_holder_field = "provider_credential_id"
    _credential_purpose = "payment:provider"

    def _is_valid_field_parameter(self, field, name) -> bool:
        return name == "required_if_provider" or super()._is_valid_field_parameter(
            field, name
        )

    name = fields.Char(
        translate=True,
        required=True,
    )
    sequence = fields.Integer(help="Define the display order")
    provider_credential_id = fields.Many2one(
        comodel_name="credential.credential",
        string="Credential",
        copy=False,
        ondelete="restrict",
        groups="base.group_system",
        help="Holds this provider's secrets.",
    )
    code = fields.Selection(
        selection=[("none", "No Provider Set")],
        default="none",
        required=True,
        help="The technical code of this payment provider.",
    )
    state = fields.Selection(
        selection=[
            ("disabled", "Disabled"),
            ("enabled", "Enabled"),
            ("test", "Test Mode"),
        ],
        default="disabled",
        copy=False,
        required=True,
        help="In test mode, a fake payment is processed through a test payment interface.\n"
        "This mode is advised when setting up the provider.",
    )
    is_published = fields.Boolean(
        string="Published",
        copy=False,
        help="Whether the provider is visible on the website or not. Tokens remain functional but "
        "are only visible on manage forms.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company.id,
        index=True,
        required=True,
    )
    main_currency_id = fields.Many2one(
        related="company_id.currency_id",
        help="The main currency of the company, used to display monetary fields.",
    )
    payment_method_ids = fields.Many2many(
        comodel_name="payment.method",
        string="Supported Payment Methods",
    )
    allow_tokenization = fields.Boolean(
        string="Allow Saving Payment Methods",
        help="This controls whether customers can save their payment methods as payment tokens.\n"
        "A payment token is an anonymous link to the payment method details saved in the\n"
        "provider's database, allowing the customer to reuse it for a next purchase.",
    )
    capture_manually = fields.Boolean(
        string="Capture Amount Manually",
        help="Capture the amount from Odoo, when the delivery is completed.\n"
        "Use this if you want to charge your customers cards only when\n"
        "you are sure you can ship the goods to them.",
    )
    allow_express_checkout = fields.Boolean(
        help="This controls whether customers can use express payment methods. Express checkout "
        "enables customers to pay with Google Pay and Apple Pay from which address "
        "information is collected at payment."
    )
    redirect_form_view_id = fields.Many2one(
        comodel_name="ir.ui.view",
        string="Redirect Form Template",
        domain=[("type", "=", "qweb")],
        ondelete="restrict",
        help="The template rendering a form submitted to redirect the user when making a payment",
    )
    inline_form_view_id = fields.Many2one(
        comodel_name="ir.ui.view",
        string="Inline Form Template",
        domain=[("type", "=", "qweb")],
        ondelete="restrict",
        help="The template rendering the inline payment form when making a direct payment",
    )
    token_inline_form_view_id = fields.Many2one(
        comodel_name="ir.ui.view",
        string="Token Inline Form Template",
        domain=[("type", "=", "qweb")],
        ondelete="restrict",
        help="The template rendering the inline payment form when making a payment by token.",
    )
    express_checkout_form_view_id = fields.Many2one(
        comodel_name="ir.ui.view",
        string="Express Checkout Form Template",
        domain=[("type", "=", "qweb")],
        ondelete="restrict",
        help="The template rendering the express payment methods' form.",
    )

    available_country_ids = fields.Many2many(
        comodel_name="res.country",
        relation="payment_country_rel",
        column1="payment_id",
        column2="country_id",
        string="Countries",
        help="The countries in which this payment provider is available. Leave blank to make it "
        "available in all countries.",
    )
    available_currency_ids = fields.Many2many(
        comodel_name="res.currency",
        relation="payment_currency_rel",
        column1="payment_provider_id",
        column2="currency_id",
        string="Currencies",
        compute="_compute_available_currency_ids",
        store=True,
        readonly=False,
        context={"active_test": False},
        help="The currencies available with this payment provider. Leave empty not to restrict "
        "any.",
    )
    maximum_amount = fields.Monetary(
        currency_field="main_currency_id",
        help="The maximum payment amount that this payment provider is available for. Leave blank "
        "to make it available for any payment amount.",
    )

    pre_msg = fields.Html(
        string="Help Message",
        translate=True,
        help="The message displayed to explain and help the payment process",
    )
    pending_msg = fields.Html(
        string="Pending Message",
        translate=True,
        default=lambda self: self.env._(
            "Your payment has been processed but is waiting for approval."
        ),
        help="The message displayed if the order pending after the payment process",
    )
    auth_msg = fields.Html(
        string="Authorize Message",
        translate=True,
        default=lambda self: self.env._("Your payment has been authorized."),
        help="The message displayed if payment is authorized",
    )
    done_msg = fields.Html(
        string="Done Message",
        translate=True,
        default=lambda self: self.env._("Your payment has been processed."),
        help="The message displayed if the order is successfully done after the payment process",
    )
    cancel_msg = fields.Html(
        string="Cancelled Message",
        translate=True,
        default=lambda self: self.env._("Your payment has been cancelled."),
        help="The message displayed if the order is cancelled during the payment process",
    )

    support_tokenization = fields.Boolean(
        string="Tokenization",
        compute="_compute_feature_support_fields",
    )
    support_manual_capture = fields.Selection(
        selection=[("full_only", "Full Only"), ("partial", "Partial")],
        string="Manual Capture Supported",
        compute="_compute_feature_support_fields",
    )
    support_express_checkout = fields.Boolean(
        string="Express Checkout",
        compute="_compute_feature_support_fields",
    )
    support_refund = fields.Selection(
        selection=[
            ("none", "Unsupported"),
            ("full_only", "Full Only"),
            ("partial", "Full & Partial"),
        ],
        string="Refund",
        compute="_compute_feature_support_fields",
        help="Refund is a feature allowing to refund customers directly from the payment in Odoo.",
    )

    image_128 = fields.Image(
        string="Image",
        max_width=128,
        max_height=128,
    )
    color = fields.Integer(
        compute="_compute_color",
        store=True,
        help="The color of the card in kanban view",
    )

    module_id = fields.Many2one(
        comodel_name="ir.module.module",
        string="Corresponding Module",
    )
    module_state = fields.Selection(
        related="module_id.state",
        string="Installation State",
    )
    module_to_buy = fields.Boolean(
        related="module_id.to_buy",
        string="Odoo Enterprise Module",
    )

    @api.depends("code")
    def _compute_available_currency_ids(self) -> None:
        all_currencies = (
            self.env["res.currency"].with_context(active_test=False).search([])
        )
        for provider in self:
            supported_currencies = provider._get_supported_currencies()
            if supported_currencies < all_currencies:
                provider.available_currency_ids = supported_currencies
            else:
                provider.available_currency_ids = None

    def _get_supported_currencies(self):
        self.check_singleton()
        return self.env["res.currency"].with_context(active_test=False).search([])

    @api.depends("state", "module_state")
    def _compute_color(self) -> None:
        for provider in self:
            if provider.module_id and provider.module_state != "installed":
                provider.color = 4
            elif provider.state == "disabled":
                provider.color = 3
            elif provider.state == "test":
                provider.color = 2
            elif provider.state == "enabled":
                provider.color = 7

    @api.depends("code")
    def _compute_feature_support_fields(self) -> None:
        self.update(
            {
                "support_express_checkout": None,
                "support_manual_capture": None,
                "support_tokenization": None,
                "support_refund": "none",
            }
        )

    @api.onchange("state")
    def _onchange_state_switch_is_published(self) -> None:
        self.is_published = self.state == "enabled"

    @api.onchange("state")
    def _onchange_state_warn_before_disabling_tokens(self) -> dict | None:
        if (
            self._origin.state in ("test", "enabled")
            and self._origin.state != self.state
        ):
            related_tokens = self.env["payment.token"].search(
                [("provider_id", "=", self._origin.id)]
            )
            if related_tokens:
                return {
                    "warning": {
                        "title": self.env._("Warning"),
                        "message": self.env._(
                            "This action will also archive %s tokens that are registered with this "
                            "provider. ",
                            len(related_tokens),
                        ),
                    }
                }
        return None

    @api.onchange("company_id")
    def _onchange_company_block_if_existing_transactions(self) -> None:
        if self._origin.company_id != self.company_id and self.env[
            "payment.transaction"
        ].search_count([("provider_id", "=", self._origin.id)], limit=1):
            raise UserError(
                self.env._(
                    "You cannot change the company of a payment provider with existing transactions."
                )
            )

    def _check_available_currency_ids(self) -> None:
        pass

    def _check_single_available_currency(self, error_message: str) -> None:
        for provider in self:
            if (
                provider.state != "disabled"
                and len(provider.available_currency_ids) > 1
            ):
                raise ValidationError(error_message)

    @api.constrains("capture_manually")
    def _check_manual_capture_supported_by_payment_methods(self) -> None:
        if self.capture_manually:
            incompatible_pms = self.payment_method_ids.filtered(
                lambda method: method.active and method.support_manual_capture == "none"
            )
            if incompatible_pms:
                raise ValidationError(
                    self.env._(
                        "The following payment methods must be disabled in order to enable manual"
                        " capture: %s",
                        ", ".join(incompatible_pms.mapped("name")),
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        providers = super().create(vals_list)
        providers._check_required_if_provider()
        if any(provider.state != "disabled" for provider in providers):
            self._toggle_post_processing_cron()
        return providers

    def write(self, vals):
        deactivated_providers = self.env["payment.provider"]
        activated_providers = self.env["payment.provider"]
        if "state" in vals:
            state_changed_providers = self.filtered(
                lambda p: p.state not in ("disabled", vals["state"])
            )
            state_changed_providers._archive_linked_tokens()
            if vals["state"] == "disabled":
                deactivated_providers = state_changed_providers
            else:
                activated_providers = self.filtered(lambda p: p.state == "disabled")

        result = super().write(vals)
        self._check_required_if_provider()

        deactivated_providers._deactivate_unsupported_payment_methods()
        activated_providers._activate_default_pms()
        if activated_providers or deactivated_providers:
            self._toggle_post_processing_cron()

        return result

    def _check_required_if_provider(self) -> None:
        field_names = []
        enabled_providers = self.filtered(lambda p: p.state in ["enabled", "test"])
        for field_name, field in self._fields.items():
            required_for_provider_code = getattr(field, "required_if_provider", None)
            if required_for_provider_code and any(
                required_for_provider_code == provider._get_code()
                and not provider[field_name]
                for provider in enabled_providers
            ):
                ir_field = self.env["ir.model.fields"]._get(self._name, field_name)
                field_names.append(ir_field.field_description)
        if field_names:
            raise ValidationError(
                self.env._(
                    "The following fields must be filled: %s", ", ".join(field_names)
                )
            )

    @api.model
    def _toggle_post_processing_cron(self) -> None:
        post_processing_cron = self.env.ref(
            "payment.cron_post_process_payment_tx", raise_if_not_found=False
        )
        if post_processing_cron:
            any_active_provider = bool(
                self.sudo().search_count([("state", "!=", "disabled")], limit=1)
            )
            post_processing_cron.active = any_active_provider

    def _archive_linked_tokens(self) -> None:
        self.env["payment.token"].search([("provider_id", "in", self.ids)]).write(
            {"active": False}
        )

    def _deactivate_unsupported_payment_methods(self) -> None:
        unsupported_pms = self.payment_method_ids.filtered(
            lambda pm: all(p.state == "disabled" for p in pm.provider_ids)
        )
        (unsupported_pms + unsupported_pms.brand_ids).active = False

    def _activate_default_pms(self) -> None:
        manual_capture_providers = self.env["payment.provider"].search(
            [("state", "in", ["enabled", "test"]), ("capture_manually", "=", True)]
        )
        compatible_pms = self.with_context(
            active_test=False
        ).payment_method_ids.filtered(
            lambda pm: (
                not pm.provider_ids & manual_capture_providers
                or pm.support_manual_capture != "none"
            )
        )
        default_pm_codes = {
            code for p in self for code in p._get_default_payment_method_codes()
        }
        pms_to_activate = (compatible_pms + compatible_pms.brand_ids).filtered(
            lambda pm: pm.code in default_pm_codes
        )
        pms_to_activate.active = True

    def _get_default_payment_method_codes(self):
        self.check_singleton()
        return set()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_master_data(self) -> None:
        external_ids = self.get_external_id()
        for provider in self:
            external_id = external_ids[provider.id]
            if external_id and not external_id.startswith("__export__"):
                raise UserError(
                    self.env._(
                        "You cannot delete the payment provider %s; disable it or uninstall it"
                        " instead.",
                        provider.name,
                    )
                )

    def button_immediate_install(self):
        if self.module_id and self.module_state != "installed":
            self.module_id.button_immediate_install()
            return {
                "type": "ir.actions.client",
                "tag": "reload",
            }
        return None

    def action_start_onboarding(self, menu_id=None):
        return {}

    def _issue_onboarding_state(self) -> str:
        self.check_singleton()
        self.check_access("write")
        return issue_session_state(
            self.env,
            ONBOARDING_STATE_SCOPE,
            request.session,
            {"provider_id": self.id, "company_id": self.company_id.id},
            max_age_seconds=ONBOARDING_STATE_MAX_AGE_SECONDS,
        )

    @api.model
    def _consume_onboarding_state(self, code, state, query_provider_id=None):
        claims = consume_session_state(
            self.env, ONBOARDING_STATE_SCOPE, request.session, state
        )
        provider = self.browse()
        if claims is not None and query_provider_id in (
            None,
            str(claims["provider_id"]),
        ):
            provider = (
                self.with_company(claims["company_id"])
                .browse(claims["provider_id"])
                .exists()
            )
        if (
            not provider
            or provider.code != code
            or provider.company_id.id != claims["company_id"]
        ):
            _debug.logic(
                "payment.onboarding_state_refused",
                code=code,
                signed=claims is not None,
                provider=provider.id or None,
            )
            raise AccessError(
                self.env._(
                    "This onboarding link is invalid, has expired or was already "
                    "used. Start the onboarding again from the provider form."
                )
            )
        provider.check_access("write")
        return provider

    def action_reset_credentials(self):
        self.check_singleton()

        return self.write(
            {
                "state": "disabled",
                "is_published": False,
                **self._prepare_credential_reset_vals(),
            }
        )

    def _prepare_credential_reset_vals(self) -> dict:
        return {}

    def action_toggle_is_published(self) -> None:
        if self.state == "disabled" and not self.is_published:
            raise UserError(self.env._("You cannot publish a disabled provider."))
        self.is_published = not self.is_published

    def action_view_payment_methods(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Payment Methods"),
            "res_model": "payment.method",
            "view_mode": "list,kanban,form",
            "domain": [
                (
                    "id",
                    "in",
                    self.with_context(active_test=False).payment_method_ids.ids,
                )
            ],
            "context": {"active_test": False, "create": False},
        }

    @api.model
    def _get_compatible_providers(
        self,
        company_id,
        partner_id,
        amount,
        currency_id=None,
        force_tokenization=False,
        is_express_checkout=False,
        is_validation=False,
        report=None,
        **kwargs,
    ):
        providers = self.env["payment.provider"].search(
            [
                *self.env["payment.provider"]._check_company_domain(company_id),
                ("state", "in", ["enabled", "test"]),
            ]
        )
        payment_utils.add_to_report(report, providers)

        if not self.env.user._is_internal():
            providers = providers.filtered("is_published")

        partner = self.env["res.partner"].browse(partner_id)
        if partner.country_id:
            unfiltered_providers = providers
            providers = providers.filtered(
                lambda p: (
                    not p.available_country_ids
                    or partner.country_id.id in p.available_country_ids.ids
                )
            )
            payment_utils.add_to_report(
                report,
                unfiltered_providers - providers,
                available=False,
                reason=REPORT_REASONS_MAPPING["incompatible_country"],
            )

        currency = self.env["res.currency"].browse(currency_id).exists()
        if not is_validation and currency:
            company = self.env["res.company"].browse(company_id).exists()
            date = fields.Date.context_today(self)
            converted_amount = currency._convert(
                amount, company.currency_id, company, date
            )
            unfiltered_providers = providers
            providers = providers.filtered(
                lambda p: (
                    not p.maximum_amount
                    or currency.compare_amounts(p.maximum_amount, converted_amount)
                    != -1
                )
            )
            payment_utils.add_to_report(
                report,
                unfiltered_providers - providers,
                available=False,
                reason=REPORT_REASONS_MAPPING["exceed_max_amount"],
            )

        if currency:
            unfiltered_providers = providers
            providers = providers.filtered(
                lambda p: (
                    not p.available_currency_ids
                    or currency.id in p.available_currency_ids.ids
                )
            )
            payment_utils.add_to_report(
                report,
                unfiltered_providers - providers,
                available=False,
                reason=REPORT_REASONS_MAPPING["incompatible_currency"],
            )

        if force_tokenization or self._is_tokenization_required(**kwargs):
            unfiltered_providers = providers
            providers = providers.filtered("allow_tokenization")
            payment_utils.add_to_report(
                report,
                unfiltered_providers - providers,
                available=False,
                reason=REPORT_REASONS_MAPPING["tokenization_not_supported"],
            )

        if is_express_checkout:
            unfiltered_providers = providers
            providers = providers.filtered("allow_express_checkout")
            payment_utils.add_to_report(
                report,
                unfiltered_providers - providers,
                available=False,
                reason=REPORT_REASONS_MAPPING["express_checkout_not_supported"],
            )

        return providers

    def _is_tokenization_required(self, **kwargs) -> bool:
        return False

    def _is_inline_form_required(self, is_validation=False) -> bool:
        return True

    def _get_validation_amount(self):
        self.check_singleton()
        return 0.0

    def _get_validation_currency(self):
        self.check_singleton()

        provider_currencies = self.available_currency_ids
        pm = self.env.context.get("validation_pm")
        pm_currencies = (
            self.env["res.currency"] if not pm else pm.supported_currency_ids
        )
        validation_currency = None
        if provider_currencies and pm_currencies:
            validation_currency = (provider_currencies & pm_currencies)[:1]
        elif provider_currencies and not pm_currencies:
            validation_currency = provider_currencies[:1]
        elif not provider_currencies and pm_currencies:
            validation_currency = pm_currencies[:1]
        if not validation_currency:
            validation_currency = self.company_id.currency_id
        return validation_currency

    def _get_redirect_form_view(self, is_validation=False):
        self.check_singleton()
        return self.redirect_form_view_id

    def _integration_connection_service(self) -> tuple[str, str, str]:
        self.check_singleton()
        label = dict(self._fields["code"]._description_selection(self.env)).get(
            self.code, self.code
        )
        return f"payment_{self.code}", self.env._("Payments: %s", label), "payment"

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        self.check_singleton()
        return False

    def _send_api_request(
        self,
        method,
        endpoint,
        *,
        params=None,
        data=None,
        json=None,
        reference=None,
        timeout=10,
        **kwargs,
    ):
        self.check_singleton()

        url = self._prepare_request_url(endpoint, **kwargs)
        body = json_dumps_bytes(json) if json is not None else data
        headers = self._prepare_request_headers(
            method, endpoint, params or body, **kwargs
        )
        if json is not None:
            headers = {"Content-Type": "application/json", **headers}
        auth = self._prepare_request_auth(**kwargs)

        self._log_request(method, url, params or data or json, reference=reference)

        try:
            response = self._get_integration_connection()._egress_request(
                method,
                url,
                purpose=f"payment_{self.code}",
                params=params,
                data=body,
                headers=headers,
                auth=auth,
                timeout=timeout,
            )
        except ConnectionUnavailable as error:
            raise ValidationError(str(error)) from None
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.InvalidURL,
        ):
            raise ValidationError(
                self.env._(
                    "Could not establish the connection to the payment provider."
                )
            ) from None

        self._log_response(response, reference=reference)

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            try:
                error_msg = self._parse_response_error(response)
            except JSONDecodeError:
                error_msg = response.text
            raise ValidationError(
                self.env._("The payment provider rejected the request.\n%s", error_msg)
            ) from None
        return self._parse_response_content(response, **kwargs)

    def _prepare_request_url(self, endpoint, **kwargs):
        return ""

    def _prepare_request_headers(self, method, endpoint, payload, **kwargs):
        return {}

    def _prepare_request_auth(self, **kwargs):
        return ()

    def _log_request(self, method, url, payload, *, reference=None) -> None:
        if reference:
            log_msg = (
                "Sending %(method)s API request to %(url)s for transaction %(ref)s."
            )
            log_values = {"method": method, "url": url, "ref": reference}
        else:
            log_msg = "Sending %(method)s API request to %(url)s for provider %(p_id)s."
            log_values = {"method": method, "url": url, "p_id": self.id}

        if payload:
            log_msg += " Payload:\n%(payload)s"
            log_values["payload"] = pformat(payload)

        _logger.info(log_msg, log_values)

    def _log_response(self, response, *, reference=None) -> None:
        if reference:
            log_msg = (
                "Received HTTP %(code)s %(status)s API response from %(url)s for transaction"
                " %(ref)s.\n%(data)s"
            )
        else:
            log_msg = (
                "Received HTTP %(code)s %(status)s API response from %(url)s for provider %(p_id)s."
                "\n%(data)s"
            )
        log_values = {
            "code": response.status_code,
            "status": response.reason,
            "url": response.url,
            "ref": reference,
            "p_id": self.id,
            "data": response.text,
        }
        if response.ok:
            _logger.info(log_msg, log_values)
        else:
            _logger.error(log_msg, log_values)

    def _parse_response_content(self, response, **kwargs):
        return response.json()

    def _parse_response_error(self, response):
        return response.text

    def _prepare_json_rpc_payload(self, data):
        return {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex,
            "method": "call",
            "params": data,
        }

    def _parse_proxy_response(self, response):
        response_content = response.json()
        if response_content.get("error"):
            error_data = response_content["error"]["data"]
            raise ValidationError(
                self.env._(
                    "The payment provider rejected the request.\n%s",
                    pformat(error_data["message"]),
                )
            )
        return response_content["result"]

    @api.model
    def _setup_provider(self, provider_code, **kwargs) -> None:
        existing_providers = self.search(
            self._get_domain_provider(provider_code, **kwargs)
        )
        main_provider = existing_providers[:1]
        existing_provider_companies = existing_providers.company_id
        companies_needing_provider = self.env["res.company"].search(
            [
                ("id", "not in", existing_provider_companies.ids),
                ("parent_id", "=", False),
            ]
        )
        for company in companies_needing_provider:
            main_provider.copy({"company_id": company.id})

    @api.model
    def _remove_provider(self, provider_code, **kwargs) -> None:
        providers = self.search(self._get_domain_provider(provider_code, **kwargs))
        providers.write(self._prepare_removal_values())

    @api.model
    def _get_domain_provider(self, provider_code, **kwargs):
        return [("code", "=", provider_code)]

    def _prepare_removal_values(self):
        return {
            "code": "none",
            "state": "disabled",
            "is_published": False,
            "redirect_form_view_id": None,
            "inline_form_view_id": None,
            "token_inline_form_view_id": None,
            "express_checkout_form_view_id": None,
        }

    def _get_code(self):
        self.check_singleton()
        return self.code

    def _get_status_message(self, status):
        match status:
            case "pending":
                status_message = self.pending_msg
            case "authorized":
                status_message = self.auth_msg
            case "done":
                status_message = self.done_msg
            case "cancel":
                status_message = self.cancel_msg
            case _:
                status_message = ""
        if not is_html_empty(status_message):
            return status_message
        return ""
