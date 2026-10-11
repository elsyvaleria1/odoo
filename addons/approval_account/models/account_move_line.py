from odoo import fields, models
from odoo.tools import frozendict


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"
    _access_anchors = frozendict(
        {
            "approval_pending_user": models.Anchor(
                "move_id.approval_pending_user_ids", kind="owner"
            ),
        }
    )

    approval_request_line_id = fields.Many2one(
        comodel_name="approval.request.line",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="Link to the approval request line that created this account move line",
    )

    def _reconcile_post_hook(self, data) -> None:
        super()._reconcile_post_hook(data)
        self._mark_approval_requests_paid()

    def remove_move_reconcile(self):
        statement_lines = self.statement_line_id
        res = super().remove_move_reconcile()
        if statement_lines:
            self._unmark_approval_requests_paid(statement_lines)
        return res

    def _approval_requests_for_statement_lines(self, statement_lines, payment_state):
        return (
            self.env["approval.request"]
            .sudo()
            .search(
                [
                    ("bank_statement_line_id", "in", statement_lines.ids),
                    ("state", "=", "approved"),
                    ("payment_state", "=", payment_state),
                ],
            )
        )

    def _mark_approval_requests_paid(self) -> None:
        statement_lines = self.statement_line_id
        if not statement_lines:
            return

        requests = self._approval_requests_for_statement_lines(
            statement_lines,
            "not_paid",
        )
        now_paid = requests.filtered(
            lambda request: request.bank_statement_line_id.is_reconciled,
        )
        if now_paid:
            now_paid.write(
                {
                    "payment_state": "paid",
                    "payment_date": fields.Date.context_today(self),
                    "paid_by_user_id": self.env.user.id,
                },
            )

    def _unmark_approval_requests_paid(self, statement_lines) -> None:
        requests = self._approval_requests_for_statement_lines(statement_lines, "paid")
        no_longer_paid = requests.filtered(
            lambda request: (
                not request.bank_statement_line_id.move_id.line_ids.filtered(
                    lambda line: line.matched_debit_ids or line.matched_credit_ids,
                )
            ),
        )
        if no_longer_paid:
            no_longer_paid.write(
                {
                    "payment_state": "not_paid",
                    "payment_date": False,
                    "paid_by_user_id": False,
                },
            )
