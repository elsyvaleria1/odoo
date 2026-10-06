from __future__ import annotations

from odoo import Command, api, fields, models
from odoo.exceptions import UserError


class AccountBankStatement(models.Model):
    _name = "account.bank.statement"
    _inherit = ["account.bank.statement", "mixin.extract"]

    _extract_document_type = "bank_statement"

    _extract_target = {
        "opening_balance": "balance_start",
        "closing_balance": "balance_end_real",
        "period_end": "date",
    }

    extract_can_be_read = fields.Boolean(compute="_compute_extract_can_be_read")

    @api.depends("line_ids.journal_id")
    def _compute_journal_id(self) -> None:
        # A statement takes its journal from its lines, so one created to be
        # read -- an attachment and nothing else -- would lose the journal it
        # was created with before the reading could put lines on it.
        statements = self.filtered("line_ids")
        super(AccountBankStatement, statements)._compute_journal_id()

    @api.depends("line_ids", "extract_state")
    def _compute_extract_can_be_read(self) -> None:
        for statement in self:
            statement.extract_can_be_read = not statement.line_ids and (
                statement.extract_state in ("none", "failed", "partial")
            )

    def _update_from_extraction(self, result) -> None:
        self.check_singleton()
        super()._update_from_extraction(result)

        if self.line_ids:
            return
        lines = self._prepare_extract_line_vals_list(result.flat().get("transactions"))
        if not lines:
            return
        self.with_context(auto_statement_processing=True).write(
            {"line_ids": [Command.create(values) for values in lines]}
        )

    def _prepare_extract_line_vals_list(self, transactions) -> list[dict]:
        # The `bank_statement` schema declares what a transaction row is and
        # coerces it, so a row that reaches here has an amount and a description
        # and nothing here has to guess which key carries them.
        self.check_singleton()
        return [
            {
                "amount": transaction["amount"],
                "journal_id": self.journal_id.id,
                "payment_ref": transaction["description"],
                **({"date": transaction["date"]} if transaction.get("date") else {}),
            }
            for transaction in transactions or ()
        ]

    def action_extract_document(self) -> dict | None:
        self.check_singleton()
        if not self.extract_can_be_read:
            raise UserError(
                self.env._("A statement is read while it still has no transactions.")
            )
        result = self._extract_document()
        if result is None:
            return None
        if result.satisfied:
            message = self.env._("The statement was read in full.")
        else:
            message = self.env._(
                "The statement was read in part. Still missing: %(fields)s",
                fields=", ".join(result.missing) or self.env._("nothing required"),
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"message": message, "type": "info", "sticky": False},
        }
