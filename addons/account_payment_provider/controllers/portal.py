from odoo import fields, http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request

from odoo.addons.account.controllers import portal
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers.portal import PaymentPortal


class PortalAccount(portal.PortalAccount, PaymentPortal):
    def _invoice_get_page_view_values(
        self, invoice, access_token, /, payment=False, amount=None, **kwargs
    ):

        values = super()._invoice_get_page_view_values(
            invoice, access_token, amount=amount, **kwargs
        )

        if not invoice._has_to_be_paid():
            return {
                **values,
                "payment": payment,
            }

        epd = values.get("epd_discount_amount_currency", 0.0)
        discounted_amount = invoice.amount_residual - epd

        common_view_values = self._prepare_common_page_view_values(
            invoices_data={
                "partner": invoice.partner_id,
                "company": invoice.company_id,
                "total_amount": invoice.amount_total,
                "currency": invoice.currency_id,
                "amount_residual": discounted_amount,
                "landing_route": invoice.get_portal_url(),
                "transaction_route": f"/invoice/transaction/{invoice.id}",
            },
            access_token=access_token,
            **kwargs,
        )

        amount_custom = float(amount or 0.0)
        values |= {
            **common_view_values,
            "amount_custom": amount_custom,
            "payment": payment,
            "invoice_id": invoice.id,
            "invoice_name": invoice.name,
            "show_epd": epd,
        }
        return values

    @http.route(
        ["/my/invoices/overdue"],
        type="http",
        auth="public",
        methods=["GET"],
        website=True,
        sitemap=False,
    )
    def portal_my_overdue_invoices(self, access_token=None, **kw):
        try:
            request.env["account.move"].check_access("read")
        except AccessError, MissingError:
            return request.redirect("/my")

        overdue_invoices = request.env["account.move"].search(
            self._get_domain_overdue_invoices()
        )

        values = self._acquire_overdue_invoice_page_values(overdue_invoices, **kw)
        return (
            request.render(
                "account_payment_provider.portal_overdue_invoices_page", values
            )
            if "payment" in values
            else request.redirect("/my/invoices")
        )

    def _acquire_overdue_invoice_page_values(self, overdue_invoices, /, **kwargs):
        values = {"page_name": "overdue_invoices"}

        if len(overdue_invoices) == 0:
            return values

        first_invoice = overdue_invoices[0]
        partner = first_invoice.partner_id
        company = first_invoice.company_id
        currency = first_invoice.currency_id

        if any(invoice.partner_id != partner for invoice in overdue_invoices):
            raise ValidationError(
                request.env._("Overdue invoices should share the same partner.")
            )
        if any(invoice.company_id != company for invoice in overdue_invoices):
            raise ValidationError(
                request.env._("Overdue invoices should share the same company.")
            )
        if any(invoice.currency_id != currency for invoice in overdue_invoices):
            raise ValidationError(
                request.env._("Overdue invoices should share the same currency.")
            )

        total_amount = sum(overdue_invoices.mapped("amount_total"))
        amount_residual = sum(overdue_invoices.mapped("amount_residual"))
        batch_name = (
            company.acquire_next_batch_payment_communication()
            if len(overdue_invoices) > 1
            else first_invoice.name
        )
        values.update(
            {
                "payment": {
                    "date": fields.Date.today(),
                    "reference": batch_name,
                    "amount": total_amount,
                    "currency": currency,
                },
                "amount": total_amount,
            }
        )

        common_view_values = self._prepare_common_page_view_values(
            invoices_data={
                "partner": partner,
                "company": company,
                "total_amount": total_amount,
                "currency": currency,
                "amount_residual": amount_residual,
                "payment_reference": batch_name,
                "landing_route": "/my/invoices/",
                "transaction_route": "/invoice/transaction/overdue",
            },
            **kwargs,
        )
        values |= common_view_values
        return values

    def _prepare_common_page_view_values(
        self, invoices_data, access_token=None, **kwargs
    ):
        logged_in = not request.env.user._is_public()
        partner_sudo = (
            request.env.user.partner_id if logged_in else invoices_data["partner"]
        )
        invoice_company = invoices_data["company"] or request.env.company

        availability_report = {}
        providers_sudo = (
            request.env["payment.provider"]
            .sudo()
            ._get_compatible_providers(
                invoice_company.id,
                partner_sudo.id,
                invoices_data["total_amount"],
                currency_id=invoices_data["currency"].id,
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
                currency_id=invoices_data["currency"].id,
                report=availability_report,
            )
        )
        tokens_sudo = (
            request.env["payment.token"]
            .sudo()
            ._get_available_tokens(providers_sudo.ids, partner_sudo.id)
        )

        company_mismatch = not PaymentPortal._can_partner_pay_in_company(
            partner_sudo, invoice_company
        )

        portal_page_values = {
            "company_mismatch": company_mismatch,
            "expected_company": invoice_company,
        }
        payment_form_values = {
            "show_tokenize_input_mapping": self._get_show_tokenize_input_mapping(
                providers_sudo, **kwargs
            ),
        }
        payment_context = {
            "currency": invoices_data["currency"],
            "partner_id": partner_sudo.id,
            "providers_sudo": providers_sudo,
            "payment_methods_sudo": payment_methods_sudo,
            "tokens_sudo": tokens_sudo,
            "availability_report": availability_report,
            "transaction_route": invoices_data["transaction_route"],
            "landing_route": invoices_data["landing_route"],
            "access_token": access_token,
            "payment_reference": invoices_data.get("payment_reference", False),
        }
        return (
            portal_page_values
            | payment_form_values
            | payment_context
            | self._prepare_extra_payment_form_context(**kwargs)
        )

    @http.route()
    def portal_my_invoice_detail(
        self, invoice_id, payment_token=None, amount=None, **kw
    ):

        if amount and not payment_utils.is_access_token_valid(
            payment_token, invoice_id, amount
        ):
            return request.redirect("/my")
        return super().portal_my_invoice_detail(invoice_id, amount=amount, **kw)
