from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    generating_loan_line_id = fields.Many2one(
        comodel_name="account.loan.line",
        index=True,
        copy=False,
        readonly=True,
        # NOT "cascade": a database-level cascade deletes journal entries in SQL,
        # below unlink(), the audit trail and the hash chain. account.loan guards
        # its own deletion and disposes of these entries through
        # _unlink_or_reverse(), which keeps audit-protected ones as cancelled.
        ondelete="set null",
        help="Line of the loan that generated this entry",
    )
    loan_id = fields.Many2one(related="generating_loan_line_id.loan_id")
    is_loan_payment_move = fields.Boolean()

    def _post_entries(self):
        posted = super()._post_entries()
        loans = posted.loan_id
        if loans:
            loans.filtered(
                lambda loan: (
                    loan.state in ("draft", "running") and loan._is_fully_repaid()
                )
            )._set_state("closed")
        return posted

    def open_loan(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Original Loan"),
            "views": [(False, "form")],
            "res_model": "account.loan",
            "res_id": self.loan_id.id,
        }
