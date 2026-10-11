import urllib.parse

from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing
from odoo.addons.portal.controllers import portal
from odoo.addons.web.controllers.utils import fragments_or_redirect


class PaymentPortal(portal.CustomerPortal):
    """This controller contains the foundations for online payments through the portal.

    It allows to complete a full payment flow without the need of going through a document-based
    flow made available by another module's controller.

    Such controllers should extend this one to gain access to the `_create_transaction` method
    that implements the creation of a transaction before its processing, or to override specific
    routes and change their behavior globally (e.g. make the /pay route handle sale orders).

    The following routes are exposed:
    - `/payment/pay` allows for arbitrary payments.
    - `/my/payment_method` allows the user to create and delete tokens. It's its own `landing_route`
    - `/payment/transaction` is the `transaction_route` for the standard payment flow. It creates a
      draft transaction, and return the processing values necessary for the completion of the
      transaction.
    - `/payment/confirmation` is the `landing_route` for the standard payment flow. It displays the
      payment confirmation page to the user when the transaction is validated.
    - `/payment/archive_token` lets the user archive one of their own tokens.
    """

    @http.route(
        "/payment/pay",
        type="http",
        methods=["GET"],
        auth="public",
        website=True,
        sitemap=False,
    )
    def payment_pay(
        self,
        reference=None,
        amount=None,
        currency_id=None,
        partner_id=None,
        company_id=None,
        access_token=None,
        **kwargs,
    ):
        currency_id, partner_id, company_id = tuple(
            map(self._cast_as_int, (currency_id, partner_id, company_id))
        )
        amount = self._cast_as_float(amount)

        if partner_id:
            if not payment_utils.is_access_token_valid(
                access_token, partner_id, amount, currency_id
            ):
                raise NotFound

        user_sudo = request.env.user
        logged_in = not user_sudo._is_public()
        partner_is_different = False
        if logged_in:
            partner_is_different = partner_id and partner_id != user_sudo.partner_id.id
            partner_sudo = user_sudo.partner_id
        else:
            partner_sudo = request.env["res.partner"].sudo().browse(partner_id).exists()
            if not partner_sudo:
                return request.redirect(
                    f"/web/login?redirect={urllib.parse.quote(request.httprequest.full_path)}"
                )

        reference = reference or payment_utils.singularize_reference_prefix(prefix="tx")
        amount = (
            amount or 0.0
        )
        company_id = company_id or partner_sudo.company_id.id or user_sudo.company_id.id
        company = request.env["res.company"].sudo().browse(company_id)
        currency_id = currency_id or company.currency_id.id

        currency = request.env["res.currency"].browse(currency_id).exists()
        if not currency or not currency.active:
            raise NotFound

        availability_report = {}
        providers_sudo = (
            request.env["payment.provider"]
            .sudo()
            ._get_compatible_providers(
                company_id,
                partner_sudo.id,
                amount,
                currency_id=currency.id,
                report=availability_report,
                **kwargs,
            )
        )
        payment_methods_sudo = (
            request.env["payment.method"]
            .sudo()
            ._get_compatible_payment_methods(
                providers_sudo.ids,
                partner_sudo.id,
                currency_id=currency.id,
                report=availability_report,
                **kwargs,
            )
        )
        tokens_sudo = (
            request.env["payment.token"]
            .sudo()
            ._get_available_tokens(providers_sudo.ids, partner_sudo.id)
        )

        company_mismatch = not PaymentPortal._can_partner_pay_in_company(
            partner_sudo, company
        )

        access_token = payment_utils.generate_access_token(
            partner_sudo.id, amount, currency.id
        )

        portal_page_values = {
            "res_company": company,
            "company_mismatch": company_mismatch,
            "expected_company": company,
            "partner_is_different": partner_is_different,
        }
        payment_form_values = {
            "show_tokenize_input_mapping": self._get_show_tokenize_input_mapping(
                providers_sudo, **kwargs
            ),
        }
        payment_context = {
            "reference_prefix": reference,
            "amount": amount,
            "currency": currency,
            "partner_id": partner_sudo.id,
            "providers_sudo": providers_sudo,
            "payment_methods_sudo": payment_methods_sudo,
            "tokens_sudo": tokens_sudo,
            "availability_report": availability_report,
            "transaction_route": "/payment/transaction",
            "landing_route": "/payment/confirmation",
            "access_token": access_token,
        }
        rendering_context = {
            **portal_page_values,
            **payment_form_values,
            **payment_context,
            **self._prepare_extra_payment_form_context(
                **payment_context, currency_id=currency.id, **kwargs
            ),
        }
        return request.render(
            self._get_payment_page_template_xmlid(**kwargs), rendering_context
        )

    @staticmethod
    def _get_show_tokenize_input_mapping(providers_sudo, **kwargs):
        show_tokenize_input_mapping = {}
        for provider_sudo in providers_sudo:
            show_tokenize_input = (
                provider_sudo.allow_tokenization
                and not provider_sudo._is_tokenization_required(**kwargs)
            )
            show_tokenize_input_mapping[provider_sudo.id] = show_tokenize_input
        return show_tokenize_input_mapping

    def _get_payment_page_template_xmlid(self, **kwargs):
        return "payment.pay"

    @http.route(
        "/my/payment_method", type="http", methods=["GET"], auth="user", website=True
    )
    def payment_method(self, **kwargs):
        partner_sudo = request.env.user.partner_id

        availability_report = {}
        providers_sudo = (
            request.env["payment.provider"]
            .sudo()
            ._get_compatible_providers(
                request.env.company.id,
                partner_sudo.id,
                0.0,
                force_tokenization=True,
                is_validation=True,
                report=availability_report,
                **kwargs,
            )
        )
        payment_methods_sudo = (
            request.env["payment.method"]
            .sudo()
            ._get_compatible_payment_methods(
                providers_sudo.ids,
                partner_sudo.id,
                force_tokenization=True,
                report=availability_report,
            )
        )
        tokens_sudo = (
            request.env["payment.token"]
            .sudo()
            ._get_available_tokens(None, partner_sudo.id, is_validation=True)
        )

        access_token = payment_utils.generate_access_token(partner_sudo.id, None, None)

        payment_form_values = {
            "mode": "validation",
            "allow_token_selection": False,
            "allow_token_deletion": True,
        }
        payment_context = {
            "reference_prefix": payment_utils.singularize_reference_prefix(prefix="V"),
            "partner_id": partner_sudo.id,
            "providers_sudo": providers_sudo,
            "payment_methods_sudo": payment_methods_sudo,
            "tokens_sudo": tokens_sudo,
            "availability_report": availability_report,
            "transaction_route": "/payment/transaction",
            "landing_route": "/my/payment_method",
            "access_token": access_token,
        }
        rendering_context = {
            **payment_form_values,
            **payment_context,
            **self._prepare_extra_payment_form_context(**kwargs),
        }
        return request.render("payment.payment_methods", rendering_context)

    def _prepare_extra_payment_form_context(self, **kwargs):
        return {}

    @http.route("/payment/transaction", type="jsonrpc", auth="public")
    def payment_transaction(
        self, amount, currency_id, partner_id, access_token, **kwargs
    ):
        amount = amount and float(
            amount
        )
        if not payment_utils.is_access_token_valid(
            access_token, partner_id, amount, currency_id
        ):
            raise Forbidden

        self._check_transaction_kwargs(
            kwargs, additional_allowed_keys=("reference_prefix",)
        )
        tx_sudo = self._create_transaction(
            amount=amount, currency_id=currency_id, partner_id=partner_id, **kwargs
        )
        self._update_landing_route(
            tx_sudo, access_token
        )
        return tx_sudo._prepare_processing_values()

    def _create_transaction(
        self,
        provider_id,
        payment_method_id,
        token_id,
        amount,
        currency_id,
        partner_id,
        flow,
        tokenization_requested,
        landing_route,
        reference_prefix=None,
        is_validation=False,
        custom_create_values=None,
        **kwargs,
    ):
        provider_sudo = request.env["payment.provider"].sudo().browse(provider_id)
        tokenize = False
        if flow in ["redirect", "direct"]:
            payment_method_sudo = (
                request.env["payment.method"].sudo().browse(payment_method_id)
            )
            token_id = None
            tokenize = bool(
                provider_sudo.allow_tokenization
                and payment_method_sudo.support_tokenization
                and (
                    provider_sudo._is_tokenization_required(**kwargs)
                    or tokenization_requested
                )
            )
        elif flow == "token":
            token_sudo = request.env["payment.token"].sudo().browse(token_id)

            partner_sudo = request.env["res.partner"].sudo().browse(partner_id)
            if (
                partner_sudo.commercial_partner_id
                != token_sudo.partner_id.commercial_partner_id
            ):
                raise AccessError(
                    request.env._("You do not have access to this payment token.")
                )

            payment_method_id = token_sudo.payment_method_id.id

        reference = request.env["payment.transaction"]._get_unique_reference(
            provider_sudo.code,
            prefix=reference_prefix,
            **(custom_create_values or {}),
            **kwargs,
        )
        if (
            is_validation
        ):
            amount = provider_sudo._get_validation_amount()
            payment_method = request.env["payment.method"].browse(payment_method_id)
            currency_id = (
                provider_sudo.with_context(
                    validation_pm=payment_method
                )
                ._get_validation_currency()
                .id
            )

        tx_sudo = (
            request.env["payment.transaction"]
            .sudo()
            .create(
                {
                    "provider_id": provider_sudo.id,
                    "payment_method_id": payment_method_id,
                    "reference": reference,
                    "amount": amount,
                    "currency_id": currency_id,
                    "partner_id": partner_id,
                    "token_id": token_id,
                    "operation": f"online_{flow}"
                    if not is_validation
                    else "validation",
                    "tokenize": tokenize,
                    "landing_route": landing_route,
                    **(custom_create_values or {}),
                }
            )
        )

        if flow != "token":
            tx_sudo._log_sent_message()
        elif not request.env.context.get("delay_token_charge"):
            tx_sudo._charge_with_token()

        PaymentPostProcessing.monitor_transaction(tx_sudo)

        return tx_sudo

    @staticmethod
    def _update_landing_route(tx_sudo, access_token):
        if tx_sudo.operation == "validation":
            access_token = payment_utils.generate_access_token(
                tx_sudo.partner_id.id, tx_sudo.amount, tx_sudo.currency_id.id
            )
        tx_sudo.landing_route = (
            f"{tx_sudo.landing_route}?tx_id={tx_sudo.id}&access_token={access_token}"
        )

    @http.route(
        "/payment/confirmation",
        type="http",
        methods=["GET"],
        auth="public",
        website=True,
    )
    def payment_confirm(self, tx_id, access_token, **kwargs):
        tx_id = self._cast_as_int(tx_id)
        if tx_id:
            tx_sudo = request.env["payment.transaction"].sudo().browse(tx_id)

            if not payment_utils.is_access_token_valid(
                access_token,
                tx_sudo.partner_id.id,
                tx_sudo.amount,
                tx_sudo.currency_id.id,
            ):
                raise NotFound

            return request.render("payment.confirm", qcontext={"tx": tx_sudo})
        else:
            return request.redirect("/my/home")

    @http.route("/payment/archive_token", type="http", auth="user", methods=["POST"])
    def archive_token(self, token_id=None, redirect=None, **kwargs):
        back = redirect or "/my/payment_method"
        token_id = self._cast_as_int(token_id)
        partner_sudo = request.env.user.partner_id
        token_sudo = (
            request.env["payment.token"]
            .sudo()
            .search(
                [
                    ("id", "=", token_id),
                    (
                        "partner_id",
                        "in",
                        [partner_sudo.id, partner_sudo.commercial_partner_id.id],
                    ),
                ]
            )
        )
        if token_sudo:
            token_sudo.active = False
        return fragments_or_redirect(request.env, back, redirect=back)

    @staticmethod
    def _cast_as_int(str_value):
        try:
            return int(str_value)
        except TypeError, ValueError, OverflowError:
            return None

    @staticmethod
    def _cast_as_float(str_value):
        try:
            return float(str_value)
        except TypeError, ValueError, OverflowError:
            return None

    @staticmethod
    def _can_partner_pay_in_company(partner, document_company) -> bool:
        return not partner.company_id or partner.company_id == document_company

    @staticmethod
    def _check_transaction_kwargs(kwargs, additional_allowed_keys=()):
        whitelist = {
            "provider_id",
            "payment_method_id",
            "token_id",
            "amount",
            "flow",
            "tokenization_requested",
            "landing_route",
            "is_validation",
            "csrf_token",
        }
        whitelist.update(additional_allowed_keys)
        rejected_keys = set(kwargs.keys()) - whitelist
        if rejected_keys:
            raise BadRequest(
                request.env._(
                    "The following kwargs are not whitelisted: %s",
                    ", ".join(rejected_keys),
                )
            )
