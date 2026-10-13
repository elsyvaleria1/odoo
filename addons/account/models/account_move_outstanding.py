from collections import defaultdict

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    payment_state_before_switch = fields.Char(copy=False)

    @_debug.perf.timed
    def action_view_bank_reconciliation_widget(self):
        _debug.lifecycle("action_view_bank_reconciliation_widget", records=self)
        return self.statement_line_id._action_view_bank_reconciliation_widget(
            default_context={
                "search_default_journal_id": self.statement_line_id.journal_id.id,
                "search_default_statement_line_id": self.statement_line_id.id,
                "default_st_line_id": self.statement_line_id.id,
            }
        )

    @_debug.perf.timed
    def action_view_bank_reconciliation_widget_statement(self):
        _debug.lifecycle(
            "action_view_bank_reconciliation_widget_statement", records=self
        )
        return self.statement_line_id._action_view_bank_reconciliation_widget(
            extra_domain=[("statement_id", "in", self.statement_id.ids)],
        )

    @_debug.perf.timed
    def _get_domain_outstanding_bank_statement_lines(self) -> list:
        self.check_singleton()
        if _debug.logic.enabled:
            _debug.logic(
                "outstanding_stline_scope",
                move=self,
                partner=self.commercial_partner_id,
                company=self.company_id,
                inbound=self.is_inbound(),
            )
        return [
            ("parent_state", "=", "posted"),
            ("partner_id", "=", self.commercial_partner_id.id),
            ("partner_id", "!=", False),
            ("account_id.account_type", "=", "asset_cash"),
            (
                "journal_id",
                "in",
                self.env["account.journal"]._search(
                    [
                        *self.env["account.journal"]._check_company_domain(
                            self.company_id.id
                        ),
                        ("type", "=", "bank"),
                    ]
                ),
            ),
            ("balance", ">" if self.is_inbound() else "<", 0.0),
            ("statement_line_id", "!=", False),
            (
                "move_id.line_ids",
                "any",
                [
                    (
                        "account_id",
                        "=",
                        self.company_id.account_config_id.account_journal_suspense_account_id.id,
                    ),
                    ("reconciled", "=", False),
                ],
            ),
        ]

    def _get_outstanding_bank_statement_lines(self):
        moves_by_scope = defaultdict(self.browse)
        for move in self:
            moves_by_scope[
                move.commercial_partner_id, move.company_id, move.is_inbound()
            ] |= move

        lines_by_move = {}
        for moves in moves_by_scope.values():
            lines = self.env["account.move.line"].search(  # noqa: E8507 -- one query per (partner, company, direction) scope; moves sharing one were merged above
                moves[0]._get_domain_outstanding_bank_statement_lines()
            )
            for move in moves:
                lines_by_move[move.id] = lines
        return lines_by_move

    def _get_outstanding_statement_line_widget_content(self, lines) -> list:
        self.check_singleton()
        content = []
        for line in lines:
            amount = line._get_statement_line_residual_in(
                self.currency_id, self.company_id
            )
            if self.currency_id.is_zero(amount):
                continue
            content.append(
                {
                    "bank_label": line.name
                    if line.journal_id.type == "bank"
                    else False,
                    "journal_name": line.ref or line.move_id.name,
                    "amount": amount,
                    "currency_id": self.currency_id.id,
                    "id": line.id,
                    "move_id": line.move_id.id,
                    "date": fields.Date.to_string(line.date),
                    "account_payment_id": line.payment_id.id,
                }
            )
        return content
