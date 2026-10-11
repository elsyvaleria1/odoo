from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
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

    def write(self, vals):
        res = super().write(vals)
        if PENDING_SENSITIVE_FIELDS.intersection(vals) and (
            pending := self.filtered("pending_match_amount")
        ):
            pending._get_pending_matches()._drop_lost()
        return res

    def unlink(self):
        if pending := self.filtered("pending_match_amount"):
            pending._release_pending_matches()
        return super().unlink()

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


class AccountMove(models.Model):
    _inherit = "account.move"

    pending_match_ids = fields.One2many(
        comodel_name="account.pending.match",
        inverse_name="draft_move_id",
        string="Pending Matches",
        readonly=True,
    )
    pending_payment_amount = fields.Monetary(
        string="Pending Payment",
        currency_field="company_currency_id",
        compute="_compute_pending_payment_amount",
    )

    @api.depends("pending_match_ids.amount")
    def _compute_pending_payment_amount(self) -> None:
        for move in self:
            move.pending_payment_amount = sum(move.pending_match_ids.mapped("amount"))

    def write(self, vals):
        res = super().write(vals)
        if "state" in vals and vals["state"] != "posted":
            lines = self.line_ids.filtered("pending_match_amount")
            if lines:
                lines._get_pending_matches()._drop_lost()
        return res

    def _get_pending_payments_widget_vals(self) -> list:
        self.check_singleton()
        vals = []
        for match in self.pending_match_ids:
            counterpart = match.posted_line_id
            vals.append(
                {
                    "name": counterpart.name,
                    "journal_name": counterpart.journal_id.name,
                    "company_name": False,
                    "amount": match.amount_currency,
                    "currency_id": match.currency_id.id,
                    "date": counterpart.date,
                    "partial_id": False,
                    "pending_match_id": match.id,
                    "is_pending": True,
                    "account_payment_id": counterpart.payment_id.id,
                    "payment_method_name": counterpart.payment_id.payment_channel_id.name,
                    "move_id": counterpart.move_id.id,
                    "is_refund": False,
                    "ref": counterpart.move_id.name,
                    "is_exchange": False,
                    "amount_company_currency": match.company_currency_id.format(
                        match.amount
                    ),
                    "amount_foreign_currency": False,
                }
            )
        return vals

    def _materialize_pending_matches(self) -> None:
        lines = self.line_ids.filtered("pending_match_amount")
        if not lines:
            return
        matches = self.env["account.pending.match"].search(
            [("draft_line_id", "in", lines.ids)]
        )
        _debug.pipeline("materialize_pending", moves=self, matches=matches)
        matches._materialize()

    def _collect_partials_to_pend(self) -> list:
        automatic = self.env["account.move"]
        pairs = []
        for line in self.line_ids:
            for partial, counterpart in [
                *((p, p.credit_move_id) for p in line.matched_credit_ids),
                *((p, p.debit_move_id) for p in line.matched_debit_ids),
            ]:
                counterpart_move = counterpart.move_id
                if (
                    counterpart_move in self
                    or counterpart_move == partial.exchange_move_id
                    or counterpart_move.tax_cash_basis_rec_id
                    or counterpart_move.tax_cash_basis_origin_move_id
                    or counterpart_move.exchange_diff_partial_ids
                ):
                    automatic |= counterpart_move
                    continue
                pairs.append(
                    (
                        counterpart,
                        line,
                        partial.amount,
                        partial.debit_amount_currency
                        if partial.debit_move_id == line
                        else partial.credit_amount_currency,
                    )
                )
        _debug.logic(
            "partials_to_pend_collected",
            moves=self,
            pairs=len(pairs),
            skipped_automatic=automatic,
        )
        return pairs

    @api.model
    def _pend_collected_partials(self, pairs) -> None:
        vals_list = [
            {
                "posted_line_id": posted.id,
                "draft_line_id": draft.id,
                "amount": amount,
                "amount_currency": amount_currency,
                "currency_id": draft.currency_id.id,
                "origin": "reset_to_draft",
            }
            for posted, draft, amount, amount_currency in pairs
            if posted.parent_state == "posted" and draft.parent_state == "draft"
        ]
        if vals_list:
            self.env["account.pending.match"].create(vals_list)

    def _is_clean_import(self) -> bool:
        self.check_singleton()
        return bool(
            self.invoice_line_ids
            and all(line.is_imported for line in self.invoice_line_ids)
            and not self.is_manually_modified
        )

    def _is_eligible_for_post_on_pending_match(self) -> bool:
        self.check_singleton()
        return bool(
            self.state == "draft"
            and self.is_purchase_document(include_receipts=True)
            and self.company_id.account_config_id.autopost_bills
            and self.partner_id
            and self.partner_id.autopost_bills in ("always", "ask")
            and not self.abnormal_amount_warning
            and not self.duplicated_ref_ids
            and not self.restrict_mode_hash_table
            and self._is_clean_import()
        )

    def _post_on_pending_match(self) -> None:
        for move in self:
            if not move._is_eligible_for_post_on_pending_match():
                continue
            _debug.logic("post_on_pending_match", move=move)
            try:
                with self.env.cr.savepoint():
                    move.action_post()
            except (UserError, ValidationError) as error:
                move._message_log(
                    body=self.env._(
                        "The bill matched a payment but was not posted automatically: "
                        "%(reason)s",
                        reason=error,
                    )
                )

    def js_remove_pending_match(self, pending_match_id):
        self.check_singleton()
        match = self.env["account.pending.match"].browse(pending_match_id).exists()
        if match and not self.line_ids & (match.posted_line_id | match.draft_line_id):
            raise UserError(
                self.env._("This pending match does not concern this document.")
            )
        match._drop(reason=self.env._("removed by %(user)s", user=self.env.user.name))
