from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

_SETTLED_ACCOUNT_TYPES = ("asset_receivable", "liability_payable")


class WizardAccountMoveApplyAdvance(models.TransientModel):
    _name = "wizard.account.move.apply.advance"
    _description = "Settle invoices from an advance or another account"
    _check_company_auto = True

    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
    )
    company_currency_id = fields.Many2one(related="company_id.currency_id")
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        required=True,
    )
    line_ids = fields.Many2many(
        comodel_name="account.move.line",
        relation="wizard_apply_advance_settled_line_rel",
        string="Settled Items",
        required=True,
    )
    source = fields.Selection(
        selection=[
            ("advance", "An open advance"),
            ("account", "Another account"),
        ],
        default="advance",
        required=True,
        help="An open advance: the partner's advance or prepayment items pay the "
        "invoices. Another account: the amount moves to an account, e.g. a third "
        "party who paid in the company's name.",
    )
    available_advance_line_ids = fields.Many2many(
        comodel_name="account.move.line",
        compute="_compute_available_advance_line_ids",
    )
    advance_line_ids = fields.Many2many(
        comodel_name="account.move.line",
        relation="wizard_apply_advance_advance_line_rel",
        string="Advances",
        domain="[('id', 'in', available_advance_line_ids)]",
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'off_balance'))]",
        check_company=True,
    )
    amount = fields.Monetary(
        currency_field="company_currency_id",
        compute="_compute_amount",
        precompute=True,
        store=True,
        readonly=False,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        compute="_compute_journal_id",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
        check_company=True,
    )
    date = fields.Date(
        default=fields.Date.context_today,
        required=True,
    )
    ref = fields.Char(string="Reference")

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        if self.env.context.get("active_model") != "account.move":
            return defaults
        moves = self.env["account.move"].browse(self.env.context.get("active_ids", []))
        lines = moves.line_ids.filtered(
            lambda line: (
                line.account_id.account_type in _SETTLED_ACCOUNT_TYPES
                and not line.reconciled
                and line.parent_state == "posted"
            )
        )
        if not lines:
            raise UserError(self.env._("These documents have nothing left to settle."))
        partners = lines.partner_id.commercial_partner_id
        if len(partners) != 1 or len(lines.company_id) != 1:
            raise UserError(
                self.env._("Settle the documents of one partner and company at a time.")
            )
        defaults.update(
            company_id=lines.company_id.id,
            partner_id=partners.id,
            line_ids=[Command.set(lines.ids)],
        )
        return defaults

    @api.depends("line_ids", "partner_id")
    def _compute_available_advance_line_ids(self) -> None:
        candidates = self.env["account.move.line"].search(
            [
                ("company_id", "in", self.company_id.ids),
                ("partner_id", "child_of", self.partner_id.ids),
                ("parent_state", "=", "posted"),
                ("reconciled", "=", False),
                ("account_id.reconcile", "=", True),
                ("account_id.account_type", "not in", _SETTLED_ACCOUNT_TYPES),
                ("amount_residual", "!=", 0.0),
            ]
        )
        for wizard in self:
            sign = wizard._get_settled_sign()
            wizard.available_advance_line_ids = candidates.filtered_domain(
                [
                    ("company_id", "=", wizard.company_id.id),
                    ("partner_id", "child_of", wizard.partner_id.id),
                    ("amount_residual", "<" if sign > 0 else ">", 0.0),
                ]
            )

    @api.depends("line_ids", "advance_line_ids", "source")
    def _compute_amount(self) -> None:
        for wizard in self:
            open_amount = abs(sum(wizard.line_ids.mapped("amount_residual")))
            if wizard.source == "advance":
                open_amount = min(
                    open_amount,
                    abs(sum(wizard.advance_line_ids.mapped("amount_residual"))),
                )
            wizard.amount = open_amount

    @api.depends("company_id")
    def _compute_journal_id(self) -> None:
        Journal = self.env["account.journal"]
        general_journals = Journal.search(
            [
                *Journal._get_domain_company_compatible(self.company_id),
                ("type", "=", "general"),
            ]
        )
        for wizard in self:
            wizard.journal_id = (
                wizard.company_id.account_config_id.automatic_entry_default_journal_id
                or general_journals.filtered_domain(
                    Journal._get_domain_company_compatible(wizard.company_id)
                )[:1]
            )

    def _get_settled_sign(self) -> int:
        return 1 if sum(self.line_ids.mapped("amount_residual")) > 0 else -1

    def _allocate(self, lines, amount) -> dict:
        allocated = defaultdict(float)
        currency = self.company_currency_id
        for line in lines.sorted(lambda line: (line.date, line.id)):
            if currency.is_zero(amount):
                break
            part = min(abs(line.amount_residual), amount)
            allocated[line] += part
            amount = currency.round(amount - part)
        return allocated

    def _check_inputs(self) -> None:
        self.check_singleton()
        currency = self.company_currency_id
        if currency.compare_amounts(self.amount, 0.0) <= 0:
            raise UserError(self.env._("Choose a positive amount to settle."))
        if (
            currency.compare_amounts(
                self.amount, abs(sum(self.line_ids.mapped("amount_residual")))
            )
            > 0
        ):
            raise UserError(
                self.env._("The amount exceeds what the documents still owe.")
            )
        if self.source == "account" and not self.account_id:
            raise UserError(self.env._("Choose the account the amount moves to."))
        if self.source == "advance":
            if not self.advance_line_ids:
                raise UserError(self.env._("Choose the advances to apply."))
            if (
                currency.compare_amounts(
                    self.amount,
                    abs(sum(self.advance_line_ids.mapped("amount_residual"))),
                )
                > 0
            ):
                raise UserError(
                    self.env._("The amount exceeds what the advances still hold.")
                )

    def _prepare_entry_line_vals(self, sign) -> list:
        label = self.ref or self.env._("Advance application")
        currency = self.company_currency_id
        vals = [
            {
                "name": label,
                "account_id": line.account_id.id,
                "partner_id": line.partner_id.id,
                "currency_id": currency.id,
                "balance": -sign * part,
                "amount_currency": -sign * part,
            }
            for line, part in self._allocate(self.line_ids, self.amount).items()
        ]
        if self.source == "account":
            sources = {(self.account_id, self.partner_id): self.amount}
        else:
            sources = defaultdict(float)
            for line, part in self._allocate(
                self.advance_line_ids, self.amount
            ).items():
                sources[line.account_id, line.partner_id] += part
        vals += [
            {
                "name": label,
                "account_id": account.id,
                "partner_id": partner.id,
                "currency_id": currency.id,
                "balance": sign * part,
                "amount_currency": sign * part,
            }
            for (account, partner), part in sources.items()
        ]
        return vals

    def action_apply(self):
        self.check_singleton()
        self._check_inputs()
        sign = self._get_settled_sign()
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.journal_id.id,
                "date": self.date,
                "ref": self.ref,
                "partner_id": self.partner_id.id,
                "line_ids": [
                    Command.create(vals) for vals in self._prepare_entry_line_vals(sign)
                ],
            }
        )
        entry.action_post()
        _debug.lifecycle(
            "advance_applied",
            entry=entry,
            source=self.source,
            settled=self.line_ids,
            advances=self.advance_line_ids,
        )
        to_match = self.line_ids | self.advance_line_ids
        for account in to_match.account_id.filtered("reconcile"):
            lines = (to_match | entry.line_ids).filtered(
                lambda line, account=account: (
                    line.account_id == account and not line.reconciled
                )
            )
            if lines:
                lines.reconcile()
        return entry._get_records_action(name=self.env._("Advance Application"))
