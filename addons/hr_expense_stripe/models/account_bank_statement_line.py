from typing import TYPE_CHECKING, Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import date_utils

from odoo.addons.hr_expense_stripe.utils import format_amount_from_stripe

if TYPE_CHECKING:
    from odoo.addons.account.models.account_journal import AccountJournal
    from odoo.addons.base.models.res_currency import ResCurrency
    from odoo.addons.hr_expense_stripe.models.hr_expense_stripe_card import (
        HrExpenseStripeCard,
    )


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    stripe_id = fields.Char(
        string="Stripe transaction ID",
        readonly=True,
    )

    _check_unique_stripe_id = models.Constraint(
        definition="UNIQUE(stripe_id)",
        message="Only one bank statement can be created from a single stripe transaction",
    )

    @api.model
    def _create_from_stripe_topup(self, tu_object) -> None:
        company = self.env.company
        journal = company.stripe_journal_id
        journal_currency = journal.currency_id or journal.company_id.stripe_currency_id
        topup_currency = self._acquire_active_currency(
            tu_object["currency"], journal_currency
        )
        amount = format_amount_from_stripe(tu_object["amount"], journal_currency)
        date = date_utils.datetime.fromtimestamp(tu_object["created"])

        transfer_account = company.account_config_id.transfer_account_id
        create_vals = {
            "stripe_id": tu_object["id"],
            "date": date,
            "journal_id": journal.id,
            "payment_ref": self.env._("Stripe Top-up"),
            "amount": amount,
        }
        if transfer_account.active:
            create_vals["counterpart_account_id"] = transfer_account.id  # Hack 'field'

        if topup_currency != journal_currency:
            create_vals.update(
                {
                    "foreign_currency_id": topup_currency.id,
                    "amount_currency": amount,
                    "amount": topup_currency._convert(
                        amount, journal_currency, journal.company_id, date
                    ),
                }
            )
        self.with_context(no_retrieve_partner=True).create([create_vals])

    @api.model
    def _create_from_stripe_transaction(self, tr_object) -> None:
        card = self.env["hr.expense.stripe.card"].search(
            [
                ("stripe_id", "=", tr_object["card"]),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )
        if not card:
            raise UserError(
                self.env._("A card that doesn't exist on the database was used")
            )
        amount, amount_currency, journal, journal_currency, merchant_currency = (
            self._acquire_transaction_data(card, tr_object)
        )
        payment_ref = self.env._(
            "Card ending in %(last_4)s payment to %(merchant_name)s",
            last_4=card.last_4,
            merchant_name=tr_object["merchant_data"]["name"],
        )
        create_vals = {
            "stripe_id": tr_object["id"],
            "date": date_utils.datetime.fromtimestamp(tr_object["created"]),
            "journal_id": journal.id,
            "payment_ref": payment_ref,
            "amount": amount,
        }
        if merchant_currency != journal_currency:
            create_vals.update(
                {
                    "foreign_currency_id": merchant_currency.id,
                    "amount_currency": amount_currency,
                }
            )

        stmt_line = self.create([create_vals])

        expenses = self.env["hr.expense"].search(
            [
                ("stripe_transaction_id", "=", tr_object["id"]),
                ("company_id", "=", stmt_line.company_id.id),
            ]
        )
        if expenses:
            for expense in expenses:
                stmt_line.move_id.message_post(
                    body=self.env._(
                        "Transaction created from %(expense)s",
                        expense=expense._get_html_link(title=expense.name),
                    ),
                    message_type="comment",
                )
            if all(
                expense.account_move_id.origin_payment_id.state == "in_process"
                for expense in expenses
            ):
                # Split expenses cases, we only want to reconcile if everything posted
                expenses._reconcile_stripe_payments(existing_statement_lines=stmt_line)

    def _update_from_stripe_transaction(self, tr_object) -> None:
        self.check_singleton()
        card = self.env["hr.expense.stripe.card"].search(
            [
                ("stripe_id", "=", tr_object["card"]),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        amount, amount_currency, _journal, journal_currency, merchant_currency = (
            self._acquire_transaction_data(card, tr_object)
        )

        update_vals = {}
        if self.currency_id.compare_amounts(self.amount, amount) != 0:
            update_vals["amount"] = amount

        if merchant_currency != journal_currency:
            if self.foreign_currency_id != merchant_currency:
                update_vals["foreign_currency_id"] = merchant_currency.id
            if (
                merchant_currency.compare_amounts(self.amount_currency, amount_currency)
                != 0
            ):
                update_vals["amount_currency"] = amount_currency

        if update_vals:
            self.write(update_vals)

    ##################
    # Helper methods #
    ##################
    @api.model
    def _acquire_transaction_data(
        self, card: HrExpenseStripeCard, tr_object: dict[str, Any]
    ) -> tuple[float, float, AccountJournal, ResCurrency, ResCurrency]:
        journal = card.journal_id
        journal_currency = journal.currency_id or journal.stripe_currency_id
        amount = amount_currency = format_amount_from_stripe(
            tr_object["amount"], card.currency_id
        )
        merchant_currency = self._acquire_active_currency(
            tr_object["merchant_currency"], journal_currency
        )
        if merchant_currency != journal_currency:
            amount_currency = format_amount_from_stripe(
                tr_object["merchant_amount"], merchant_currency
            )
        return amount, amount_currency, journal, journal_currency, merchant_currency

    def _acquire_active_currency(
        self, currency_code: str, fallback: ResCurrency
    ) -> ResCurrency:
        currency = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([("name", "ilike", currency_code)], limit=1)
            or fallback
        )
        if currency and not currency.active:
            currency.active = True
        return currency
