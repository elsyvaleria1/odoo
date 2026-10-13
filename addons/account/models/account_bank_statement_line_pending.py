from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    draft_match_proposal_ids = fields.Many2many(
        comodel_name="account.move.line",
        relation="account_bank_statement_line_draft_proposal_rel",
        column1="statement_line_id",
        column2="move_line_id",
        string="Proposed Draft Matches",
        copy=False,
        readonly=True,
    )
    draft_match_proposal_label = fields.Char(
        compute="_compute_draft_match_proposal_label"
    )

    @api.depends(
        "is_reconciled",
        "draft_match_proposal_ids.parent_state",
        "draft_match_proposal_ids.move_name",
    )
    def _compute_draft_match_proposal_label(self) -> None:
        for st_line in self:
            proposals = st_line._get_live_draft_match_proposals()
            st_line.draft_match_proposal_label = (
                ", ".join(proposals.move_id.mapped("display_name"))
                if proposals
                else False
            )

    def _get_live_draft_match_proposals(self):
        self.check_singleton()
        if self.is_reconciled:
            return self.env["account.move.line"]
        return self.draft_match_proposal_ids.filtered(
            lambda line: line.parent_state == "draft" and not line.pending_match_amount
        )

    def _get_matching_parent_state(self) -> str:
        return "draft" if self.env.context.get("propose_draft_matches") else "posted"

    def _propose_draft_matches(self) -> None:
        remaining = (
            self.exists()
            ._filtered_auto_reconcilable()
            .filtered(lambda st_line: not st_line.draft_match_proposal_ids)
        )
        if not remaining:
            return
        proposing = remaining.with_context(propose_draft_matches=True)
        st_move_ids = remaining.move_id.ids
        account_ids = proposing._get_matchable_account_ids()
        proposing._match_payment_references(
            st_move_ids, account_ids, set(remaining.ids)
        )
        left = remaining.filtered(lambda st_line: not st_line.draft_match_proposal_ids)
        if left:
            proposing._handle_reconciliation_matching_amount(
                st_move_ids, account_ids, set(left.ids)
            )
        left = left.filtered(lambda st_line: not st_line.draft_match_proposal_ids)
        if left:
            proposing._match_amount_alone(account_ids, set(left.ids))
        _debug.pipeline(
            "draft_matches_proposed",
            st_lines=remaining,
            proposed=remaining.filtered("draft_match_proposal_ids"),
        )

    def _record_draft_match_proposal(self, move_lines_ids) -> None:
        self.check_singleton()
        if self.draft_match_proposal_ids:
            return
        lines = (
            self.env["account.move.line"]
            .browse(
                move_lines_ids if isinstance(move_lines_ids, list) else [move_lines_ids]
            )
            .filtered(lambda line: line.parent_state == "draft")
        )
        if lines:
            self.draft_match_proposal_ids = lines

    def action_confirm_draft_match_proposal(self) -> None:
        self.check_access("write")
        for st_line in self:
            proposals = st_line._get_live_draft_match_proposals()
            st_line.draft_match_proposal_ids = False
            if proposals:
                st_line.with_context(
                    pending_match_origin="bank_auto"
                ).set_line_bank_statement_line(proposals.ids)

    def action_dismiss_draft_match_proposal(self) -> None:
        self.check_access("write")
        self.draft_match_proposal_ids = False

    def _release_pending_line(self, line) -> None:
        self.check_singleton()
        liquidity_lines, _suspense_lines, other_lines = self._seek_for_lines()
        try:
            with self.env.cr.savepoint():
                self._set_move_line_to_statement_line_move(
                    liquidity_lines + other_lines - line, []
                )
        except UserError as error:
            _debug.logic("pending_line_kept", st_line=self, line=line, error=str(error))
            self.move_id._message_log(
                body=self.env._(
                    "The transaction could not go back to the bank reconciliation: "
                    "%(reason)s. Its amount stays open as an advance.",
                    reason=error,
                )
            )
            return
        self.auto_reconcile_rule = False
        self._post_matching_unreconciled()
