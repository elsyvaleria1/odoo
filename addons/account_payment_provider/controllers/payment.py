from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.fields import Command
from odoo.http import request, route

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers import portal as payment_portal


class PaymentPortal(payment_portal.PaymentPortal):
    @route("/invoice/transaction/<int:invoice_id>", type="jsonrpc", auth="public")
    def invoice_transaction(self, invoice_id, access_token, **kwargs):
        try:
            invoice_sudo = request.env["access.link"]._open_record(
                "account.move", invoice_id, access_token
            )
        except MissingError:
            raise
        except AccessError as error:
            raise ValidationError(
                request.env._("The access token is invalid.")
            ) from error

        logged_in = not request.env.user._is_public()
        partner_sudo = (
            request.env.user.partner_id if logged_in else invoice_sudo.partner_id
        )
        self._check_transaction_kwargs(
            kwargs, additional_allowed_keys={"name_next_installment"}
        )
        return self._process_transaction(
            partner_sudo.id, invoice_sudo.currency_id.id, [invoice_id], False, **kwargs
        )

    @route("/invoice/transaction/overdue", type="jsonrpc", auth="public")
    def overdue_invoices_transaction(self, payment_reference, **kwargs):
        logged_in = not request.env.user._is_public()
        if not logged_in:
            raise ValidationError(
                request.env._("Please log in to pay your overdue invoices")
            )
        partner = request.env.user.partner_id
        overdue_invoices = request.env["account.move"].search(
            self._get_domain_overdue_invoices()
        )
        currencies = overdue_invoices.mapped("currency_id")
        if not all(currency == currencies[0] for currency in currencies):
            raise ValidationError(
                request.env._(
                    "Impossible to pay all the overdue invoices if they don't share the same currency."
                )
            )
        self._check_transaction_kwargs(kwargs)
        return self._process_transaction(
            partner.id,
            currencies[0].id,
            overdue_invoices.ids,
            payment_reference,
            **kwargs,
        )

    def _process_transaction(
        self, partner_id, currency_id, invoice_ids, payment_reference, **kwargs
    ):
        kwargs.update(
            {
                "currency_id": currency_id,
                "partner_id": partner_id,
                "reference_prefix": payment_reference,
            }
        )
        tx_sudo = self._create_transaction(
            custom_create_values={
                "invoice_ids": [Command.set(invoice_ids)],
            },
            **kwargs,
        )

        return tx_sudo._prepare_processing_values()


    @route()
    def payment_pay(
        self, *args, amount=None, invoice_id=None, access_token=None, **kwargs
    ):
        amount = self._cast_as_float(amount)
        invoice_id = self._cast_as_int(invoice_id)
        if invoice_id:
            invoice_sudo = (
                request.env["account.move"].sudo().browse(invoice_id).exists()
            )
            if not invoice_sudo:
                raise ValidationError(
                    request.env._("The provided parameters are invalid.")
                )

            if not payment_utils.is_access_token_valid(
                access_token,
                invoice_sudo.partner_id.id,
                amount,
                invoice_sudo.currency_id.id,
            ):
                raise ValidationError(
                    request.env._("The provided parameters are invalid.")
                )

            kwargs.update(
                {
                    "reference": invoice_sudo.name,
                    "currency_id": invoice_sudo.currency_id.id,
                    "partner_id": invoice_sudo.partner_id.id,
                    "company_id": invoice_sudo.company_id.id,
                    "invoice_id": invoice_id,
                }
            )
        return super().payment_pay(
            *args, amount=amount, access_token=access_token, **kwargs
        )

    def _prepare_extra_payment_form_context(
        self, invoice_id=None, access_token=None, **kwargs
    ):
        form_values = super()._prepare_extra_payment_form_context(
            invoice_id=invoice_id, access_token=access_token, **kwargs
        )
        if invoice_id:
            invoice_id = self._cast_as_int(invoice_id)

            try:
                invoice_sudo = request.env["access.link"]._open_record(
                    "account.move", invoice_id, access_token
                )
            except (
                AccessError
            ):
                if not payment_utils.is_access_token_valid(
                    access_token,
                    kwargs.get("partner_id"),
                    kwargs.get("amount"),
                    kwargs.get("currency_id"),
                ):
                    raise
                invoice_sudo = (
                    request.env["account.move"].sudo().browse(invoice_id).exists()
                )
                if not invoice_sudo:
                    raise ValidationError(
                        request.env._("The provided parameters are invalid.")
                    ) from None

            if invoice_sudo.state == "cancel":
                form_values["amount"] = 0.0

            token = invoice_sudo._portal_get_or_create_token()
            form_values.update(
                {
                    "transaction_route": f"/invoice/transaction/{invoice_id}",
                    "landing_route": f"{invoice_sudo.access_url}?access_token={token}",
                    "access_token": token,
                }
            )
        return form_values
