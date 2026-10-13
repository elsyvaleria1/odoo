from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


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

    def _remove_lost_pending_matches(self, vals) -> None:
        if "state" in vals and vals["state"] != "posted":
            lines = self.line_ids.filtered("pending_match_amount")
            if lines:
                lines._get_pending_matches()._drop_lost()

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
        pendable = [
            (posted, draft, amount, amount_currency)
            for posted, draft, amount, amount_currency in pairs
            if posted.parent_state == "posted" and draft.parent_state == "draft"
        ]
        kept = [
            pair
            for pair in pendable
            if pair[0].partner_id.commercial_partner_id
            == pair[1].partner_id.commercial_partner_id
        ]
        if len(kept) != len(pendable):
            _debug.logic(
                "partials_released_across_partners",
                released=len(pendable) - len(kept),
            )
        vals_list = [
            {
                "posted_line_id": posted.id,
                "draft_line_id": draft.id,
                "amount": amount,
                "amount_currency": amount_currency,
                "currency_id": draft.currency_id.id,
                "origin": "reset_to_draft",
            }
            for posted, draft, amount, amount_currency in kept
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
