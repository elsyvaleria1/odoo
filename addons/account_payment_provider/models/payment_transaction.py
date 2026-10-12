from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import ValidationError


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model_create_multi
    def create(self, vals_list):
        transactions = super().create(vals_list)
        invoices = transactions.filtered(
            lambda tx: tx.operation not in ("refund", "validation")
        ).invoice_ids
        invoices._lock_for_payment()
        if any(invoice.state == "cancel" for invoice in invoices):
            raise ValidationError(self.env._("You cannot pay a cancelled invoice."))
        return transactions

    payment_ids = fields.One2many(
        comodel_name="account.payment",
        inverse_name="transaction_id",
        string="Payments",
        readonly=True,
    )
    payment_id = fields.Many2one(
        comodel_name="account.payment",
        compute="_compute_payment_id",
        search="_search_payment_id",
        readonly=True,
    )

    invoice_ids = fields.Many2many(
        comodel_name="account.move",
        relation="account_invoice_transaction_rel",
        column1="transaction_id",
        column2="invoice_id",
        string="Invoices",
        copy=False,
        readonly=True,
        domain=[
            (
                "move_type",
                "in",
                ("out_invoice", "out_refund", "in_invoice", "in_refund"),
            )
        ],
    )
    invoices_count = fields.Count(count_of="invoice_ids")

    @api.depends("payment_ids")
    def _compute_payment_id(self) -> None:
        for tx in self:
            tx.payment_id = tx.payment_ids[:1]

    def _search_payment_id(self, operator, value) -> list:
        return [("payment_ids", operator, value)]

    def action_view_invoices(self):
        self.check_singleton()

        action = {
            "name": self.env._("Invoices"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "target": "current",
        }
        invoice_ids = self.invoice_ids.ids
        if len(invoice_ids) == 1:
            invoice = invoice_ids[0]
            action["res_id"] = invoice
            action["view_mode"] = "form"
            action["views"] = [(self.env.ref("account.view_move_form").id, "form")]
        else:
            action["view_mode"] = "list,form"
            action["domain"] = [("id", "in", invoice_ids)]
        return action

    @api.model
    def _get_reference_prefix(self, separator, **values):
        command_list = values.get("invoice_ids")
        if command_list:
            invoice_ids = self._fields["invoice_ids"].convert_to_cache(
                command_list, self
            )
            invoices = self.env["account.move"].browse(invoice_ids).exists()
            if len(invoices) == len(invoice_ids):
                prefix = separator.join(
                    invoices.filtered(lambda inv: inv.name).mapped("name")
                )
                if name := values.get("name_next_installment"):
                    prefix = name
                return prefix
        return super()._get_reference_prefix(separator, **values)

    def _post_process(self):
        super()._post_process()
        for tx in self.filtered(lambda t: t.state == "done"):
            drafts = tx.invoice_ids.filtered(lambda inv: inv.state == "draft")
            with drafts._exempting_posting_from_approval("payment_received"):
                drafts.action_post()

            if (
                tx.operation != "validation"
                and not tx.payment_id
                and not any(
                    child.state in ["done", "cancel"]
                    for child in tx.child_transaction_ids
                )
            ):
                tx.with_company(tx.company_id)._create_payment()

            if tx.payment_id:
                message = self.env._(
                    "The payment related to transaction %(ref)s has been posted: %(link)s",
                    ref=tx._get_html_link(),
                    link=tx.payment_id._get_html_link(),
                )
                tx._log_message_on_linked_documents(message)
        for tx in self.filtered(lambda t: t.state == "cancel"):
            tx.payment_id.action_cancel()

    def _prepare_payment_vals(self, **extra_create_values):
        self.check_singleton()

        reference = f"{self.reference} - {self.provider_reference or ''}"
        payment_channel = (
            self.provider_id.journal_id.inbound_payment_channel_ids.filtered(
                lambda l: l.payment_provider_id == self.provider_id
            )
        )
        payment_values = {
            "amount": abs(self.amount),
            "payment_type": "inbound" if self.amount > 0 else "outbound",
            "currency_id": self.currency_id.id,
            "partner_id": self.partner_id.commercial_partner_id.id,
            "partner_type": "customer",
            "journal_id": self.provider_id.journal_id.id,
            "company_id": self.provider_id.company_id.id,
            "payment_channel_id": payment_channel.id,
            "payment_token_id": self.token_id.id,
            "transaction_id": self.id,
            "memo": reference,
            "write_off_line_vals": [],
            "invoice_ids": self.invoice_ids,
            **extra_create_values,
        }
        payment_values["write_off_line_vals"] += (
            self._prepare_early_payment_discount_vals()
        )

        payment_term_lines = self.invoice_ids.line_ids.filtered(
            lambda line: line.display_type == "payment_term"
        )
        if payment_term_lines and len(payment_term_lines.account_id) == 1:
            payment_values["counterpart_account_id"] = payment_term_lines[
                0
            ].account_id.id

        return payment_values

    def _prepare_early_payment_discount_vals(self):
        self.check_singleton()

        for invoice in self.invoice_ids:
            if invoice.state != "posted":
                continue
            next_payment_values = invoice._prepare_invoice_next_payment_values()
            if (
                next_payment_values["installment_state"] != "epd"
                or self.amount != next_payment_values["amount_due"]
            ):
                continue
            aml = next_payment_values["epd_line"]
            epd_aml_values_list = [
                {
                    "aml": aml,
                    "amount_currency": -aml.amount_residual_currency,
                    "balance": -aml.balance,
                }
            ]
            open_balance = next_payment_values["epd_discount_amount"]
            early_payment_values = self.env[
                "account.move"
            ]._get_invoice_counterpart_amls_for_early_payment_discount(
                epd_aml_values_list, open_balance
            )
            write_off_line_vals = []
            for aml_values_list in early_payment_values.values():
                if aml_values_list:
                    aml_vl = aml_values_list[0]
                    aml_vl["partner_id"] = invoice.partner_id.id
                    write_off_line_vals += [aml_vl]
            return write_off_line_vals

        return []

    def _reconcile_payment(self, payment) -> None:
        self.check_singleton()

        if self.operation == self.source_transaction_id.operation:
            invoices = self.source_transaction_id.invoice_ids
        else:
            invoices = self.invoice_ids
        invoices = invoices.filtered(lambda inv: inv.state != "cancel")
        if not invoices:
            return

        drafts = invoices.filtered(lambda inv: inv.state == "draft")
        with drafts._exempting_posting_from_approval("payment_received"):
            drafts.action_post()
        (payment.move_id.line_ids + invoices.line_ids).filtered(
            lambda line: (
                line.account_id == payment.counterpart_account_id
                and not line.reconciled
            )
        ).reconcile()

    def _create_payment(self, **extra_create_values):
        self.check_singleton()

        payment = self.env["account.payment"].create(
            self._prepare_payment_vals(**extra_create_values)
        )
        payment.action_post()

        self._reconcile_payment(payment)

        return payment

    def _log_message_on_linked_documents(self, message) -> None:
        self.check_singleton()
        if self.env.uid == SUPERUSER_ID or self.env.context.get(
            "payment_backend_action"
        ):
            author = self.env.user.partner_id
        else:
            author = self.partner_id
        if self.source_transaction_id:
            for invoice in self.source_transaction_id.invoice_ids:
                invoice.message_post(body=message, author_id=author.id)
            payment_id = self.source_transaction_id.payment_id
            if payment_id:
                payment_id.message_post(body=message, author_id=author.id)
        for invoice in self._get_invoices_to_notify():
            invoice.message_post(body=message, author_id=author.id)

    def _get_invoices_to_notify(self):
        return self.invoice_ids
