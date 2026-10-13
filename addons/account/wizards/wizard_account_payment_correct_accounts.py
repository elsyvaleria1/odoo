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
    is_reclassified = fields.Boolean(compute="_compute_is_locked")
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
            if not wizard.payment_id:
                wizard.counterpart_account_id = False
                wizard.liquidity_account_id = False
                continue
            chain, _broken = wizard._get_reclassification_chain()
            wizard.counterpart_account_id = chain["counterpart_account_id"][0]
            wizard.liquidity_account_id = chain["liquidity_account_id"][0]

    @api.depends("payment_id")
    def _compute_is_locked(self) -> None:
        for wizard in self:
            wizard.is_locked = wizard.payment_id._is_entry_locked()
            wizard.is_reclassified = bool(
                wizard.payment_id and wizard._get_standing_reclassifications()
            )

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

    def _get_changes(self, chain) -> dict:
        self.check_singleton()
        changes = {}
        for fname, (current, _lines) in chain.items():
            if self[fname] != current:
                changes[fname] = (current, self[fname])
        return changes

    def _get_standing_reclassifications(self):
        reclassifications = self.env["account.move"].search(
            [
                ("reclassified_payment_id", "=", self.payment_id.id),
                ("state", "=", "posted"),
            ],
            order="date, id",
        )
        standing = reclassifications.filtered(
            lambda entry: (
                not entry.reversal_move_ids.filtered(
                    lambda reversal: reversal.state == "posted"
                )
            )
        )
        _debug.logic(
            "standing_reclassifications",
            payment=self.payment_id,
            reclassifications=reclassifications,
            standing=standing,
        )
        return standing

    def _get_reclassification_chain(self):
        # A field's lines are told apart by account type: a counterpart is always
        # receivable/payable and a liquidity account never is (action_correct).
        self.check_singleton()
        payment = self.payment_id
        liquidity, counterpart, _other = payment._seek_for_lines()
        chain = {
            "counterpart_account_id": (payment.counterpart_account_id, counterpart),
            "liquidity_account_id": (payment.liquidity_account_id, liquidity),
        }
        broken = {}
        counterpart_types = payment._get_valid_payment_account_types()
        for entry in self._get_standing_reclassifications():
            for fname, (current, _lines) in chain.items():
                field_lines = entry.line_ids.filtered(
                    lambda line, fname=fname: (
                        (line.account_type in counterpart_types)
                        == (fname == "counterpart_account_id")
                    )
                )
                if not field_lines:
                    continue
                if fname in broken:
                    broken[fname] |= entry
                    continue
                moved = field_lines.filtered(
                    lambda line, current=current: line.account_id != current
                )
                if moved == field_lines or len(moved.account_id) != 1:
                    broken[fname] = entry
                    continue
                chain[fname] = (moved.account_id, moved)
        _debug.logic(
            "reclassification_chain",
            payment=payment,
            counterpart=chain["counterpart_account_id"][0],
            liquidity=chain["liquidity_account_id"][0],
            broken=sorted(broken),
        )
        return chain, broken

    def action_correct(self):
        self.check_singleton()
        payment = self.payment_id
        if payment.state not in ("in_process", "paid") or not payment.move_id:
            raise UserError(
                self.env._(
                    "Only a confirmed payment with a journal entry has accounts to correct."
                )
            )
        chain, broken = self._get_reclassification_chain()
        if not (changes := self._get_changes(chain)):
            raise UserError(
                self.env._("Choose an account different from the current one.")
            )
        if entries := self.env["account.move"].union(
            *(broken[fname] for fname in changes if fname in broken)
        ):
            raise UserError(
                self.env._(
                    "%(entries)s no longer continue the reclassifications of this "
                    "account of the payment, an earlier one having been reversed; "
                    "reverse them before reclassifying the account again.",
                    entries=", ".join(entries.mapped("display_name")),
                )
            )
        counterpart_types = payment._get_valid_payment_account_types()
        if (
            "counterpart_account_id" in changes
            and self.counterpart_account_id.account_type not in counterpart_types
        ):
            raise UserError(
                self.env._(
                    "A payment's counterpart must be a receivable or payable account."
                )
            )
        if (
            "liquidity_account_id" in changes
            and self.liquidity_account_id.account_type in counterpart_types
        ):
            raise UserError(
                self.env._(
                    "A payment's liquidity account cannot be a receivable or payable "
                    "account."
                )
            )
        reclassify = self.is_locked or self.is_reclassified
        _debug.lifecycle(
            "payment_accounts_corrected",
            payment=payment,
            locked=self.is_locked,
            reclassified=self.is_reclassified,
            fields=sorted(changes),
        )
        if reclassify:
            entry = self._reclassify(changes, chain)
        else:
            payment._correct_accounts(
                {fname: new.id for fname, (_old, new) in changes.items()}
            )
            entry = payment.move_id
        payment.message_post(body=self._get_note(changes, entry, reclassify))
        return {"type": "ir.actions.act_window_close"}

    def _get_note(self, changes, entry, reclassified):
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
        elif reclassified:
            intro = self.env._(
                "Accounts reclassified by %(entry)s, the payment's accounts having "
                "already been reclassified:",
                entry=entry._get_html_link(),
            )
        else:
            intro = self.env._("Accounts corrected on the payment and its entry:")
        return Markup("%s<ul>%s</ul>") % (intro, items)

    def _reclassify(self, changes, chain):
        self.check_singleton()
        payment = self.payment_id
        if not self.journal_id:
            raise UserError(
                self.env._("Choose the journal of the reclassification entry.")
            )
        line_vals = []
        to_match = []
        for fname, (old, new) in changes.items():
            for line in chain[fname][1]:
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
