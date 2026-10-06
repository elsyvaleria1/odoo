from odoo import models


class AccountBankStatementLine(models.Model):
    _name = "account.bank.statement.line"
    _inherit = "account.bank.statement.line"

    def set_batch_payment_bank_statement_line(self, batch_payment_id) -> None:
        self.check_singleton()
        batch_payment = self.env["account.batch.payment"].browse(batch_payment_id)

        amls_to_create, has_exchange_diff = batch_payment._get_amls_for_reconciliation(
            self
        )

        self.with_context(
            no_exchange_difference_no_recursive=not has_exchange_diff
        )._add_move_line_to_statement_line_move(amls_to_create)
        if payments_to_validate := batch_payment.payment_ids.filtered(
            lambda p: (
                not p.move_id
                and p.state in self.env["account.payment"]._valid_payment_states()
            )
        ):
            payments_to_validate.action_validate()

    def remove_reconciled_line(self, move_line_ids) -> None:
        self.check_singleton()
        payments = self.env["account.move.line"].browse(move_line_ids).payment_lines_ids
        super().remove_reconciled_line(move_line_ids)
        payments.filtered(
            lambda payment: not payment.move_id and payment.state == "paid"
        ).state = "in_process"
