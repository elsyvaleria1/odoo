import logging
import re

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import frozendict

_logger = logging.getLogger(__name__)
_DIGITS = re.compile(r"\d+")


def _luhn_digit(number: str) -> str:
    total = 0
    for index, digit in enumerate(reversed(number)):
        value = int(digit) * (2 if index % 2 == 0 else 1)
        total += value - 9 if value > 9 else value
    return str((10 - total % 10) % 10)


def bank_reference_for(remittance_id: int) -> str:
    number = f"{remittance_id:07d}"
    return number + _luhn_digit(number)


class AccountCollectionRemittance(models.Model):
    _name = "account.collection.remittance"
    _description = "Collection Remittance"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _order = "date desc, id desc"
    _check_company_auto = True
    _access_anchors = frozendict({"owner": "collector_id"})
    _access_verbs = {
        "submit": models.Verb(transition=("state", "draft", "submitted")),
        "reopen": models.Verb(
            transition=("state", ("submitted", "done"), "draft"), at_create=False
        ),
        "validate": models.Verb(
            methods=("action_validate",), transition=("state", "submitted", "done")
        ),
        "cancel": models.Verb(
            transition=("state", ("draft", "submitted"), "cancel"), at_create=False
        ),
    }

    name = fields.Char(
        string="Number",
        default="/",
        copy=False,
        readonly=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("submitted", "To Validate"),
            ("done", "Handed In"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        copy=False,
        readonly=True,
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    collector_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.user,
        index=True,
        required=True,
        tracking=True,
        help="Who hands the money in.",
    )
    date = fields.Date(
        string="Hand-in Date",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
        help="The day the money reached the till or the bank.",
    )
    payment_ids = fields.Many2many(
        comodel_name="account.payment",
        relation="account_collection_remittance_payment_rel",
        column1="remittance_id",
        column2="payment_id",
        string="Collections",
        copy=False,
        domain="[('collector_id', '=', collector_id), ('company_id', '=', company_id), ('is_in_custody', '=', True)]",
        check_company=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
    )
    amount_collected = fields.Monetary(
        string="Collected",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    amount_handed_in = fields.Monetary(
        string="Handed In",
        currency_field="currency_id",
        tracking=True,
        help="What actually reached the till or the bank.",
    )
    amount_difference = fields.Monetary(
        string="Difference",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
        help="Handed in minus collected: below zero is a shortage charged to the "
        "collector, above zero an overage.",
    )
    count_payment = fields.Integer(
        compute="_compute_amounts",
        store=True,
    )
    destination_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Handed In To",
        domain="[('type', 'in', ('bank', 'cash')), ('is_collection_custody', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
        tracking=True,
        help="The till that received the cash, or the bank account it was deposited "
        "into.",
    )
    destination_type = fields.Selection(
        related="destination_journal_id.type",
    )
    bank_reference = fields.Char(
        string="Deposit Reference Number",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="The number the collector gives the bank as the deposit's reference: "
        "the bank transaction that carries it, for the amount handed in, "
        "validates this remittance by itself.",
    )
    deposit_reference = fields.Char(
        tracking=True,
        help="The reference printed on the deposit slip.",
    )
    statement_line_id = fields.Many2one(
        comodel_name="account.bank.statement.line",
        string="Bank Transaction",
        copy=False,
        domain="[('journal_id', '=', destination_journal_id), ('is_reconciled', '=', False)]",
        check_company=True,
        tracking=True,
        help="The deposit as the bank reports it. Once set, validating settles it.",
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Hand-in Entry",
        copy=False,
        readonly=True,
        check_company=True,
    )
    validated_by_id = fields.Many2one(
        comodel_name="res.users",
        copy=False,
        readonly=True,
    )
    note = fields.Text()

    @api.depends("payment_ids.amount_company_currency_signed", "amount_handed_in")
    def _compute_amounts(self) -> None:
        for remittance in self:
            collected = sum(
                remittance.payment_ids.mapped("amount_company_currency_signed")
            )
            remittance.amount_collected = collected
            remittance.count_payment = len(remittance.payment_ids)
            remittance.amount_difference = (
                remittance.amount_handed_in - collected
                if remittance.amount_handed_in
                else 0.0
            )

    @api.model_create_multi
    def create(self, vals_list):
        remittances = super().create(vals_list)
        for remittance in remittances:
            remittance.bank_reference = bank_reference_for(remittance.id)
        return remittances

    @api.constrains("payment_ids", "collector_id", "state")
    def _check_payments(self) -> None:
        live = self.filtered(lambda remittance: remittance.state != "cancel")
        for remittance in live:
            strangers = remittance.payment_ids.filtered(
                lambda payment, remittance=remittance: (
                    payment.collector_id != remittance.collector_id
                    or not payment.is_collection_custody
                )
            )
            if strangers:
                raise ValidationError(
                    self.env._(
                        "Remittance %(remittance)s hands in only %(collector)s's "
                        "collections held in custody, not %(payments)s.",
                        remittance=remittance.display_name,
                        collector=remittance.collector_id.name,
                        payments=", ".join(strangers.mapped("name")),
                    )
                )
        for payment in live.payment_ids:
            holders = payment.collection_remittance_ids.filtered(
                lambda remittance: remittance.state != "cancel"
            )
            if len(holders) > 1:
                raise ValidationError(
                    self.env._(
                        "Collection %(payment)s is in remittances %(remittances)s; "
                        "a collection is handed in once.",
                        payment=payment.name,
                        remittances=", ".join(holders.mapped("display_name")),
                    )
                )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_handed_in(self) -> None:
        if self.filtered(
            lambda remittance: remittance.state not in ("draft", "cancel")
        ):
            raise UserError(
                self.env._("Only a draft or cancelled remittance can be deleted.")
            )

    def action_load_custody(self) -> None:
        drafts = self.filtered(lambda remittance: remittance.state == "draft")
        if not drafts:
            return
        held = self.env["account.payment"].search(
            [
                ("collector_id", "in", drafts.collector_id.ids),
                ("company_id", "in", drafts.company_id.ids),
                ("is_in_custody", "=", True),
                ("collection_remittance_id", "=", False),
            ]
        )
        for remittance in drafts:
            remittance.payment_ids = [
                Command.link(payment.id)
                for payment in held
                if payment.collector_id == remittance.collector_id
                and payment.company_id == remittance.company_id
                and not remittance._is_post_dated(payment)
            ]

    def _is_post_dated(self, payment) -> bool:
        self.check_singleton()
        return bool(
            payment.collection_check_date and payment.collection_check_date > self.date
        )

    def action_submit(self) -> None:
        for remittance in self:
            if remittance.state != "draft":
                raise UserError(self.env._("Only a draft remittance can be submitted."))
            if problem := remittance._get_submit_problem():
                raise UserError(problem)
            vals = {"state": "submitted"}
            if not remittance.amount_handed_in:
                vals["amount_handed_in"] = remittance.amount_collected
            if remittance.name == "/":
                vals["name"] = (
                    self.env["ir.sequence"]
                    .with_company(remittance.company_id)
                    .next_by_code("account.collection.remittance")
                )
            remittance.write(vals)

    def _get_submit_problem(self) -> str | None:
        self.check_singleton()
        if not self.payment_ids:
            return self.env._("Add the collections being handed in.")
        if not self.destination_journal_id:
            return self.env._("Say where the money was handed in.")
        released = self.payment_ids.filtered(lambda payment: not payment.is_in_custody)
        if released:
            return self.env._(
                "%(payments)s are no longer in custody.",
                payments=", ".join(released.mapped("name")),
            )
        post_dated = self.payment_ids.filtered(self._is_post_dated)
        if post_dated:
            return self.env._(
                "The checks of %(payments)s are dated after %(date)s: hand them in on "
                "their date.",
                payments=", ".join(post_dated.mapped("name")),
                date=self.date,
            )
        return None

    def action_reopen(self) -> None:
        for remittance in self:
            if remittance.state != "submitted":
                raise UserError(
                    self.env._("Only a remittance awaiting validation can be reopened.")
                )
            remittance.state = "draft"

    def action_validate(self) -> None:
        self.check_access("validate")
        for remittance in self:
            if remittance.state != "submitted":
                raise UserError(
                    self.env._("Only a submitted remittance can be validated.")
                )
            if problem := remittance._get_submit_problem():
                raise UserError(problem)
            move = (
                self.env["account.move"]
                .with_company(remittance.company_id)
                .create(remittance._prepare_hand_in_move_vals())
            )
            move.action_post()
            remittance._reconcile_hand_in_move(move)
            remittance.write(
                {
                    "state": "done",
                    "move_id": move.id,
                    "validated_by_id": self.env.uid,
                }
            )

    def _prepare_hand_in_move_vals(self) -> dict:
        self.check_singleton()
        company = self.company_id
        journal = self.destination_journal_id
        config = company.account_config_id
        if journal.type == "cash":
            received_account = journal.default_account_id
        else:
            received_account = config.transfer_account_id
        if not received_account:
            raise UserError(
                self.env._(
                    "Set the inter-bank transfer account of %(company)s: a deposit "
                    "waits there for the bank to report it.",
                    company=company.name,
                )
            )
        label = self.env._("Collections handed in: %(name)s", name=self.name)
        collector_partner = self.collector_id.partner_id
        lines = [
            Command.create(
                {
                    "name": label,
                    "account_id": received_account.id,
                    "partner_id": collector_partner.id,
                    "balance": self.amount_handed_in,
                }
            )
        ]
        lines.extend(
            Command.create(
                {
                    "name": payment.name,
                    "account_id": payment.outstanding_account_id.id,
                    "partner_id": payment.collector_id.partner_id.id,
                    "balance": -payment.amount_company_currency_signed,
                }
            )
            for payment in self.payment_ids
        )
        difference = self.amount_difference
        if not self.currency_id.is_zero(difference):
            account = (
                config.collection_overage_account_id
                if difference > 0
                else config.collection_shortage_account_id
            )
            if not account:
                raise UserError(
                    self.env._(
                        "Remittance %(name)s hands in %(handed)s against %(collected)s "
                        "collected: set the collector shortage and overage accounts "
                        "of %(company)s to book the difference.",
                        name=self.name,
                        handed=self.amount_handed_in,
                        collected=self.amount_collected,
                        company=company.name,
                    )
                )
            lines.append(
                Command.create(
                    {
                        "name": self.env._(
                            "Hand-in difference: %(name)s", name=self.name
                        ),
                        "account_id": account.id,
                        "partner_id": collector_partner.id,
                        "balance": -difference,
                    }
                )
            )
        return {
            "move_type": "entry",
            "journal_id": journal.id,
            "company_id": company.id,
            "date": self.date,
            "ref": " ".join(filter(None, [self.name, self.deposit_reference])),
            "line_ids": lines,
        }

    def _reconcile_hand_in_move(self, move) -> None:
        self.check_singleton()
        for payment in self.payment_ids:
            custody_lines = payment.move_id.line_ids.filtered(
                lambda line, payment=payment: (
                    line.account_id == payment.outstanding_account_id
                    and not line.reconciled
                )
            )
            hand_in_line = move.line_ids.filtered(
                lambda line, payment=payment: (
                    line.name == payment.name
                    and line.account_id == payment.outstanding_account_id
                    and not line.reconciled
                )
            )[:1]
            (custody_lines + hand_in_line).reconcile()
        if self.statement_line_id:
            received_line = move.line_ids[:1]
            self.statement_line_id.set_line_bank_statement_line(received_line.ids)

    def _cron_match_bank_transactions(self) -> None:
        waiting = self.search(
            [
                ("state", "=", "submitted"),
                ("destination_journal_id.type", "=", "bank"),
                ("statement_line_id", "=", False),
                ("bank_reference", "!=", False),
            ]
        )
        if not waiting:
            return
        transactions = self.env["account.bank.statement.line"].search(
            [
                ("journal_id", "in", waiting.destination_journal_id.ids),
                ("is_reconciled", "=", False),
                ("amount", "in", list(set(waiting.mapped("amount_handed_in")))),
            ]
        )
        references = {
            transaction: {
                int(group) for group in _DIGITS.findall(transaction.payment_ref or "")
            }
            for transaction in transactions
        }
        matches = {}
        for remittance in waiting:
            number = int(remittance.bank_reference)
            found = [
                transaction
                for transaction, numbers in references.items()
                if number in numbers
                and transaction.journal_id == remittance.destination_journal_id
                and transaction.currency_id.compare_amounts(
                    transaction.amount, remittance.amount_handed_in
                )
                == 0
            ]
            if len(found) == 1:
                matches.setdefault(found[0], []).append(remittance)
        for transaction, remittances in matches.items():
            if len(remittances) != 1:
                continue
            remittance = remittances[0]
            try:
                with self.env.cr.savepoint():
                    remittance.statement_line_id = transaction
                    remittance.action_validate()
            except UserError as error:
                _logger.info(
                    "Remittance %s matched %s but did not validate: %s",
                    remittance.name,
                    transaction.payment_ref,
                    error,
                )
                remittance.message_post(
                    body=self.env._(
                        "The bank reported this deposit (%(transaction)s), but the "
                        "remittance could not be validated: %(reason)s",
                        transaction=transaction.payment_ref,
                        reason=str(error),
                    )
                )
            else:
                remittance.message_post(
                    body=self.env._(
                        "Validated by itself: the bank reported this deposit as "
                        "%(transaction)s.",
                        transaction=transaction.payment_ref,
                    )
                )

    def action_cancel(self) -> None:
        for remittance in self:
            if remittance.state not in ("draft", "submitted"):
                raise UserError(
                    self.env._(
                        "Only an open remittance can be cancelled; revert a handed-in one."
                    )
                )
            remittance.state = "cancel"

    def action_revert(self) -> None:
        self.check_access("reopen")
        for remittance in self:
            if remittance.state != "done":
                raise UserError(
                    self.env._("Only a handed-in remittance can be reverted.")
                )
            if bounced := remittance.payment_ids.filtered("collection_bounce_move_id"):
                raise UserError(
                    self.env._(
                        "The checks of %(payments)s bounced after this remittance; "
                        "it stands as handed in.",
                        payments=", ".join(bounced.mapped("name")),
                    )
                )
            move = remittance.move_id
            move.line_ids.remove_move_reconcile()
            move._reverse_moves(
                default_values_list=[
                    {
                        "date": fields.Date.context_today(remittance),
                        "ref": self.env._("Reversal of %(name)s", name=remittance.name),
                    }
                ],
                cancel=True,
            )
            remittance.write(
                {"state": "draft", "move_id": False, "validated_by_id": False}
            )
