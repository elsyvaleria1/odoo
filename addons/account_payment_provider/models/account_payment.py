from odoo import Command, api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    transaction_id = fields.Many2one(
        comodel_name="payment.transaction",
        string="Payment Transaction",
        readonly=True,
        bypass_search_access=True,
    )
    payment_token_id = fields.Many2one(
        comodel_name="payment.token",
        string="Saved Payment Token",
        domain="""[
            ('id', 'in', suitable_payment_token_ids),
        ]""",
        help="Note that only tokens from providers allowing to capture the amount are available.",
    )
    amount_available_for_refund = fields.Monetary(
        compute="_compute_amount_available_for_refund"
    )

    suitable_payment_token_ids = fields.Many2many(
        comodel_name="payment.token",
        compute="_compute_suitable_payment_token_ids",
        compute_sudo=True,
    )
    use_electronic_payment_method = fields.Boolean(
        compute="_compute_use_electronic_payment_method"
    )

    source_payment_id = fields.Many2one(
        comodel_name="account.payment",
        compute="_compute_source_payment_id",
        store=True,
        index="btree_not_null",
        readonly=True,
        help="The source payment of related refund payments",
    )
    refunds_count = fields.Integer(compute="_compute_refunds_count")

    _transaction_id_uniq = models.UniqueIndex(
        "(transaction_id) WHERE transaction_id IS NOT NULL",
        "A payment transaction can only be linked to one payment.",
    )


    @api.depends("transaction_id.source_transaction_id.payment_ids")
    def _compute_source_payment_id(self) -> None:
        for payment in self:
            source_tx = payment.transaction_id.source_transaction_id
            payment.source_payment_id = source_tx.payment_ids[:1]

    @api.depends("amount", "payment_method_id", "transaction_id")
    def _compute_amount_available_for_refund(self) -> None:
        rg_data = self.env["account.payment"]._read_group(
            domain=[("source_payment_id", "in", self.ids)],
            groupby=["source_payment_id"],
            aggregates=["amount:sum"],
        )
        refunded_amount_per_payment = {
            source_payment.id: amount_sum for source_payment, amount_sum in rg_data
        }
        for payment in self:
            tx_sudo = payment.transaction_id.sudo()
            payment_method = (
                tx_sudo.payment_method_id.primary_payment_method_id
                or tx_sudo.payment_method_id
            )
            if (
                tx_sudo
                and tx_sudo.provider_id.support_refund != "none"
                and payment_method.support_refund != "none"
                and tx_sudo.operation != "refund"
            ):
                refunded_amount = abs(refunded_amount_per_payment.get(payment.id, 0.0))
                payment.amount_available_for_refund = payment.amount - refunded_amount
            else:
                payment.amount_available_for_refund = 0

    @api.depends("payment_channel_id")
    def _compute_suitable_payment_token_ids(self) -> None:
        electronic_payments = self.filtered("use_electronic_payment_method")
        tokens_per_group = {}
        for payment in electronic_payments:
            group_key = (
                payment.company_id.id,
                payment.partner_id.id,
                payment.payment_channel_id.payment_provider_id.id,
            )
            if group_key not in tokens_per_group:
                tokens_per_group[group_key] = (
                    self.env["payment.token"]
                    .sudo()
                    .search(
                        [
                            *self.env["payment.token"]._check_company_domain(
                                payment.company_id
                            ),
                            ("provider_id.capture_manually", "=", False),
                            ("partner_id", "=", payment.partner_id.id),
                            (
                                "provider_id",
                                "=",
                                payment.payment_channel_id.payment_provider_id.id,
                            ),
                        ]
                    )
                )
            payment.suitable_payment_token_ids = tokens_per_group[group_key]
        for payment in self - electronic_payments:
            payment.suitable_payment_token_ids = [Command.clear()]

    @api.depends("payment_channel_id")
    def _compute_use_electronic_payment_method(self) -> None:
        codes = self._get_electronic_payment_method_codes()
        for payment in self:
            payment.use_electronic_payment_method = payment.payment_method_code in codes

    def _compute_refunds_count(self) -> None:
        rg_data = self.env["account.payment"]._read_group(
            domain=[
                ("source_payment_id", "in", self.ids),
                ("transaction_id.operation", "=", "refund"),
            ],
            groupby=["source_payment_id"],
            aggregates=["__count"],
        )
        data = {source_payment.id: count for source_payment, count in rg_data}
        for payment in self:
            payment.refunds_count = data.get(payment.id, 0)


    def _get_electronic_payment_method_codes(self):
        return list(
            dict(
                self.env["payment.provider"]
                ._fields["code"]
                ._description_selection(self.env)
            )
        )


    @api.onchange("partner_id", "payment_channel_id", "journal_id")
    def _onchange_set_payment_token_id(self) -> None:
        codes = self._get_electronic_payment_method_codes()
        if not (
            self.payment_method_code in codes and self.partner_id and self.journal_id
        ):
            self.payment_token_id = False
            return

        self.payment_token_id = (
            self.env["payment.token"]
            .sudo()
            .search(
                [
                    *self.env["payment.token"]._check_company_domain(self.company_id),
                    ("partner_id", "=", self.partner_id.id),
                    ("provider_id.capture_manually", "=", False),
                    (
                        "provider_id",
                        "=",
                        self.payment_channel_id.payment_provider_id.id,
                    ),
                ],
                limit=1,
            )
        )


    def action_post(self):

        payments_need_tx = self.filtered(
            lambda p: p.payment_token_id and not p.transaction_id
        )
        transactions = payments_need_tx.sudo()._create_payment_transaction()

        res = super(AccountPayment, self - payments_need_tx).action_post()

        for tx in transactions:
            tx._charge_with_token()

        transactions._post_process()
        payments_tx_done = payments_need_tx.filtered(
            lambda p: p.transaction_id.state == "done"
        )
        super(AccountPayment, payments_tx_done).action_post()
        payments_tx_not_done = payments_need_tx.filtered(
            lambda p: p.transaction_id.state != "done"
        )
        payments_tx_not_done.action_cancel()

        return res

    def action_refund_wizard(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Refund"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.account.payment.refund",
            "target": "new",
        }

    def action_view_refunds(self):
        self.check_singleton()
        action = {
            "name": self.env._("Refund"),
            "res_model": "account.payment",
            "type": "ir.actions.act_window",
        }
        if self.refunds_count == 1:
            refund_tx = self.env["account.payment"].search(
                [("source_payment_id", "=", self.id)], limit=1
            )
            action["res_id"] = refund_tx.id
            action["view_mode"] = "form"
        else:
            action["view_mode"] = "list,form"
            action["domain"] = [("source_payment_id", "=", self.id)]
        return action


    def _create_payment_transaction(self, **extra_create_values):
        for payment in self:
            if payment.transaction_id:
                raise ValidationError(
                    self.env._(
                        "A payment transaction with reference %s already exists.",
                        payment.transaction_id.reference,
                    )
                )
            if not payment.payment_token_id:
                raise ValidationError(
                    self.env._(
                        "A token is required to create a new payment transaction."
                    )
                )

        transactions = self.env["payment.transaction"]
        for payment in self:
            transaction_vals = payment._prepare_payment_transaction_vals(
                **extra_create_values
            )
            transaction = self.env["payment.transaction"].create(transaction_vals)
            transactions += transaction
            payment.transaction_id = (
                transaction
            )
        return transactions

    def _prepare_payment_transaction_vals(self, **extra_create_values) -> dict:
        self.check_singleton()
        if self.env.context.get("active_model", "") == "account.move":
            invoice_ids = self.env.context.get("active_ids", [])
        elif self.env.context.get("active_model", "") == "account.move.line":
            invoice_ids = (
                self.env["account.move.line"]
                .browse(self.env.context.get("active_ids"))
                .move_id.ids
            )
        else:
            invoice_ids = []
        return {
            "provider_id": self.payment_token_id.provider_id.id,
            "payment_method_id": self.payment_token_id.payment_method_id.id,
            "reference": self.env["payment.transaction"]._get_unique_reference(
                self.payment_token_id.provider_id.code, prefix=self.memo
            ),
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "partner_id": self.partner_id.id,
            "token_id": self.payment_token_id.id,
            "operation": "offline",
            "invoice_ids": [Command.set(invoice_ids)],
        }

    def _prepare_payment_refund_wizard_vals(self) -> ValuesType:
        self.check_singleton()
        return {
            "transaction_id": self.transaction_id.id,
            "payment_amount": self.amount,
            "amount_available_for_refund": self.amount_available_for_refund,
        }
