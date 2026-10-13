from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_debug = DebugLog(__name__)

PENDING_SENSITIVE_FIELDS = frozenset(
    {
        "account_id",
        "partner_id",
        "balance",
        "debit",
        "credit",
        "amount_currency",
        "currency_id",
    }
)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    pending_match_amount = fields.Monetary(
        string="Pending Match Amount",
        currency_field="company_currency_id",
        copy=False,
        readonly=True,
        help="What pending matches commit of this journal item, until the draft "
        "side is posted.",
    )
    pending_match_label = fields.Char(compute="_compute_pending_match_label")

    @api.depends("pending_match_amount")
    def _compute_pending_match_label(self) -> None:
        pending = self.filtered("pending_match_amount")
        (self - pending).pending_match_label = False
        if not pending:
            return
        matches = self.env["account.pending.match"].search(
            [
                "|",
                ("posted_line_id", "in", pending.ids),
                ("draft_line_id", "in", pending.ids),
            ]
        )
        names = defaultdict(list)
        for match in matches:
            names[match.posted_line_id].append(match.draft_move_id.display_name)
            names[match.draft_line_id].append(match.posted_move_id.display_name)
        for line in pending:
            line.pending_match_label = self.env._(
                "%(entries)s (pending posting)", entries=", ".join(names[line])
            )

    def _refresh_pending_match_amount(self) -> None:
        if not self:
            return
        self.env["account.pending.match"].flush_model(
            ["posted_line_id", "draft_line_id", "amount"]
        )
        self.env.execute_query(
            SQL(
                """
                UPDATE account_move_line line
                   SET pending_match_amount = NULLIF(
                           COALESCE((SELECT SUM(amount) FROM account_pending_match
                                      WHERE posted_line_id = line.id), 0)
                         + COALESCE((SELECT SUM(amount) FROM account_pending_match
                                      WHERE draft_line_id = line.id), 0),
                           0)
                 WHERE line.id = ANY(%s)
                """,
                self.ids,
            )
        )
        self.invalidate_recordset(["pending_match_amount"])

    def _get_pending_rate(self) -> float:
        self.check_singleton()
        if self.currency_id == self.company_currency_id:
            return 1.0
        balance = self.amount_residual or self.balance
        amount_currency = self.amount_residual_currency or self.amount_currency
        if self.company_currency_id.is_zero(balance) or self.currency_id.is_zero(
            amount_currency
        ):
            return 1.0
        return abs(amount_currency / balance)

    def _get_pending_matches(self):
        return self.env["account.pending.match"].search(
            ["|", ("posted_line_id", "in", self.ids), ("draft_line_id", "in", self.ids)]
        )

    @api.model
    def _reconcile_plan_or_pend(self, reconciliation_plan, origin):
        posted_plan = []
        to_pend = []
        for item in reconciliation_plan:
            drafts = item.filtered(lambda line: line.parent_state == "draft")
            if not drafts:
                posted_plan.append(item)
                continue
            posted = item - drafts
            if not posted:
                raise UserError(
                    self.env._(
                        "Draft entries cannot be matched with each other: post one "
                        "of them first."
                    )
                )
            posted_plan.append(posted)
            to_pend.append((posted, drafts))
        _debug.pipeline(
            "reconcile_or_pend",
            plan=len(reconciliation_plan),
            pending_items=len(to_pend),
            origin=origin,
        )
        if posted_plan:
            self._reconcile_plan(posted_plan)
        matches = self.env["account.pending.match"]
        for posted, drafts in to_pend:
            open_posted = posted.filtered(lambda line: not line.reconciled)
            matches |= matches._create_from_lines(open_posted, drafts, origin)
        return matches

    def _reconcile_or_pend(self, origin):
        return self._reconcile_plan_or_pend([self], origin)

    def _get_pending_lines_sensitive_to(self, vals):
        if not PENDING_SENSITIVE_FIELDS.intersection(vals):
            return self.browse()
        return self.filtered("pending_match_amount")

    def _remove_lost_pending_matches(self) -> None:
        if pending := self.exists():
            pending._get_pending_matches()._drop_lost()

    def _release_pending_matches(self) -> None:
        matches = self._get_pending_matches()
        removed = matches.filtered(lambda match: match.posted_line_id in self)
        removed._drop(
            reason=self.env._("the matched journal item was removed"), release=False
        )
        lost = self.env["account.pending.match"]
        for match in matches - removed:
            account = match.draft_line_id.account_id
            anchor = (match.draft_move_id.line_ids - self).filtered(
                lambda line, account=account: (
                    line.account_id == account and line.display_type == "payment_term"
                )
            )[:1]
            if anchor:
                match.draft_line_id = anchor
                anchor._refresh_pending_match_amount()
            else:
                lost |= match
        _debug.pipeline(
            "pending_lines_unlinked",
            lines=self,
            matches=matches,
            removed=removed,
            lost=lost,
        )
        lost._drop()
