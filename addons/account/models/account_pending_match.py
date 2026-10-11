from collections import defaultdict

from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

from .account_payment import _PAYMENTS_UNSETTLED

_debug = DebugLog(__name__)

PENDING_MATCH_ORIGINS = [
    ("bank_auto", "Bank matching proposal"),
    ("bank_manual", "Bank matching"),
    ("outstanding", "Outstanding credit or debit"),
    ("register_payment", "Payment registration"),
    ("reset_to_draft", "Reset to draft"),
    ("manual", "Manual matching"),
]


class AccountPendingMatch(models.Model):
    _name = "account.pending.match"
    _description = "Pending Match"
    _order = "id"

    posted_line_id = fields.Many2one(
        comodel_name="account.move.line",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    draft_line_id = fields.Many2one(
        comodel_name="account.move.line",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    posted_move_id = fields.Many2one(
        comodel_name="account.move",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    draft_move_id = fields.Many2one(
        comodel_name="account.move",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        index=True,
        readonly=True,
        required=True,
    )
    partner_id = fields.Many2one(related="draft_line_id.partner_id")
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Company Currency",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
        required=True,
    )
    amount = fields.Monetary(
        currency_field="company_currency_id",
        readonly=True,
        required=True,
    )
    amount_currency = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        required=True,
    )
    origin = fields.Selection(
        selection=PENDING_MATCH_ORIGINS,
        readonly=True,
        required=True,
    )

    _positive_amount = models.Constraint(
        "CHECK(amount > 0)", "A pending match carries a positive amount."
    )
    _unique_pair = models.Constraint(
        "UNIQUE(posted_line_id, draft_line_id)",
        "A journal item is promised to a draft journal item once.",
    )

    @api.constrains("posted_line_id", "draft_line_id", "amount")
    def _check_pending_match_contract(self) -> None:
        for match in self:
            posted, draft = match.posted_line_id, match.draft_line_id
            if posted.parent_state != "posted" or draft.parent_state != "draft":
                raise ValidationError(
                    self.env._(
                        "A pending match joins a posted journal item to a draft one."
                    )
                )
            if posted.account_id != draft.account_id:
                raise ValidationError(
                    self.env._(
                        "A pending match joins journal items of the same account."
                    )
                )
            if (
                posted.partner_id.commercial_partner_id
                != draft.partner_id.commercial_partner_id
            ):
                raise ValidationError(
                    self.env._(
                        "A pending match joins journal items of the same partner."
                    )
                )
            if posted.company_id.root_id != draft.company_id.root_id:
                raise ValidationError(
                    self.env._(
                        "A pending match joins journal items of the same company."
                    )
                )
            if (posted.balance > 0) == (draft.balance > 0):
                raise ValidationError(
                    self.env._(
                        "A pending match joins a debit to a credit journal item."
                    )
                )
        reserved = defaultdict(float)
        for match in self.search([("posted_line_id", "in", self.posted_line_id.ids)]):
            reserved[match.posted_line_id] += match.amount
        for line, amount in reserved.items():
            if (
                line.company_currency_id.compare_amounts(
                    amount, abs(line.amount_residual)
                )
                > 0
            ):
                raise ValidationError(
                    self.env._(
                        "%(line)s is promised beyond what it leaves open.",
                        line=line.display_name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        lines = self.env["account.move.line"]
        for vals in vals_list:
            posted = lines.browse(vals["posted_line_id"])
            vals["posted_move_id"] = posted.move_id.id
            vals["draft_move_id"] = lines.browse(vals["draft_line_id"]).move_id.id
            vals["company_id"] = posted.company_id.id
        matches = super().create(vals_list)
        (matches.posted_line_id | matches.draft_line_id)._refresh_pending_match_amount()
        _debug.lifecycle("create", matches=matches)
        return matches

    def unlink(self):
        lines = self.posted_line_id | self.draft_line_id
        res = super().unlink()
        lines.exists()._refresh_pending_match_amount()
        return res

    @api.model
    def _create_from_lines(self, posted_lines, draft_lines, origin):
        reserved = {line: line.pending_match_amount for line in posted_lines}
        vals_list = []
        for draft in draft_lines.sorted(
            lambda line: (line.date_maturity or line.date, line.id)
        ):
            company_currency = draft.company_currency_id
            draft_rate = draft._get_pending_rate()
            need = abs(draft.amount_residual) - draft.pending_match_amount
            for posted in posted_lines:
                if not company_currency.compare_amounts(need, 0) > 0:
                    break
                if (posted.balance > 0) == (draft.balance > 0):
                    continue
                available = abs(posted.amount_residual) - reserved[posted]
                if not company_currency.compare_amounts(available, 0) > 0:
                    continue
                if (
                    posted.currency_id == draft.currency_id
                    and draft.currency_id != company_currency
                ):
                    posted_rate = posted._get_pending_rate()
                    taken = min(available * posted_rate, need * draft_rate)
                    amount = company_currency.round(taken / posted_rate)
                    amount_currency = draft.currency_id.round(taken)
                    need -= taken / draft_rate
                else:
                    amount = min(available, need)
                    amount_currency = draft.currency_id.round(amount * draft_rate)
                    need -= amount
                reserved[posted] += amount
                vals_list.append(
                    {
                        "posted_line_id": posted.id,
                        "draft_line_id": draft.id,
                        "amount": amount,
                        "amount_currency": amount_currency,
                        "currency_id": draft.currency_id.id,
                        "origin": origin,
                    }
                )
        matches = self.create(vals_list)
        _debug.pipeline(
            "pending_matches_created",
            posted=posted_lines,
            drafts=draft_lines,
            origin=origin,
            matches=matches,
        )
        if matches:
            matches._log_pending_created()
            matches.draft_move_id._post_on_pending_match()
        return matches

    def _log_pending_created(self) -> None:
        for draft_move, matches in self.grouped("draft_move_id").items():
            draft_move._message_log(
                body=self.env._(
                    "Payment matched, pending the posting of this entry: %(entries)s",
                    entries=matches._describe("posted_move_id"),
                )
            )

    def _describe(self, move_fname) -> Markup:
        return Markup(", ").join(
            Markup("%s (%s)")
            % (
                match[move_fname]._get_html_link(),
                match.company_currency_id.format(match.amount),
            )
            for match in self
        )

    def _materialize(self) -> None:
        pairs = [
            (
                match.posted_line_id,
                match.draft_line_id,
                match.amount,
                match.amount_currency
                if match.posted_line_id.currency_id == match.currency_id
                else None,
                match.amount_currency,
            )
            for match in self.sorted("id")
        ]
        self.unlink()
        shortfall = defaultdict(float)
        aml_model = self.env["account.move.line"]
        for posted, draft, amount, posted_cap_currency, draft_cap_currency in pairs:
            if posted.parent_state != "posted" or draft.parent_state != "posted":
                continue
            before = abs(draft.amount_residual)
            aml_model._reconcile_plan(
                [posted | draft],
                residual_caps={
                    posted: (amount, posted_cap_currency),
                    draft: (amount, draft_cap_currency),
                },
            )
            applied = before - abs(draft.amount_residual)
            if posted.company_currency_id.compare_amounts(applied, amount) < 0:
                shortfall[draft.move_id] += amount - applied
        _debug.pipeline(
            "pending_matches_materialized",
            pairs=len(pairs),
            shortfalls=len(shortfall),
        )
        for move, missing in shortfall.items():
            move._message_log(
                body=self.env._(
                    "Posting completed the pending payment matches %(missing)s short: "
                    "the counterpart no longer leaves that amount open.",
                    missing=move.company_currency_id.format(missing),
                )
            )

    def _get_lost(self):
        lost = self.browse()
        drafts_over = set()
        totals = defaultdict(float)
        for match in self:
            totals[match.draft_line_id] += match.amount_currency
        for draft, total in totals.items():
            if draft.parent_state == "draft" and (
                draft.currency_id
                not in self.filtered(
                    lambda match, draft=draft: match.draft_line_id == draft
                ).currency_id
                or draft.currency_id.compare_amounts(
                    abs(draft.amount_residual_currency), total
                )
                < 0
            ):
                drafts_over.add(draft.id)
        for match in self:
            posted, draft = match.posted_line_id, match.draft_line_id
            if (
                draft.parent_state == "cancel"
                or posted.parent_state != "posted"
                or posted.account_id != draft.account_id
                or posted.partner_id.commercial_partner_id
                != draft.partner_id.commercial_partner_id
                or draft.id in drafts_over
            ):
                lost |= match
        return lost

    def _drop_lost(self) -> None:
        if lost := self.exists()._get_lost():
            lost._drop()

    def _unlink_settled_documents(self) -> None:
        for match in self:
            for payment_move, document in (
                (match.draft_move_id, match.posted_move_id),
                (match.posted_move_id, match.draft_move_id),
            ):
                payment = payment_move.exists().origin_payment_id
                document = document.exists()
                if not payment or document not in payment.invoice_ids:
                    continue
                document.matched_payment_ids = [Command.unlink(payment.id)]
                self.env.cr.cache.setdefault(_PAYMENTS_UNSETTLED, set()).add(payment.id)
                payment._message_log(
                    body=self.env._(
                        "%(document)s is no longer among the documents this payment "
                        "settles: their pending match was dropped.",
                        document=document._get_html_link(),
                    )
                )

    def _drop(self, reason=None, release=True) -> None:
        self = self.exists()
        if not self:
            return
        reason = reason or self.env._(
            "the draft entry was cancelled, deleted or changed"
        )
        _debug.pipeline("pending_matches_dropped", matches=self, reason=reason)
        released = self.posted_line_id.filtered(
            lambda line: (
                release
                and line.parent_state == "posted"
                and line.move_id.statement_line_id
            )
        )
        for match in self:
            amount = match.company_currency_id.format(match.amount)
            draft_move = match.draft_move_id.exists()
            match.posted_move_id._message_log(
                body=self.env._(
                    "The pending payment match of %(amount)s with %(other)s was "
                    "dropped: %(reason)s.",
                    amount=amount,
                    other=draft_move._get_html_link()
                    if draft_move
                    else match.draft_line_id.move_name or "",
                    reason=reason,
                )
            )
            if draft_move:
                draft_move._message_log(
                    body=self.env._(
                        "The pending payment match of %(amount)s with %(other)s was "
                        "dropped: %(reason)s.",
                        amount=amount,
                        other=match.posted_move_id._get_html_link(),
                        reason=reason,
                    )
                )
        self._unlink_settled_documents()
        self.unlink()
        for line in released.filtered(lambda line: not line.pending_match_amount):
            line.move_id.statement_line_id._release_pending_line(line)
