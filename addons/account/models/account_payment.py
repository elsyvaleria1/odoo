from collections import defaultdict
from itertools import zip_longest

from odoo import Command, api, fields, models
from odoo.exceptions import MissingError, UserError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict
from odoo.tools.authority_keys import declare_authority_keys

from odoo.addons.account.models.account_journal import LIQUIDITY_TYPES

_debug = DebugLog(__name__)

_ENTRIES_JUST_CREATED = "account_payment_entries_just_created"
_PAYMENTS_UNSETTLED = "account.payment.unsettled_by_dropped_match"
declare_authority_keys("account", _ENTRIES_JUST_CREATED)

_SQL_RECONCILED_INVOICES_PER_PAYMENT = """
    SELECT
        payment.id,
        ARRAY_AGG(DISTINCT invoice.id) AS invoice_ids,
        invoice.move_type
    FROM account_payment payment
    JOIN account_move move ON move.id = payment.move_id
    JOIN account_move_line line ON line.move_id = move.id
    JOIN account_partial_reconcile part ON
        part.debit_move_id = line.id
        OR
        part.credit_move_id = line.id
    JOIN account_move_line counterpart_line ON
        part.debit_move_id = counterpart_line.id
        OR
        part.credit_move_id = counterpart_line.id
    JOIN account_move invoice ON invoice.id = counterpart_line.move_id
    JOIN account_account account ON account.id = line.account_id
    WHERE account.account_type = ANY(%(account_types)s)
        AND payment.id = ANY(%(payment_ids)s)
        AND line.id != counterpart_line.id
        AND invoice.move_type = ANY(%(move_types)s)
    GROUP BY payment.id, invoice.move_type
"""

_SQL_RECONCILED_STATEMENT_LINES_PER_PAYMENT = """
    SELECT
        payment.id,
        ARRAY_AGG(DISTINCT counterpart_move.statement_line_id) AS statement_line_ids
    FROM account_payment payment
    JOIN account_move move ON move.id = payment.move_id
    JOIN account_move_line line ON line.move_id = move.id
    JOIN account_account account ON account.id = line.account_id
    JOIN account_partial_reconcile part ON
        part.debit_move_id = line.id
        OR
        part.credit_move_id = line.id
    JOIN account_move_line counterpart_line ON
        part.debit_move_id = counterpart_line.id
        OR
        part.credit_move_id = counterpart_line.id
    JOIN account_move counterpart_move ON counterpart_move.id = counterpart_line.move_id
    WHERE account.id = payment.liquidity_account_id
        AND payment.id = ANY(%(payment_ids)s)
        AND line.id != counterpart_line.id
        AND counterpart_move.statement_line_id IS NOT NULL
    GROUP BY payment.id
"""

_SEEK_FOR_LINES_DEPENDS = ("move_id.line_ids.payment_role",)
_CHECKED_ROLES = ("liquidity", "counterpart", "withholding")


def _may_hold_payments(move) -> bool:
    if move._cache.get("matched_payment_ids", None) != ():
        return True
    if "line_ids" not in move._cache:
        return True
    return any(
        line._cache.get(fname, None) != ()
        for line in move.line_ids
        for fname in ("matched_debit_ids", "matched_credit_ids")
    )


class AccountPayment(models.Model):
    _name = "account.payment"
    _inherit = [
        "mixin.mail.thread.main.attachment",
        "mixin.mail.activity",
        "mixin.payment.qr.code",
    ]
    _description = "Payments"
    _order = "date desc, name desc"
    _legacy_field_names = frozendict(
        {
            "is_reconciled": "is_invoice_reconciled",
            "is_matched": "is_bank_matched",
            "payment_method_line_id": "payment_channel_id",
            "destination_account_id": "counterpart_account_id",
            "outstanding_account_id": "liquidity_account_id",
        }
    )
    _check_company_auto = True

    name = fields.Char(
        string="Number",
        compute="_compute_name",
        store=True,
    )
    date = fields.Date(
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Journal Entry",
        index=True,
        copy=False,
        check_company=True,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        compute="_compute_journal_id",
        precompute=True,
        store=True,
        index=False,
        readonly=False,
        required=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        precompute=True,
        store=True,
        index=False,
        readonly=False,
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("in_process", "In Process"),
            ("paid", "Paid"),
            ("canceled", "Canceled"),
            ("rejected", "Rejected"),
        ],
        compute="_compute_state",
        default="draft",
        store=True,
        copy=False,
        readonly=False,
        required=True,
        tracking=True,
    )
    is_invoice_reconciled = fields.Boolean(
        string="Is Reconciled",
        compute="_compute_reconciliation_status",
        store=True,
    )
    is_bank_matched = fields.Boolean(
        string="Is Matched With a Bank Statement",
        compute="_compute_reconciliation_status",
        store=True,
    )
    is_sent = fields.Boolean(
        copy=False,
        readonly=True,
    )
    available_bank_account_ids = fields.Many2many(
        comodel_name="res.partner.bank.account",
        compute="_compute_available_bank_account_ids",
    )
    bank_account_id = fields.Many2one(
        comodel_name="res.partner.bank.account",
        string="Recipient Bank Account",
        compute="_compute_bank_account_id",
        store=True,
        readonly=False,
        domain="[('id', 'in', available_bank_account_ids)]",
        ondelete="restrict",
        check_company=True,
        tracking=True,
    )
    qr_code = fields.Html(
        string="QR Code URL",
        compute="_compute_qr_code",
    )
    paired_internal_transfer_payment_id = fields.Many2one(
        comodel_name="account.payment",
        index="btree_not_null",
        copy=False,
        help="When an internal transfer is posted, a paired payment is created. "
        "They are cross referenced through this field",
    )

    payment_channel_id = fields.Many2one(
        comodel_name="account.payment.channel",
        string="Payment Method",
        compute="_compute_payment_channel_id",
        store=True,
        copy=False,
        readonly=False,
        domain="[('id', 'in', available_payment_channel_ids)]",
        help="Manual: Pay or Get paid by any method outside of Odoo.\n"
        "Payment Providers: Each payment provider has its own Payment Method. Request a transaction on/to a card thanks to a payment token saved by the partner when buying or subscribing online.\n"
        "Check: Pay bills by check and print it from Odoo.\n"
        "Batch Deposit: Collect several customer checks at once generating and submitting a batch deposit to your bank. Module account_batch_payment is necessary.\n"
        "SEPA Credit Transfer: Pay in the SEPA zone by submitting a SEPA Credit Transfer file to your bank. Module account_iso20022 is necessary.\n"
        "SEPA Direct Debit: Get paid in the SEPA zone thanks to a mandate your partner will have granted to you. Module account_iso20022 is necessary.\n"
        "U.S. ISO20022: Pay in the US by submitting an ISO20022 file to your bank. Module account_iso20022 is necessary.\n",
    )
    available_payment_channel_ids = fields.Many2many(
        comodel_name="account.payment.channel",
        compute="_compute_available_payment_channel_ids",
    )
    payment_method_id = fields.Many2one(
        related="payment_channel_id.payment_method_id",
        string="Method",
        tracking=True,
    )
    available_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        compute="_compute_available_journal_ids",
    )

    amount = fields.Monetary(currency_field="currency_id")
    payment_type = fields.Selection(
        selection=[
            ("outbound", "Send"),
            ("inbound", "Receive"),
        ],
        default="inbound",
        required=True,
        tracking=True,
    )
    partner_type = fields.Selection(
        selection=[
            ("customer", "Customer"),
            ("supplier", "Vendor"),
        ],
        default="customer",
        required=True,
        tracking=True,
    )
    memo = fields.Char(
        inverse="_inverse_memo",
        tracking=True,
    )
    payment_reference = fields.Char(
        copy=False,
        tracking=True,
        help="Reference of the document used to issue this payment. Eg. check number, file name, etc.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_currency_id",
        precompute=True,
        store=True,
        readonly=False,
        help="The payment's currency.",
    )
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Company Currency",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer/Vendor",
        domain="['|', ('parent_id','=', False), ('is_company','=', True)]",
        ondelete="restrict",
        check_company=True,
        tracking=True,
    )
    liquidity_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Liquidity Account",
        compute="_compute_liquidity_account_id",
        store=True,
        index="btree_not_null",
        readonly=False,
        check_company=True,
        tracking=True,
    )
    is_entry_required = fields.Boolean(
        copy=False,
        readonly=True,
    )
    counterpart_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Counterpart Account",
        compute="_compute_counterpart_account_id",
        store=True,
        readonly=False,
        domain="[('account_type', 'in', ('asset_receivable', 'liability_payable'))]",
        check_company=True,
        tracking=True,
        help="The receivable or payable account the payment settles. It follows "
        "the documents being paid; without them, it is your choice or, when the "
        "partner and journal leave only one candidate, that candidate.",
    )
    counterpart_account_source = fields.Selection(
        selection=[
            ("settled", "Settled documents"),
            ("explicit", "Chosen"),
            ("default", "Partner or journal default"),
        ],
        compute="_compute_counterpart_account_id",
        store=True,
        copy=False,
        readonly=False,
    )
    counterpart_review_required = fields.Boolean(
        copy=False,
        readonly=True,
        help="The counterpart account of the payment and its journal entry's "
        "disagreed when account 1.42 was installed. Until someone reviews it and "
        "aligns the payment to its entry, the entry stays editable and unchecked "
        "and the payment cannot rebuild it.",
    )
    is_counterpart_account_ambiguous = fields.Boolean(
        compute="_compute_is_counterpart_account_ambiguous",
    )

    invoice_ids = fields.Many2many(
        comodel_name="account.move",
        relation="account_move__account_payment",
        column1="payment_id",
        column2="invoice_id",
        string="Invoices",
        copy=False,
    )
    reconciled_invoice_ids = fields.Many2many(
        comodel_name="account.move",
        string="Reconciled Invoices",
        compute="_compute_stat_buttons_from_reconciliation",
        search="_search_reconciled_invoice_ids",
        help="Invoices whose journal items have been reconciled with these payments.",
    )
    reconciled_invoices_count = fields.Count(
        count_of="reconciled_invoice_ids",
        string="# Reconciled Invoices",
    )

    reconciled_invoices_type = fields.Selection(
        selection=[("credit_note", "Credit Note"), ("invoice", "Invoice")],
        compute="_compute_stat_buttons_from_reconciliation",
    )
    reconciled_bill_ids = fields.Many2many(
        comodel_name="account.move",
        string="Reconciled Bills",
        compute="_compute_stat_buttons_from_reconciliation",
        search="_search_reconciled_bill_ids",
        help="Bills whose journal items have been reconciled with these payments.",
    )
    reconciled_bills_count = fields.Count(
        count_of="reconciled_bill_ids",
        string="# Reconciled Bills",
    )
    reconciled_statement_line_ids = fields.Many2many(
        comodel_name="account.bank.statement.line",
        string="Reconciled Statement Lines",
        compute="_compute_stat_buttons_from_reconciliation",
        help="Statements lines matched to this payment",
    )
    reconciled_statement_lines_count = fields.Count(
        count_of="reconciled_statement_line_ids",
        string="# Reconciled Statement Lines",
    )

    payment_method_code = fields.Char(related="payment_channel_id.code")
    payment_receipt_title = fields.Char(compute="_compute_payment_receipt_title")

    need_cancel_request = fields.Boolean(related="move_id.need_cancel_request")
    show_partner_bank_account = fields.Boolean(
        compute="_compute_show_require_partner_bank"
    )
    require_partner_bank_account = fields.Boolean(
        compute="_compute_show_require_partner_bank"
    )
    country_code = fields.Char(
        related="company_id.tax_config_id.account_fiscal_country_id.code"
    )
    amount_signed = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_amount_signed",
        tracking=True,
        help="Negative value of amount field if payment_type is outbound",
    )
    amount_company_currency_signed = fields.Monetary(
        currency_field="company_currency_id",
        compute="_compute_amount_company_currency_signed",
        store=True,
    )
    duplicate_payment_ids = fields.Many2many(
        comodel_name="account.payment",
        compute="_compute_duplicate_payment_ids",
    )
    attachment_ids = fields.One2many(
        comodel_name="ir.attachment",
        inverse_name="res_id",
        string="Attachments",
    )

    _check_amount_not_negative = models.Constraint(
        "CHECK(amount >= 0.0)",
        "The payment amount cannot be negative.",
    )
    _journal_id_company_id_idx = models.Index("(journal_id, company_id)")
    _unmatched_idx = models.Index(
        "(journal_id, company_id) WHERE is_bank_matched IS NOT TRUE"
    )

    @api.model
    def _get_valid_payment_account_types(self):
        return ["asset_receivable", "liability_payable"]

    def _seek_for_lines(self) -> list | tuple:
        self.check_singleton()
        empty = self.env["account.move.line"]
        lines_by_role = self.move_id.line_ids.grouped("payment_role")
        return [
            lines_by_role.get("liquidity", empty),
            lines_by_role.get("counterpart", empty),
            lines_by_role.get("write_off", empty)
            | lines_by_role.get("withholding", empty),
        ]

    def _valid_payment_states(self):
        if self.env["account.move"]._has_full_accounting():
            return ["in_process"]
        return ["in_process", "paid"]

    def _get_aml_default_display_name_list(self):
        self.check_singleton()
        label = (
            self.payment_channel_id.name
            if self.payment_channel_id
            else self.env._("No Payment Method")
        )

        if self.memo:
            return [
                ("label", label),
                ("sep", ": "),
                ("memo", self.memo),
            ]
        return [
            ("label", label),
        ]

    @_debug.perf.timed
    def _prepare_move_withholding_lines(self, default_values):
        self.check_singleton()
        return []

    @_debug.perf.timed
    def _prepare_move_liquidity_lines(self, default_values) -> list:
        self.check_singleton()
        return [
            {
                "name": default_values["name"],
                "date_maturity": self.date,
                "partner_id": self.partner_id.id,
                "account_id": self.liquidity_account_id.id,
                "currency_id": self.currency_id.id,
                "balance": default_values["balance"],
                "amount_currency": default_values["amount_currency"],
                "payment_role": "liquidity",
            }
        ]

    @_debug.perf.timed
    def _prepare_move_counterpart_lines(self, default_values) -> list:
        self.check_singleton()
        return [
            {
                "name": default_values["name"],
                "date_maturity": self.date,
                "partner_id": self.partner_id.id,
                "account_id": self.counterpart_account_id.id,
                "currency_id": self.currency_id.id,
                "balance": default_values["balance"],
                "amount_currency": default_values["amount_currency"],
                "payment_role": "counterpart",
            }
        ]

    @_debug.perf.timed
    def _prepare_move_lines_per_type(
        self, write_off_line_vals=None, force_balance=None
    ) -> dict:
        self.check_singleton()

        if force_balance is not None and write_off_line_vals:
            raise ValueError(
                "force_balance sets the liquidity balance outright and cannot be "
                "combined with write_off_line_vals, which derive it."
            )

        if not self.liquidity_account_id:
            raise UserError(
                self.env._(
                    "You can't create a new payment without an outstanding payments/receipts account set either on the company or the %(payment_method)s payment method in the %(journal)s journal.",
                    payment_method=self.payment_channel_id.name,
                    journal=self.journal_id.display_name,
                )
            )

        self._check_counterpart_account()
        self._check_liquidity_account()

        line_name = "".join(
            x[1] for x in self._get_aml_default_display_name_list() if x[1]
        )

        write_off_lines = [
            {**vals, "payment_role": "write_off"} for vals in write_off_line_vals or []
        ]
        write_off_amount_currency = sum(x["amount_currency"] for x in write_off_lines)
        write_off_balance = sum(x["balance"] for x in write_off_lines)

        sign = -1 if self.payment_type == "outbound" else 1
        liquidity_amount_currency = sign * self.amount

        withholding_lines = [
            {**vals, "payment_role": "withholding"}
            for vals in self._prepare_move_withholding_lines(
                {"name": line_name, "amount_currency": liquidity_amount_currency}
            )
        ]
        withholding_amount_currency = sum(
            x["amount_currency"] for x in withholding_lines
        )
        withholding_balance = sum(x["balance"] for x in withholding_lines)

        if force_balance is not None:
            liquidity_balance = sign * abs(force_balance)
        else:
            liquidity_balance = self.currency_id._convert(
                liquidity_amount_currency,
                self.company_id.currency_id,
                self.company_id,
                self.date,
            )
        liquidity_amount_currency -= withholding_amount_currency
        liquidity_balance -= withholding_balance

        liquidity_lines = self._prepare_move_liquidity_lines(
            {
                "name": line_name,
                "balance": liquidity_balance,
                "amount_currency": liquidity_amount_currency,
            }
        )

        counterpart_amount_currency = (
            -liquidity_amount_currency
            - write_off_amount_currency
            - withholding_amount_currency
        )
        counterpart_balance = (
            -liquidity_balance - write_off_balance - withholding_balance
        )
        counterpart_lines = self._prepare_move_counterpart_lines(
            {
                "name": line_name,
                "balance": counterpart_balance,
                "amount_currency": counterpart_amount_currency,
            }
        )

        _debug.pipeline(
            "payment_lines_prepared",
            payment=self,
            forced_balance=force_balance is not None,
            liquidity=len(liquidity_lines),
            counterpart=len(counterpart_lines),
            write_off=len(write_off_lines),
            withholding=len(withholding_lines),
            liquidity_balance=liquidity_balance,
            counterpart_balance=counterpart_balance,
        )
        return {
            "liquidity_lines": liquidity_lines,
            "counterpart_lines": counterpart_lines,
            "write_off_lines": write_off_lines,
            "withholding_lines": withholding_lines,
        }

    @_debug.perf.timed
    def _prepare_move_line_default_vals(
        self, write_off_line_vals=None, force_balance=None
    ):
        self.check_singleton()

        line_vals_per_type = self._prepare_move_lines_per_type(
            write_off_line_vals=write_off_line_vals, force_balance=force_balance
        )
        line_vals = []
        for sub_line_vals in line_vals_per_type.values():
            line_vals += sub_line_vals
        return line_vals

    @api.depends("move_id.name", "state", "company_id", "date")
    def _compute_name(self):
        for payment in self:
            if not payment.id or payment.state not in ("in_process", "paid"):
                continue
            if payment.name and (
                not payment.move_id or payment.name == payment.move_id.name
            ):
                continue
            payment.name = payment.move_id.name or self.env["ir.sequence"].with_company(
                payment.company_id
            ).next_by_code("account.payment", sequence_date=payment.date)

    @api.depends("company_id", "partner_id", "payment_type")
    @_debug.perf.timed
    def _compute_journal_id(self) -> None:
        default_journal_by_company = {}
        for payment in self:
            partner = payment.partner_id
            payment_type = (
                payment.payment_type
                if payment.payment_type in ("inbound", "outbound")
                else None
            )
            if not payment._origin and partner and payment_type:
                field_name = f"property_{payment_type}_payment_channel_id"
                default_payment_channel = payment.partner_id.with_company(
                    payment.company_id
                )[field_name]
                journal = default_payment_channel.journal_id
                if journal:
                    payment.journal_id = journal
                    continue

            company = payment.company_id or self.env.company
            if not payment.journal_id or company != payment.journal_id.company_id:
                if company not in default_journal_by_company:
                    default_journal_by_company[company] = self._get_default_journal(
                        company
                    )
                payment.journal_id = default_journal_by_company[company]
        _debug.logic(
            "journal_defaults_resolved",
            payment=self,
            companies_defaulted=len(default_journal_by_company),
        )

    def _get_default_journal(self, company):
        Journal = self.env["account.journal"]
        return Journal.search(Journal._get_payment_journal_domain(company), limit=1)

    @api.depends("journal_id")
    def _compute_company_id(self):
        for payment in self:
            if payment.journal_id.company_id not in payment.company_id.parent_ids:
                payment.company_id = (
                    payment.journal_id.company_id or self.env.company
                )._get_accessible_branches()[:1]

    @api.depends(
        "reconciled_invoice_ids.payment_state",
        "reconciled_bill_ids.payment_state",
        "move_id.line_ids.amount_residual",
        "move_id.line_ids.account_id.reconcile",
        *_SEEK_FOR_LINES_DEPENDS,
    )
    @_debug.perf.timed
    def _compute_state(self):
        for payment in self:
            if not payment.state:
                payment.state = "draft"
            if (move := payment.move_id) and payment.state in ("paid", "in_process"):
                liquidity, _counterpart, _writeoff = payment._seek_for_lines()
                payment.state = (
                    "paid"
                    if move.company_currency_id.is_zero(
                        sum(liquidity.mapped("amount_residual"))
                    )
                    or not any(liquidity.account_id.mapped("reconcile"))
                    else "in_process"
                )
            if (
                payment.state == "in_process"
                and (
                    moves := (
                        payment.reconciled_invoice_ids | payment.reconciled_bill_ids
                    )
                )
                and all(invoice.payment_state == "paid" for invoice in moves)
            ):
                _debug.logic("all_reconciled_invoices_paid_paid", payment=payment)
                payment.state = "paid"
            _debug.logic(
                "_compute_state",
                payment=payment,
                state=payment.state,
                move=payment.move_id,
            )

    @api.depends(
        "move_id.line_ids.amount_residual",
        "move_id.line_ids.amount_residual_currency",
        "state",
        "amount",
        "currency_id",
        "company_id.currency_id",
        *_SEEK_FOR_LINES_DEPENDS,
    )
    @_debug.perf.timed
    def _compute_reconciliation_status(self) -> None:
        for pay in self:
            liquidity_lines, counterpart_lines, writeoff_lines = pay._seek_for_lines()

            if not pay.liquidity_account_id:
                pay.is_invoice_reconciled = False
                pay.is_bank_matched = pay.state == "paid"
            elif not pay.currency_id or not pay.id or not pay.move_id:
                pay.is_invoice_reconciled = False
                pay.is_bank_matched = False
            elif pay.currency_id.is_zero(pay.amount):
                pay.is_invoice_reconciled = True
                pay.is_bank_matched = True
            else:
                residual_field = (
                    "amount_residual"
                    if pay.currency_id == pay.company_id.currency_id
                    else "amount_residual_currency"
                )
                if (
                    pay.journal_id.default_account_id
                    and pay.journal_id.default_account_id in liquidity_lines.account_id
                ):
                    pay.is_bank_matched = True
                else:
                    pay.is_bank_matched = pay.currency_id.is_zero(
                        sum(liquidity_lines.mapped(residual_field))
                    )

                reconcile_lines = (counterpart_lines + writeoff_lines).filtered(
                    lambda line: line.account_id.reconcile
                )
                pay.is_invoice_reconciled = pay.currency_id.is_zero(
                    sum(reconcile_lines.mapped(residual_field))
                )
        if _debug.logic.enabled:
            _debug.logic(
                "reconciliation_status_computed",
                payment=self,
                invoice_reconciled=len(self.filtered("is_invoice_reconciled")),
                bank_matched=len(self.filtered("is_bank_matched")),
            )

    @api.model
    def _get_method_codes_using_bank_account(self):
        return ["manual"]

    @api.model
    def _get_method_codes_needing_bank_account(self):
        return []

    @_debug.perf.timed
    def action_view_business_doc(self):
        _debug.lifecycle("action_view_business_doc", records=self)
        return {
            "name": self.env._("Payment"),
            "type": "ir.actions.act_window",
            "views": [(False, "form")],
            "res_model": "account.payment",
            "res_id": self.id,
        }

    @api.depends("payment_method_code", "journal_id.type", "state")
    def _compute_show_require_partner_bank(self) -> None:
        for payment in self:
            if payment.journal_id.type == "cash":
                payment.show_partner_bank_account = False
            else:
                payment.show_partner_bank_account = (
                    payment.payment_method_code
                    in self._get_method_codes_using_bank_account()
                )
            payment.require_partner_bank_account = (
                payment.state == "draft"
                and payment.payment_method_code
                in self._get_method_codes_needing_bank_account()
            )

    @api.depends(
        "move_id.line_ids.balance",
        "amount",
        "payment_type",
        "currency_id",
        "date",
        "company_id",
        "company_currency_id",
        *_SEEK_FOR_LINES_DEPENDS,
    )
    def _compute_amount_company_currency_signed(self) -> None:
        for payment in self:
            if payment.move_id:
                liquidity_lines = payment._seek_for_lines()[0]
                payment.amount_company_currency_signed = sum(
                    liquidity_lines.mapped("balance")
                )
            else:
                payment.amount_company_currency_signed = payment.currency_id._convert(
                    from_amount=payment.amount_signed,
                    to_currency=payment.company_currency_id,
                    company=payment.company_id,
                    date=payment.date,
                )

    @api.depends("amount", "payment_type")
    def _compute_amount_signed(self) -> None:
        for payment in self:
            if payment.payment_type == "outbound":
                payment.amount_signed = -payment.amount
            else:
                payment.amount_signed = payment.amount

    @api.depends(
        "partner_id", "company_id", "payment_type", "journal_id.bank_account_id"
    )
    def _compute_available_bank_account_ids(self) -> None:
        for pay in self:
            if pay.payment_type == "inbound":
                pay.available_bank_account_ids = pay.journal_id.bank_account_id
            else:
                pay.available_bank_account_ids = (
                    pay.partner_id.bank_account_ids.filtered_domain(
                        [("company_id", "in", [False, pay.company_id.id])]
                    )._origin
                )

    @api.depends("available_bank_account_ids", "journal_id")
    def _compute_bank_account_id(self) -> None:
        for pay in self:
            if pay.bank_account_id not in pay.available_bank_account_ids:
                pay.bank_account_id = pay.available_bank_account_ids[:1]._origin

    @api.depends("available_payment_channel_ids", "partner_id", "company_id")
    @_debug.perf.timed
    def _compute_payment_channel_id(self) -> None:
        for pay in self:
            available = pay.available_payment_channel_ids
            available_ids = set(available.ids)
            partner = pay.partner_id.with_company(pay.company_id)
            preferred = self.env["account.payment.channel"]
            if pay.payment_type in ("inbound", "outbound"):
                preferred = partner[f"property_{pay.payment_type}_payment_channel_id"]
            if preferred.id in available_ids:
                pay.payment_channel_id = preferred
            elif pay.payment_channel_id.id in available_ids:
                continue
            elif available:
                pay.payment_channel_id = available[0]._origin
            else:
                pay.payment_channel_id = False
        if _debug.logic.enabled:
            _debug.logic(
                "payment_channels_resolved",
                payment=self,
                channels=self.mapped("payment_channel_id"),
            )

    @api.depends("payment_type", "journal_id", "currency_id")
    def _compute_available_payment_channel_ids(self) -> None:
        for pay in self:
            channels = pay.journal_id._get_available_payment_channels(pay.payment_type)
            if to_exclude := pay._get_payment_method_codes_to_exclude():
                channels = channels.browse(
                    [
                        channel.id
                        for channel in channels
                        if channel.code not in to_exclude
                    ]
                )
            pay.available_payment_channel_ids = channels

    def _get_available_journals(self, company):
        return self.env["account.journal"].search(
            [
                "|",
                ("company_id", "parent_of", company.id),
                ("company_id", "child_of", company.id),
                ("type", "in", LIQUIDITY_TYPES),
            ]
        )

    @api.depends("payment_type", "company_id")
    def _compute_available_journal_ids(self) -> None:
        journals_per_company = {}
        for pay in self:
            company = pay.company_id or self.env.company
            if company not in journals_per_company:
                journals_per_company[company] = self._get_available_journals(company)
            method_lines = (
                "inbound_payment_channel_ids"
                if pay.payment_type == "inbound"
                else "outbound_payment_channel_ids"
            )
            pay.available_journal_ids = journals_per_company[company].filtered(
                method_lines
            )

    def _get_payment_method_codes_to_exclude(self):
        self.check_singleton()
        return []

    @api.depends("journal_id.currency_id", "company_id.currency_id")
    def _compute_currency_id(self) -> None:
        for pay in self:
            pay.currency_id = pay.journal_id.currency_id or pay.company_id.currency_id

    def _liquidity_account_is_mandatory(self):
        return (
            self.is_entry_required
            or not self.env["account.move"]._has_full_accounting()
        )

    @api.depends(
        "payment_channel_id", "payment_type", "company_id", "is_entry_required"
    )
    def _compute_liquidity_account_id(self) -> None:
        fallback = {}
        for pay in self:
            mandatory = pay._liquidity_account_is_mandatory()
            account = pay.payment_channel_id.payment_account_id
            if not account and mandatory:
                key = (pay.company_id, pay.payment_type)
                if key not in fallback:
                    fallback[key] = pay._get_default_liquidity_account(pay.payment_type)
                account = fallback[key]
            if not account and pay.move_id:
                _debug.logic("outstanding_account_kept_no_channel", payment=pay)
                continue
            _debug.logic(
                "outstanding",
                payment=pay,
                account=account,
                channel=pay.payment_channel_id,
                mandatory=mandatory,
            )
            pay.liquidity_account_id = account

    @api.depends(
        "journal_id", "partner_id", "partner_type", "company_id", "invoice_ids"
    )
    @_debug.perf.timed
    def _compute_counterpart_account_id(self) -> None:
        for pay in self:
            settled_account = pay._get_counterpart_account_from_settled_lines(
                pay._get_settled_counterpart_lines()
            )
            if settled_account:
                source = "settled"
                account = settled_account
            elif (
                pay.counterpart_account_id
                and pay.counterpart_account_source == "explicit"
            ):
                _debug.logic(
                    "counterpart_account_kept",
                    payment=pay,
                    account=pay.counterpart_account_id,
                    source=pay.counterpart_account_source,
                )
                continue
            else:
                candidates = pay._get_counterpart_account_candidates()
                account = candidates if len(candidates) == 1 else candidates.browse()
                source = "default" if account else False
            _debug.logic(
                "counterpart_account_resolved",
                payment=pay,
                account=account,
                source=source,
            )
            pay.counterpart_account_id = account
            pay.counterpart_account_source = source

    @api.depends(
        "journal_id",
        "partner_id",
        "partner_type",
        "company_id",
        "invoice_ids",
        "counterpart_account_source",
    )
    def _compute_is_counterpart_account_ambiguous(self) -> None:
        for pay in self:
            pay.is_counterpart_account_ambiguous = (
                pay.counterpart_account_source != "settled"
                and len(pay._get_counterpart_account_candidates()) > 1
            )

    def _get_counterpart_account_types(self) -> tuple:
        self.check_singleton()
        if self.partner_type == "customer":
            return ("asset_receivable",)
        if self.partner_type == "supplier":
            return ("liability_payable",)
        return ()

    def _get_settled_counterpart_lines(self):
        self.check_singleton()
        counterpart_lines = self.move_id.line_ids.filtered(
            lambda line: line.payment_role == "counterpart"
        )
        reconciled = (
            counterpart_lines.matched_debit_ids.debit_move_id
            | counterpart_lines.matched_credit_ids.credit_move_id
        ) - counterpart_lines
        if reconciled:
            return reconciled
        account_types = self._get_counterpart_account_types()
        return self.invoice_ids.line_ids.filtered(
            lambda line: line.account_id.account_type in account_types
        )

    def _get_counterpart_account_from_settled_lines(self, lines):
        self.check_singleton()
        accounts = lines.account_id
        return accounts if len(accounts) == 1 else accounts.browse()

    def _get_counterpart_account_candidates(self):
        self.check_singleton()
        Account = self.env["account.account"]
        partner_property = {
            "customer": "property_account_receivable_id",
            "supplier": "property_account_payable_id",
        }.get(self.partner_type)
        if not partner_property:
            return Account
        if self.partner_id:
            return self.partner_id.with_company(self.company_id)[partner_property]
        return (
            Account.with_company(self.company_id)
            .search(
                [
                    *Account._get_domain_company_compatible(self.company_id),
                    ("account_type", "in", self._get_counterpart_account_types()),
                ],
                limit=1,
            )
            .with_env(self.env)
        )

    def _classify_counterpart_account_source(self) -> None:
        for pay in self:
            account = pay.counterpart_account_id
            if not account:
                source = False
            elif account == pay._get_counterpart_account_from_settled_lines(
                pay._get_settled_counterpart_lines()
            ):
                source = "settled"
            elif account == pay._get_counterpart_account_candidates():
                source = "default"
            else:
                source = "explicit"
            _debug.logic(
                "counterpart_account_source_classified",
                payment=pay,
                account=account,
                source=source,
            )
            if pay.counterpart_account_source != source:
                pay.counterpart_account_source = source

    @api.model
    def _get_entry_line_signature(self, line) -> tuple:
        read = line.get if isinstance(line, dict) else line.__getitem__
        account_id, partner_id, currency_id = (
            value.id if isinstance(value, models.BaseModel) else value or False
            for value in (read("account_id"), read("partner_id"), read("currency_id"))
        )
        currency = self.env["res.currency"].browse(currency_id)
        return (
            account_id,
            partner_id,
            currency_id,
            currency.round(read("amount_currency") or 0.0),
        )

    def _describe_entry_lines(self, signatures) -> str:
        return ", ".join(
            self.env._(
                "%(account)s %(amount)s",
                account=self.env["account.account"].browse(account_id).display_name,
                amount=amount,
            )
            for account_id, _partner_id, _currency_id, amount in signatures
        ) or self.env._("nothing")

    def _get_entry_mismatches(self) -> list:
        self.check_singleton()
        empty = self.env["account.move.line"]
        lines_by_role = self.move_id.line_ids.grouped("payment_role")
        if "counterpart" not in lines_by_role:
            return []
        expected = self._prepare_move_lines_per_type(
            write_off_line_vals=[
                {"amount_currency": line.amount_currency, "balance": line.balance}
                for line in lines_by_role.get("write_off", empty)
            ]
        )
        role_labels = dict(
            self.env["account.move.line"]
            ._fields["payment_role"]
            ._description_selection(self.env)
        )
        mismatches = []
        if unowned := lines_by_role.get(False):
            mismatches.append(
                self.env._(
                    "%(lines)s are not generated by the payment",
                    lines=", ".join(unowned.mapped("display_name")),
                )
            )
        for role in _CHECKED_ROLES:
            actual = sorted(
                self._get_entry_line_signature(line)
                for line in lines_by_role.get(role, empty)
            )
            generated = sorted(
                self._get_entry_line_signature(vals)
                for vals in expected[f"{role}_lines"]
            )
            if actual != generated:
                mismatches.append(
                    self.env._(
                        "%(role)s: the entry holds %(actual)s, the payment generates "
                        "%(generated)s",
                        role=role_labels[role],
                        actual=self._describe_entry_lines(actual),
                        generated=self._describe_entry_lines(generated),
                    )
                )
        return mismatches

    def _check_entry_matches_payment(self) -> None:
        for pay in self:
            if not (mismatches := pay._get_entry_mismatches()):
                continue
            _debug.logic("entry_mismatch_refused", payment=pay, mismatches=mismatches)
            raise UserError(
                self.env._(
                    "%(move)s no longer matches %(payment)s, which generated it:\n"
                    "%(mismatches)s\n"
                    "Correct the payment instead: reset it to draft, edit it and "
                    "confirm it, or use Correct Accounts.",
                    move=pay.move_id.display_name,
                    payment=pay.display_name,
                    mismatches="\n".join(mismatches),
                )
            )

    def _is_entry_locked(self) -> bool:
        self.check_singleton()
        move = self.move_id
        return bool(
            move.inalterable_hash
            or move.need_cancel_request
            or self.company_id._get_lock_date_violations(
                move.date,
                fiscalyear=True,
                sale=False,
                purchase=False,
                tax=False,
                hard=True,
            )
        )

    def _correct_accounts(self, vals) -> None:
        self.check_singleton()
        _debug.lifecycle("correct_accounts", payment=self, fields=sorted(vals))
        self.action_draft()
        self.write(vals)
        self.action_post()

    def _get_entry_correction_hint(self) -> str:
        return self.env._(
            "reset the payment to draft and edit it, or use Correct Accounts on a "
            "posted one."
        )

    def action_align_counterpart_to_entry(self) -> None:
        for pay in self.filtered("counterpart_review_required"):
            counterpart = pay._seek_for_lines()[1]
            if len(counterpart.account_id) != 1:
                raise UserError(
                    self.env._(
                        "%(payment)s has no single counterpart line to align to.",
                        payment=pay.display_name,
                    )
                )
            old_account = pay.counterpart_account_id
            pay.write(
                {
                    "counterpart_account_id": counterpart.account_id.id,
                    "counterpart_account_source": "settled"
                    if counterpart.matched_debit_ids or counterpart.matched_credit_ids
                    else "explicit",
                    "counterpart_review_required": False,
                }
            )
            _debug.lifecycle(
                "counterpart_aligned_to_entry",
                payment=pay,
                old=old_account,
                new=counterpart.account_id,
            )
            pay.message_post(
                body=self.env._(
                    "Counterpart account aligned to the journal entry after review: "
                    "%(old)s → %(new)s.",
                    old=old_account.display_name or self.env._("none"),
                    new=counterpart.account_id.display_name,
                )
            )

    def _is_money_moving(self) -> bool:
        self.check_singleton()
        return any(
            line.account_id.account_type in self._get_liquidity_account_types()
            for line in self.move_id.line_ids
        )

    def action_convert_to_entry(self):
        if moving := self.filtered(
            lambda pay: not pay.move_id or pay._is_money_moving()
        ):
            raise UserError(
                self.env._(
                    "Only a payment whose journal entry moves no money can become a "
                    "plain journal entry: %(payments)s.",
                    payments=", ".join(moving.mapped("display_name")),
                )
            )
        moves = self.move_id
        self._convert_to_entry()
        return moves._get_records_action(name=self.env._("Journal Entries"))

    def _convert_to_entry(self) -> None:
        if not self:
            return
        notes = {
            pay.move_id: self.env._(
                "Converted from the payment %(payment)s: it moved no money, so it "
                "is a journal entry settling documents from an advance or another "
                "account. The payment's history is kept here.",
                payment=pay.display_name,
            )
            for pay in self
        }
        pairs = [(pay.id, pay.move_id.id) for pay in self]
        _debug.lifecycle("payments_converted_to_entries", payments=self)
        self.env.flush_all()
        self.env["account.move"]._move_payment_records_to_entries(pairs)
        self.env.invalidate_all()
        for move, note in notes.items():
            move.message_post(body=note)

    def action_open_correct_accounts(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Correct Accounts"),
            "res_model": "wizard.account.payment.correct.accounts",
            "view_mode": "form",
            "target": "new",
            "context": {"default_payment_id": self.id},
        }

    @api.model
    def _get_liquidity_account_types(self) -> tuple:
        return ("asset_cash", "liability_credit_card", "asset_current")

    def _check_liquidity_account(self) -> None:
        liquidity_types = self._get_liquidity_account_types()
        for pay in self:
            account = pay.liquidity_account_id
            if account.account_type in liquidity_types:
                continue
            _debug.logic("liquidity_account_refused", payment=pay, account=account)
            raise UserError(
                self.env._(
                    "%(payment)s would book its money on %(account)s, which is not a "
                    "bank, cash, card or outstanding account: a payment moves money. "
                    "To settle documents from an advance, or from a payment a third "
                    "party made in the company's name, use Apply Advance on them.",
                    payment=pay.display_name,
                    account=account.display_name,
                )
            )

    def _check_counterpart_account(self) -> None:
        for pay in self:
            if pay.counterpart_account_id:
                continue
            candidates = pay._get_counterpart_account_candidates()
            raise UserError(
                self.env._(
                    "Choose the counterpart account of %(payment)s: it settles no "
                    "document to take it from, and %(candidates)s are all valid for "
                    "%(partner)s.",
                    payment=pay.display_name,
                    candidates=", ".join(candidates.mapped("display_name")),
                    partner=pay.partner_id.display_name or pay.company_id.display_name,
                )
                if len(candidates) > 1
                else self.env._(
                    "Choose the counterpart account of %(payment)s.",
                    payment=pay.display_name,
                )
            )

    @api.depends(
        "bank_account_id",
        "amount",
        "memo",
        "currency_id",
        "journal_id",
        "move_id.state",
        "payment_channel_id",
        "payment_type",
        "state",
    )
    def _compute_qr_code(self) -> None:
        for pay in self:
            pay.qr_code = (
                pay._render_payment_qr_code(pay.amount, pay.memo)
                if pay.state in ("draft", "in_process")
                else False
            )

    def _get_reconciled_invoices_per_payment(self, stored_payments):
        return self.env.execute_query(
            SQL(
                _SQL_RECONCILED_INVOICES_PER_PAYMENT,
                payment_ids=stored_payments.ids,
                account_types=self._get_valid_payment_account_types(),
                move_types=list(
                    self.env["account.move"].get_sale_types(True)
                    + self.env["account.move"].get_purchase_types(True)
                ),
            )
        )

    def _get_reconciled_statement_lines_per_payment(self, stored_payments):
        return dict(
            self.env.execute_query(
                SQL(
                    _SQL_RECONCILED_STATEMENT_LINES_PER_PAYMENT,
                    payment_ids=stored_payments.ids,
                )
            )
        )

    @api.depends(
        "move_id.line_ids.matched_debit_ids",
        "move_id.line_ids.matched_credit_ids",
        "invoice_ids",
    )
    @_debug.perf.timed
    def _compute_stat_buttons_from_reconciliation(self) -> None:
        stored_payments = self.filtered("id")
        _debug.logic(
            "stat_buttons_scope",
            payment=self,
            stored=len(stored_payments),
            skipped=not stored_payments,
        )
        if not stored_payments:
            self.reconciled_invoice_ids = False
            self.reconciled_invoices_type = False
            self.reconciled_bill_ids = False
            self.reconciled_statement_line_ids = False
            return

        self.env["account.payment"].flush_model(
            fnames=["move_id", "liquidity_account_id"]
        )
        self.env["account.move"].flush_model(fnames=["move_type", "statement_line_id"])
        self.env["account.move.line"].flush_model(
            fnames=["move_id", "account_id", "statement_line_id"]
        )
        self.env["account.partial.reconcile"].flush_model(
            fnames=["debit_move_id", "credit_move_id"]
        )

        invoices_per_payment = self._get_reconciled_invoices_per_payment(
            stored_payments
        )
        _debug.perf.count("reconciled_invoices_fetched", rows=len(invoices_per_payment))

        query_res = self._get_reconciled_statement_lines_per_payment(stored_payments)
        _debug.perf.count("reconciled_statement_lines_fetched", rows=len(query_res))
        sale_types = self.env["account.move"].get_sale_types(True)

        invoices_by_payment = defaultdict(list)
        bills_by_payment = defaultdict(list)
        for payment_id, invoice_ids, move_type in invoices_per_payment:
            target = (
                invoices_by_payment if move_type in sale_types else bills_by_payment
            )
            target[payment_id].extend(invoice_ids)

        _debug.pipeline(
            "reconciled_documents_grouped",
            payment=stored_payments,
            with_invoices=len(invoices_by_payment),
            with_bills=len(bills_by_payment),
            with_statement_lines=len(query_res),
        )
        for pay in self:
            invoices = pay.invoice_ids.filtered(lambda m: m.is_sale_document(True))
            bills = pay.invoice_ids.filtered(lambda m: m.is_purchase_document(True))
            invoices |= self.env["account.move"].browse(
                invoices_by_payment.get(pay.id, ())
            )
            bills |= self.env["account.move"].browse(bills_by_payment.get(pay.id, ()))

            pay.reconciled_invoice_ids = invoices
            pay.reconciled_bill_ids = bills
            pay.reconciled_statement_line_ids = [Command.set(query_res.get(pay.id, []))]
            pay.reconciled_invoices_type = (
                "credit_note"
                if set(invoices.mapped("move_type")) == {"out_refund"}
                else "invoice"
            )

    def _compute_payment_receipt_title(self) -> None:
        self.payment_receipt_title = self.env._("Payment Receipt")

    @api.depends(
        "partner_id",
        "amount",
        "date",
        "payment_type",
        "company_id",
        "currency_id",
        "state",
    )
    def _compute_duplicate_payment_ids(self) -> None:
        payment_to_duplicate_move = self._get_duplicate_reference()
        _debug.perf.count(
            "duplicate_payments_fetched", rows=len(payment_to_duplicate_move)
        )
        for payment in self:
            payment.duplicate_payment_ids = payment_to_duplicate_move.get(
                payment._origin.id, self.env["account.payment"]
            )

    @_debug.perf.timed
    def _search_reconciled_move_ids(self, operator, value, move_filter=None):
        if operator not in ("in", "="):
            return NotImplemented

        def payment_ids(moves):
            if move_filter is not None:
                moves = moves.filtered(move_filter)
            return moves.filtered(_may_hold_payments).reconciled_payment_ids.ids

        moves = self.env["account.move"].browse(value)
        try:
            ids = payment_ids(moves)
        except MissingError:
            ids = payment_ids(moves.exists())
        return [("id", "in", ids)]

    @_debug.perf.timed
    def _search_reconciled_invoice_ids(self, operator, value):
        return self._search_reconciled_move_ids(
            operator, value, lambda move: move.is_sale_document(True)
        )

    @_debug.perf.timed
    def _search_reconciled_bill_ids(self, operator, value):
        return self._search_reconciled_move_ids(
            operator, value, lambda move: move.is_purchase_document(True)
        )

    @_debug.perf.timed
    def _get_duplicate_reference(self, matching_states=("draft", "in_process")):
        if len(self) > 1 and not all(self._ids):
            return {
                payment_id: duplicates
                for payment in self
                for payment_id, duplicates in payment._get_duplicate_reference(
                    matching_states
                ).items()
            }
        payments = self.filtered(
            lambda p: p.partner_id and p.amount and p.state != "in_process"
        )
        _debug.pipeline(
            "duplicate_candidates_filtered",
            payment=self,
            candidates=len(payments),
            unsaved=not all(self._ids),
            matching_states=matching_states,
        )
        if not payments:
            return {}

        matched_fields = (
            "company_id",
            "partner_id",
            "date",
            "amount",
            "payment_type",
            "currency_id",
        )
        self.flush_model((*matched_fields, "state"))

        payment_table_and_alias = SQL("account_payment AS payment")
        if not all(self._ids):
            self.check_singleton()
            values = {
                field_name: self._fields[field_name].convert_to_write(
                    self[field_name], self
                )
                or None
                for field_name in matched_fields
            }
            values["id"] = self._origin.id or 0
            casted_values = SQL(", ").join(
                SQL(
                    "%s::%s",
                    value,
                    SQL.identifier(self._fields[field_name].column_type[0]),
                )
                for field_name, value in values.items()
            )
            column_names = SQL(", ").join(
                SQL.identifier(field_name) for field_name in values
            )
            payment_table_and_alias = SQL(
                "(VALUES (%s)) AS payment(%s)", casted_values, column_names
            )

        query = SQL(
            """
                SELECT payment.id AS payment_id,
                       ARRAY_AGG(DISTINCT duplicate_payment.id) AS duplicate_payment_ids
                  FROM %(payment_table_and_alias)s
                  JOIN account_payment AS duplicate_payment ON payment.id != duplicate_payment.id
                                                           AND payment.partner_id = duplicate_payment.partner_id
                                                           AND payment.company_id = duplicate_payment.company_id
                                                           AND payment.date = duplicate_payment.date
                                                           AND payment.payment_type = duplicate_payment.payment_type
                                                           AND payment.amount = duplicate_payment.amount
                                                           AND payment.currency_id = duplicate_payment.currency_id
                                                           AND duplicate_payment.state IN %(matching_states)s
                 WHERE payment.id = ANY(%(payments)s)
              GROUP BY payment.id
            """,
            payment_table_and_alias=payment_table_and_alias,
            matching_states=tuple(matching_states),
            payments=payments.ids or [0],
        )

        return {
            payment_id: self.env["account.payment"].browse(duplicate_ids)
            for payment_id, duplicate_ids in self.env.execute_query(query)
        }

    def _inverse_memo(self) -> None:
        for payment in self:
            payment.move_id.ref = payment.memo

    @api.constrains("payment_channel_id")
    @_debug.perf.timed
    def _check_payment_channel_id(self) -> None:
        for pay in self:
            if not pay.payment_channel_id:
                raise ValidationError(
                    self.env._("Please define a payment method line on your payment.")
                )
            if (
                pay.payment_channel_id.journal_id
                and pay.payment_channel_id.journal_id != pay.journal_id
            ):
                raise ValidationError(
                    self.env._(
                        "The selected payment method is not available for this payment, please select the payment method again."
                    )
                )

    def _is_counterpart_account_type_enforced(self) -> bool:
        return False

    @api.constrains("counterpart_account_id")
    def _check_counterpart_account_type(self) -> None:
        valid_types = self._get_valid_payment_account_types()
        for pay in self:
            account = pay.counterpart_account_id
            if (
                account
                and account.account_type not in valid_types
                and pay._is_counterpart_account_type_enforced()
            ):
                raise ValidationError(
                    self.env._(
                        "The counterpart account of %(payment)s must be a receivable "
                        "or payable account, not %(account)s.",
                        payment=pay.display_name,
                        account=account.display_name,
                    )
                )

    @api.constrains("state", "move_id")
    @_debug.perf.timed
    def _check_move_id(self) -> None:
        for payment in self:
            if payment.state in ("draft", "canceled") or payment.move_id:
                continue
            if (
                payment.liquidity_account_id
                or payment._liquidity_account_is_mandatory()
            ):
                raise ValidationError(
                    self.env._(
                        "A payment with an outstanding account cannot be confirmed without having a journal entry."
                    )
                )

    @api.model_create_multi
    @_debug.perf.timed
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                model=self._name,
                count=len(vals_list),
                fields=sorted({key for vals in vals_list for key in vals}),
            )
        if self.env.context.get("force_payment_move"):
            for vals in vals_list:
                vals.setdefault("is_entry_required", True)
        entry_vals_list = [
            (
                vals.pop("write_off_line_vals", None),
                vals.pop("force_balance", None),
                vals.pop("line_ids", None),
            )
            for vals in vals_list
        ]

        payments = super().create(vals_list)
        payments.browse(
            [
                pay.id
                for pay, vals in zip(payments, vals_list, strict=True)
                if vals.get("counterpart_account_id")
                and vals.get("counterpart_account_source") != "settled"
            ]
        )._classify_counterpart_account_source()

        default_entry_payments = self.env["account.payment"]
        entry_payments_vals = []
        for pay, vals, (write_off_line_vals, force_balance, line_ids) in zip(
            payments, vals_list, entry_vals_list, strict=True
        ):
            if (
                write_off_line_vals is None
                and force_balance is None
                and line_ids is None
            ):
                continue
            entry_payments_vals.append((pay, vals))
            if not write_off_line_vals and force_balance is None and not line_ids:
                default_entry_payments |= pay
                continue
            _debug.pipeline(
                "create_journal_entry_explicit_vals",
                payment=pay,
                write_off=write_off_line_vals is not None,
                force_balance=force_balance is not None,
                line_ids=line_ids is not None,
            )
            pay._create_journal_entry(
                write_off_line_vals=write_off_line_vals,
                force_balance=force_balance,
                line_ids=line_ids,
            )
        default_entry_payments._create_journal_entry()
        moves_per_vals = []
        for pay, vals in entry_payments_vals:
            if not (move_vals := pay._move_vals_from_related(vals)):
                continue
            for written_vals, moves in moves_per_vals:
                if written_vals == move_vals:
                    moves.append(pay.move_id.id)
                    break
            else:
                moves_per_vals.append((move_vals, [pay.move_id.id]))
        for move_vals, move_ids in moves_per_vals:
            self.env["account.move"].browse(move_ids).with_context(
                entry_owner_sync=True
            ).write(move_vals)
        return payments

    def _move_vals_from_related(self, vals) -> dict:
        return {
            fname: value
            for fname, value in vals.items()
            if (self._fields[fname].related or "").split(".")[0] == "move_id"
        }

    def _get_default_liquidity_account(self, payment_type):
        account_ref = (
            "account_journal_payment_debit_account_id"
            if payment_type == "inbound"
            else "account_journal_payment_credit_account_id"
        )
        chart_template = self.with_context(
            allowed_company_ids=self.company_id.root_id.ids
        ).env["account.chart.template"]
        outstanding_account = (
            chart_template.ref(account_ref, raise_if_not_found=False)
            or self.company_id.account_config_id.transfer_account_id
        )
        if not outstanding_account:
            raise UserError(
                self.env._("No outstanding account could be found to make the payment")
            )
        return outstanding_account

    @_debug.perf.timed
    def write(self, vals):
        _debug.lifecycle("write", records=self, fields=sorted(vals))
        if _debug.lifecycle.enabled and "state" in vals:
            _debug.lifecycle(
                "state_change",
                payment=self,
                state=set(self.mapped("state")),
                state_to=vals["state"],
            )
        if (
            vals.get("state") in ("in_process", "paid")
            and not vals.get("move_id")
            and not self.env.context.get(_ENTRIES_JUST_CREATED)
        ):
            self.filtered(lambda p: not p.move_id)._create_journal_entry()
            draft_moves = self.move_id.filtered(lambda m: m.state == "draft")
            _debug.pipeline("posting_moves", payment=self, draft_moves=draft_moves)
            draft_moves.action_post()

        res = super().write(vals)
        if (
            "counterpart_account_id" in vals
            and vals.get("counterpart_account_source") != "settled"
        ):
            self._classify_counterpart_account_source()
        if with_move := self.filtered("move_id"):
            with_move._sync_to_moves(set(vals.keys()))
            unsettled = self.env.cr.cache.pop(_PAYMENTS_UNSETTLED, set())
            with_move.filtered(
                lambda pay: (
                    pay.id in unsettled
                    and pay.move_id.state == "draft"
                    and pay.counterpart_account_id
                )
            )._sync_to_moves({"counterpart_account_id"})
        return res

    @_debug.perf.timed
    def unlink(self):
        _debug.lifecycle("unlink", unlink=self)
        moves = self.move_id
        res = super().unlink()
        moves.filtered(lambda m: m.state != "draft").action_draft()
        moves.unlink()
        return res

    @api.depends("name")
    def _compute_display_name(self):
        for payment in self:
            payment.display_name = payment.name or self.env._("Draft Payment")

    @_debug.perf.timed
    def copy_data(self, default=None):
        _debug.lifecycle("copy_data", records=self)
        vals_list = super().copy_data(dict(default or {}))
        for payment, vals in zip(self, vals_list, strict=True):
            vals.setdefault("payment_channel_id", payment.payment_channel_id.id)
        return vals_list

    def _message_mail_after_hook(self, mails):
        for payment, mail in zip(self, mails, strict=False):
            if not payment.message_main_attachment_id and (
                attachments_to_link := mail.attachment_ids.filtered(
                    lambda a: a.res_model == "mail.message"
                )
            ):
                attachments_to_link.write(
                    {"res_model": self._name, "res_id": payment.id}
                )
        return super()._message_mail_after_hook(mails)

    @api.model
    @_debug.perf.timed
    def _prepare_line_commands(self, lines, line_vals):
        commands = []
        for line, vals in zip_longest(lines, line_vals):
            if line is not None and vals is not None:
                commands.append(Command.update(line.id, vals))
            elif vals is not None:
                commands.append(Command.create(vals))
            else:
                commands.append(Command.delete(line.id))
        return commands

    @_debug.perf.timed
    def _sync_to_moves(self, changed_fields):
        if not any(
            field_name in changed_fields
            for field_name in self._get_trigger_fields_to_synchronize()
        ):
            return

        for pay in self:
            if pay.move_id.state == "posted":
                _debug.logic("_sync_to_moves_move_posted_not_synced", payment=pay)
                continue
            if pay.counterpart_review_required:
                raise UserError(
                    self.env._(
                        "The counterpart account of %(payment)s differs from its "
                        "journal entry's and awaits review: align the payment to "
                        "its entry before editing it.",
                        payment=pay.display_name,
                    )
                )
            lines_by_role = pay.move_id.line_ids.grouped("payment_role")
            empty = self.env["account.move.line"]
            liquidity_lines = lines_by_role.get("liquidity", empty)
            counterpart_lines = lines_by_role.get("counterpart", empty)
            withholding_lines = lines_by_role.get("withholding", empty)
            write_off_lines = lines_by_role.get("write_off", empty)
            if _debug.pipeline.enabled:
                _debug.pipeline(
                    "_sync_to_moves",
                    payment=pay,
                    fields=sorted(changed_fields),
                    liquidity=liquidity_lines,
                    counterpart=counterpart_lines,
                    withholding=withholding_lines,
                    writeoff=write_off_lines,
                )

            if "amount" in changed_fields and len(liquidity_lines) > 1:
                raise UserError(
                    self.env._(
                        "You cannot change the amount of a payment with multiple liquidity lines."
                    )
                )

            line_vals_per_type = pay._prepare_move_lines_per_type(
                write_off_line_vals=[
                    {"amount_currency": line.amount_currency, "balance": line.balance}
                    for line in write_off_lines
                ]
            )
            line_ids_commands = [
                *self._prepare_line_commands(
                    liquidity_lines, line_vals_per_type["liquidity_lines"]
                ),
                *self._prepare_line_commands(
                    counterpart_lines, line_vals_per_type["counterpart_lines"]
                ),
                *self._prepare_line_commands(
                    withholding_lines, line_vals_per_type["withholding_lines"]
                ),
            ]
            to_write = {
                "date": pay.date,
                "partner_id": pay.partner_id.id,
                "currency_id": pay.currency_id.id,
                "bank_account_id": pay.bank_account_id.id,
                "line_ids": line_ids_commands,
            }
            if "journal_id" in changed_fields:
                to_write.update(
                    {
                        "name": "/",
                        "journal_id": pay.journal_id.id,
                    }
                )
            pay.move_id.with_context(
                skip_invoice_sync=True, entry_owner_sync=True
            ).write(to_write)

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        return (
            "date",
            "amount",
            "payment_type",
            "partner_type",
            "memo",
            "payment_channel_id",
            "currency_id",
            "partner_id",
            "counterpart_account_id",
            "liquidity_account_id",
            "bank_account_id",
            "journal_id",
        )

    @_debug.perf.timed
    def _create_journal_entry(
        self, write_off_line_vals=None, force_balance=None, line_ids=None
    ) -> None:
        if len(self) > 1 and (write_off_line_vals or force_balance or line_ids):
            raise ValueError(
                "write_off_line_vals, force_balance and line_ids describe one "
                "entry and cannot be applied to a recordset."
            )
        need_move = self.filtered(lambda p: not p.move_id and p.liquidity_account_id)

        move_vals = [
            pay._generate_move_vals(write_off_line_vals, force_balance, line_ids)
            for pay in need_move
        ]
        moves = self.env["account.move"].with_context(is_payment=True).create(move_vals)
        _debug.pipeline(
            "_create_journal_entry",
            payment=need_move,
            moves=moves,
            skipped=self - need_move,
        )
        need_move._write_many2one_multi("move_id", moves.ids)
        need_move.with_context(**{_ENTRIES_JUST_CREATED: True}).write(
            {"state": "in_process"}
        )

    def _link_matched_invoices(self, invoices_per_payment) -> None:
        links = defaultdict(list)
        for payment, invoices in zip(self, invoices_per_payment, strict=True):
            for invoice in invoices:
                links[invoice].append(Command.link(payment.id))
        invoices = self.env["account.move"].concat(*links)
        invoices._write_x2many_multi(
            "matched_payment_ids", [links[invoice] for invoice in invoices]
        )

    @_debug.perf.timed
    def _generate_move_vals(
        self, write_off_line_vals=None, force_balance=None, line_ids=None
    ) -> dict:
        self.check_singleton()
        return {
            "move_type": "entry",
            "ref": self.memo,
            "date": self.date,
            "journal_id": self.journal_id.id,
            "company_id": self.company_id.id,
            "partner_id": self.partner_id.id,
            "currency_id": self.currency_id.id,
            "bank_account_id": self.bank_account_id.id,
            "line_ids": line_ids
            or [
                Command.create(line_vals)
                for line_vals in self._prepare_move_line_default_vals(
                    write_off_line_vals=write_off_line_vals,
                    force_balance=force_balance,
                )
            ],
        }

    def _prepare_payment_receipt_report_values(self):
        self.check_singleton()
        return {
            "display_invoices": True,
            "display_payment_method": True,
        }

    def mark_as_sent(self) -> None:
        self.write({"is_sent": True})

    def unmark_as_sent(self) -> None:
        self.write({"is_sent": False})

    @_debug.perf.timed
    def action_post(self):
        _debug.lifecycle("action_post", records=self)
        for payment in self:
            if (
                payment.require_partner_bank_account
                and not payment.bank_account_id.allow_out_payment
                and payment.payment_type == "outbound"
            ):
                raise UserError(
                    self.env._(
                        "To record payments with %(method_name)s, the recipient bank account must be manually validated. "
                        "You should go on the partner bank account of %(partner)s in order to validate it.",
                        method_name=payment.payment_channel_id.name,
                        partner=payment.partner_id.display_name,
                    )
                )
        postable = self.filtered(
            lambda pay: pay.state in {False, "draft", "in_process"}
        )
        postable._check_counterpart_account()
        cash_payments = postable.filtered(
            lambda pay: pay.liquidity_account_id.account_type == "asset_cash"
        )
        _debug.logic(
            "action_post_cash_payments_straight_paid",
            cash_payments=cash_payments,
            skipped=self - postable,
        )
        cash_payments.state = "paid"
        (postable - cash_payments).state = "in_process"

    @_debug.perf.timed
    def action_validate(self):
        _debug.lifecycle("action_validate", records=self)
        self.state = "paid"

    @_debug.perf.timed
    def action_reject(self):
        _debug.lifecycle("action_reject", records=self)
        self.state = "rejected"

    @_debug.perf.timed
    def action_cancel(self):
        _debug.lifecycle("action_cancel", records=self)
        moves = self.move_id
        draft_moves = moves.filtered(lambda m: m.state == "draft")
        self.state = "canceled"
        (moves - draft_moves).action_cancel()
        draft_moves.unlink()

    @_debug.perf.timed
    def button_request_cancel(self):
        _debug.lifecycle("button_request_cancel", records=self)
        return self.move_id.button_request_cancel()

    @_debug.perf.timed
    def action_draft(self):
        _debug.lifecycle("action_draft", records=self)
        self.state = "draft"
        self.move_id.action_draft()

    @_debug.perf.timed
    def button_open_invoices(self):
        _debug.lifecycle("button_open_invoices", records=self)
        self.check_singleton()
        return self.reconciled_invoice_ids.with_context(
            create=False
        )._get_records_action(
            name=self.env._("Paid Invoices"),
        )

    @_debug.perf.timed
    def button_open_bills(self):
        _debug.lifecycle("button_open_bills", records=self)
        self.check_singleton()
        return self.reconciled_bill_ids.with_context(create=False)._get_records_action(
            name=self.env._("Paid Bills"),
        )

    @_debug.perf.timed
    def button_open_journal_entry(self):
        _debug.lifecycle("button_open_journal_entry", records=self)
        self.check_singleton()
        return self.move_id.with_context(create=False)._get_records_action(
            name=self.env._("Journal Entry"),
        )
