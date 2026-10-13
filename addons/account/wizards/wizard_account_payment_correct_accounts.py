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
            chain, _broken, _held = wizard._get_reclassification_chain()
            wizard.counterpart_account_id = chain["counterpart_account_id"][0]
            wizard.liquidity_account_id = chain["liquidity_account_id"][0]

    @api.depends("payment_id")
    def _compute_is_locked(self) -> None:
        for wizard in self:
            wizard.is_locked = wizard.payment_id._is_entry_locked()
            wizard.is_reclassified = bool(
                wizard.payment_id and wizard._is_reclassified()
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

    def _get_reclassifications(self):
        return self.env["account.move"].search(
            [
                ("reclassified_payment_id", "=", self.payment_id.id),
                ("state", "=", "posted"),
            ],
            order="id",
        )

    @api.model
    def _is_standing(self, entry) -> bool:
        return not entry.reversal_move_ids.filtered(
            lambda reversal: reversal.state == "posted"
        )

    @api.model
    def _get_family_lines(self, reclassifications):
        return (
            reclassifications
            | reclassifications.reversal_move_ids.filtered(
                lambda reversal: reversal.state == "posted"
            )
        ).line_ids

    def _is_reclassified(self) -> bool:
        self.check_singleton()
        reclassifications = self._get_reclassifications()
        if any(self._is_standing(entry) for entry in reclassifications):
            return True
        family_lines = self._get_family_lines(reclassifications)
        payment_lines = self.payment_id.move_id.line_ids
        matched = (
            payment_lines.matched_debit_ids.debit_move_id
            | payment_lines.matched_credit_ids.credit_move_id
        )
        return bool(matched & family_lines)

    @api.model
    def _split_reclassification(self, entry, held) -> dict:
        lines_per_field = {
            fname: entry.line_ids.filtered(
                lambda line, accounts=accounts: line.account_id in accounts
            )
            for fname, accounts in held.items()
        }
        touched = [fname for fname, lines in lines_per_field.items() if lines]
        added = entry.line_ids - self.env["account.move.line"].union(
            *lines_per_field.values()
        )
        if len(touched) == 1:
            lines_per_field[touched[0]] |= added
            return lines_per_field
        if not touched:
            return dict.fromkeys(held, entry.line_ids)
        # Both accounts moved in one entry: each added line mirrors the line it
        # takes the amount from (_reclassify), and a counterpart and a liquidity
        # line of one payment never share a sign.
        sources = dict(lines_per_field)
        for line in added:
            owners = [
                fname
                for fname in touched
                if any(
                    source.partner_id == line.partner_id
                    and source.currency_id == line.currency_id
                    and source.company_currency_id.is_zero(
                        source.balance + line.balance
                    )
                    and source.currency_id.is_zero(
                        source.amount_currency + line.amount_currency
                    )
                    for source in sources[fname]
                )
            ]
            if len(owners) != 1:
                return dict.fromkeys(held, entry.line_ids)
            lines_per_field[owners[0]] |= line
        return lines_per_field

    def _get_reclassification_chain(self):
        # Walked in creation order, not by date: each reclassification was built
        # from the chain as it stood when it was created. A field's lines are told
        # apart by the accounts that field has held, whatever their type.
        self.check_singleton()
        payment = self.payment_id
        liquidity, counterpart, _other = payment._seek_for_lines()
        own_lines = {
            "counterpart_account_id": counterpart,
            "liquidity_account_id": liquidity,
        }
        current = {fname: payment[fname] for fname in own_lines}
        held = dict(current)
        broken = {}
        reclassifications = self._get_reclassifications()
        for entry in reclassifications:
            lines_per_field = self._split_reclassification(entry, held)
            for fname, field_lines in lines_per_field.items():
                held[fname] |= field_lines.account_id
            if not self._is_standing(entry):
                continue
            for fname, field_lines in lines_per_field.items():
                if not field_lines:
                    continue
                if fname in broken:
                    broken[fname] |= entry
                    continue
                moved = field_lines.filtered(
                    lambda line, fname=fname: line.account_id != current[fname]
                )
                if moved == field_lines or len(moved.account_id) != 1:
                    broken[fname] = entry
                    continue
                current[fname] = moved.account_id
        # A reversal posted without unmatching (auto-posted, future-dated) leaves
        # the open amount on its own line instead of the line it reverses.
        family_lines = self._get_family_lines(reclassifications)
        chain = {
            fname: (
                account,
                (own_lines[fname] | family_lines).filtered(
                    lambda line, account=account: line.account_id == account
                ),
            )
            for fname, account in current.items()
        }
        _debug.logic(
            "reclassification_chain",
            payment=payment,
            reclassifications=reclassifications,
            counterpart=current["counterpart_account_id"],
            liquidity=current["liquidity_account_id"],
            broken=sorted(broken),
        )
        return chain, broken, held

    def action_correct(self):
        self.check_singleton()
        payment = self.payment_id
        if payment.state not in ("in_process", "paid") or not payment.move_id:
            raise UserError(
                self.env._(
                    "Only a confirmed payment with a journal entry has accounts to correct."
                )
            )
        chain, broken, held = self._get_reclassification_chain()
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
        if any(
            new in held[other]
            for fname, (_old, new) in changes.items()
            for other in held
            if other != fname
        ):
            raise UserError(
                self.env._(
                    "A payment's counterpart and liquidity accounts must differ, "
                    "including the accounts either was reclassified to."
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

    @api.model
    def _get_open_amounts(self, account, lines) -> list:
        if account.reconcile:
            return [
                (line, line.amount_residual, line.amount_residual_currency)
                for line in lines
            ]
        # Lines on an account that is never matched add up: a chain that came back
        # to the account leaves an amount and its earlier reversals there.
        balance, amount_currency = (
            ("amount_residual", "amount_residual_currency")
            if account.is_reconcilable
            else ("balance", "amount_currency")
        )
        return [
            (
                group[:1],
                sum(group.mapped(balance)),
                sum(group.mapped(amount_currency)),
            )
            for group in lines.grouped(
                lambda line: (line.partner_id, line.currency_id)
            ).values()
        ]

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
            for line, balance, amount_currency in self._get_open_amounts(
                old, chain[fname][1]
            ):
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
                if old.reconcile:
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
            if line.reconciled:
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
