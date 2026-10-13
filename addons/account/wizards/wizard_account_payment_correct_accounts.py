from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardAccountPaymentCorrectAccounts(models.TransientModel):
    _name = "wizard.account.payment.correct.accounts"
    _description = "Correct the accounts of a posted payment"
    _check_company_auto = True

    payment_id = fields.Many2one(
        comodel_name="account.payment",
        readonly=True,
        required=True,
    )
    company_id = fields.Many2one(related="payment_id.company_id")
    payment_type = fields.Selection(related="payment_id.payment_type")
    counterpart_account_types = fields.Char(
        compute="_compute_counterpart_account_types",
    )
    counterpart_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Counterpart Account",
        compute="_compute_accounts",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
        domain="[('account_type', 'in', counterpart_account_types.split(','))]",
        check_company=True,
    )
    liquidity_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Liquidity Account",
        compute="_compute_accounts",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'off_balance'))]",
        check_company=True,
    )
    is_locked = fields.Boolean(compute="_compute_is_locked")
    date = fields.Date(
        string="Reclassification Date",
        default=fields.Date.context_today,
        required=True,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Reclassification Journal",
        compute="_compute_journal_id",
        precompute=True,
        store=True,
        readonly=False,
        domain="[('type', '=', 'general')]",
        check_company=True,
    )

    @api.depends("payment_id")
    def _compute_counterpart_account_types(self) -> None:
        for wizard in self:
            wizard.counterpart_account_types = ",".join(
                self.env["account.payment"]._get_valid_payment_account_types()
            )

    @api.depends("payment_id")
    def _compute_accounts(self) -> None:
        for wizard in self:
            payment = wizard.payment_id
            wizard.counterpart_account_id = payment.counterpart_account_id
            wizard.liquidity_account_id = payment.liquidity_account_id

    @api.depends("payment_id")
    def _compute_is_locked(self) -> None:
        for wizard in self:
            wizard.is_locked = wizard.payment_id._is_entry_locked()

    @api.depends("company_id")
    def _compute_journal_id(self) -> None:
        Journal = self.env["account.journal"]
        general_journals = Journal.search(
            [
                *Journal._check_company_domain(self.company_id),
                ("type", "=", "general"),
            ]
        )
        for wizard in self:
            wizard.journal_id = (
                wizard.company_id.account_config_id.automatic_entry_default_journal_id
                or general_journals.filtered_domain(
                    Journal._check_company_domain(wizard.company_id)
                )[:1]
            )

    def _get_changes(self) -> dict:
        self.check_singleton()
        payment = self.payment_id
        changes = {}
        if self.counterpart_account_id != payment.counterpart_account_id:
            changes["counterpart_account_id"] = (
                payment.counterpart_account_id,
                self.counterpart_account_id,
            )
        if self.liquidity_account_id != payment.liquidity_account_id:
            changes["liquidity_account_id"] = (
                payment.liquidity_account_id,
                self.liquidity_account_id,
            )
        return changes

    def action_correct(self):
        self.check_singleton()
        payment = self.payment_id
        if payment.state not in ("in_process", "paid") or not payment.move_id:
            raise UserError(
                self.env._(
                    "Only a confirmed payment with a journal entry has accounts to correct."
                )
            )
        if not (changes := self._get_changes()):
            raise UserError(
                self.env._("Choose an account different from the current one.")
            )
        if self.env["account.move"].search_count(
            [("reclassified_payment_id", "=", payment.id), ("state", "=", "posted")],
            limit=1,
        ):
            raise UserError(
                self.env._(
                    "This payment's accounts were already reclassified by a journal "
                    "entry; correct that entry instead."
                )
            )
        if (
            "counterpart_account_id" in changes
            and self.counterpart_account_id.account_type
            not in payment._get_valid_payment_account_types()
        ):
            raise UserError(
                self.env._(
                    "A payment's counterpart must be a receivable or payable account."
                )
            )
        _debug.lifecycle(
            "payment_accounts_corrected",
            payment=payment,
            locked=self.is_locked,
            fields=sorted(changes),
        )
        if self.is_locked:
            entry = self._reclassify(changes)
        else:
            payment._correct_accounts(
                {fname: new.id for fname, (_old, new) in changes.items()}
            )
            entry = payment.move_id
        payment.message_post(body=self._get_note(changes, entry))
        return {"type": "ir.actions.act_window_close"}

    def _get_note(self, changes, entry):
        labels = {
            "counterpart_account_id": self.env._("Counterpart account"),
            "liquidity_account_id": self.env._("Liquidity account"),
        }
        items = Markup("").join(
            Markup("<li>%s: %s &rarr; %s</li>")
            % (labels[fname], old.display_name, new.display_name)
            for fname, (old, new) in changes.items()
        )
        if self.is_locked:
            intro = self.env._(
                "Accounts reclassified by %(entry)s, the payment's entry being in a "
                "locked period:",
                entry=entry._get_html_link(),
            )
        else:
            intro = self.env._("Accounts corrected on the payment and its entry:")
        return Markup("%s<ul>%s</ul>") % (intro, items)

    def _reclassify(self, changes):
        self.check_singleton()
        payment = self.payment_id
        if not self.journal_id:
            raise UserError(
                self.env._("Choose the journal of the reclassification entry.")
            )
        liquidity, counterpart, _other = payment._seek_for_lines()
        lines_per_field = {
            "counterpart_account_id": counterpart,
            "liquidity_account_id": liquidity,
        }
        line_vals = []
        to_match = []
        for fname, (old, new) in changes.items():
            for line in lines_per_field[fname]:
                if line.account_id.is_reconcilable:
                    balance = line.amount_residual
                    amount_currency = line.amount_residual_currency
                else:
                    balance = line.balance
                    amount_currency = line.amount_currency
                if line.currency_id.is_zero(
                    amount_currency
                ) and line.company_currency_id.is_zero(balance):
                    _debug.logic(
                        "reclassification_line_skipped", line=line, reason="settled"
                    )
                    continue
                common = {
                    "name": self.env._(
                        "Reclassification of %(payment)s", payment=payment.display_name
                    ),
                    "partner_id": line.partner_id.id,
                    "currency_id": line.currency_id.id,
                }
                line_vals += [
                    {
                        **common,
                        "account_id": old.id,
                        "balance": -balance,
                        "amount_currency": -amount_currency,
                    },
                    {
                        **common,
                        "account_id": new.id,
                        "balance": balance,
                        "amount_currency": amount_currency,
                    },
                ]
                to_match.append((line, old))
        if not line_vals:
            raise UserError(
                self.env._(
                    "Nothing is left open on the lines to reclassify: they are fully "
                    "matched."
                )
            )
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.journal_id.id,
                "date": self.date,
                "ref": self.env._(
                    "Reclassification of %(payment)s", payment=payment.display_name
                ),
                "partner_id": payment.partner_id.id,
                "reclassified_payment_id": payment.id,
                "line_ids": [Command.create(vals) for vals in line_vals],
            }
        )
        entry.action_post()
        for line, old in to_match:
            if not old.reconcile or line.reconciled:
                continue
            reversal = entry.line_ids.filtered(
                lambda reclass, old=old, line=line: (
                    reclass.account_id == old
                    and reclass.partner_id == line.partner_id
                    and not reclass.reconciled
                )
            )[:1]
            (line + reversal).reconcile()
        return entry
