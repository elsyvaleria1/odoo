from typing import Any

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict
from odoo.tools.misc import clean_context

from odoo.addons.approval.models.mixin_approval import (
    APPROVAL_TRIGGER_CATEGORY,
    APPROVAL_TRIGGER_RULE,
)

MAX_DETAIL_LINES = 5


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "mixin.approval.gate"]

    _approval_requester_field = "invoice_user_id"
    _access_anchors = frozendict(
        {
            "approval_pending_user": models.Anchor(
                "approval_pending_user_ids", kind="owner"
            ),
        }
    )

    count_approval = fields.Integer(compute="_compute_count_approval")

    @api.depends("line_ids.approval_request_line_id.approval_request_id")
    def _compute_count_approval(self) -> None:
        # Read straight down the declared depends path. Searching
        # approval.request.line on account_move_id instead read a DIFFERENT
        # field from the one that invalidates this compute, so the count could
        # cache stale and never recover.
        for move in self:
            if not move._origin.id:
                move.count_approval = 0
                continue
            move.count_approval = len(
                move.line_ids.approval_request_line_id.approval_request_id,
            )

    @api.depends(
        "amount_total",
        "date",
        "currency_id",
        "move_type",
        "partner_id",
        "partner_id.invoice_approval_required",
        "partner_id.bill_approval_required",
        "journal_id",
        "journal_id.approval_required",
        "company_id.invoice_approval_threshold",
        "company_id.bill_approval_threshold",
        "approval_request_id",
        "approval_request_id.target_model",
        "approval_request_id.state",
    )
    def _compute_approval_required(self) -> None:
        super()._compute_approval_required()

    def _get_approval_trigger(self) -> str | bool:
        self.check_singleton()
        request = self.approval_request_id
        if (
            request
            and request.target_model == "account.move"
            and request.state == "approved"
        ) or self.move_type == "entry":
            return False
        if self._approval_trigger_fired():
            return APPROVAL_TRIGGER_RULE
        return APPROVAL_TRIGGER_CATEGORY

    def _amount_total_company_currency(self) -> float:
        self.check_singleton()
        company_currency = self.company_id.currency_id
        if not self.currency_id or self.currency_id == company_currency:
            return self.amount_total
        return self.currency_id._convert(
            self.amount_total,
            company_currency,
            self.company_id,
            self.date or fields.Date.context_today(self),
        )

    def _approval_trigger_fired(self) -> bool:
        self.check_singleton()
        if self.partner_id:
            if (
                self.move_type in ("out_invoice", "out_refund")
                and self.partner_id.invoice_approval_required
            ):
                return True
            if (
                self.move_type in ("in_invoice", "in_refund")
                and self.partner_id.bill_approval_required
            ):
                return True

        if self.journal_id and self.journal_id.approval_required:
            return True

        if self.move_type in ("out_invoice", "out_refund"):
            threshold = self.company_id.invoice_approval_threshold
        elif self.move_type in ("in_invoice", "in_refund"):
            threshold = self.company_id.bill_approval_threshold
        else:
            return False
        return 0 < threshold <= self._amount_total_company_currency()

    def _get_fields_approval_required(self) -> list[str]:
        return ["partner_id", "line_ids"]

    def _get_fields_approval_protected(self) -> list[str]:
        return [
            "line_ids",
            "invoice_line_ids",
            "partner_id",
            "currency_id",
            "journal_id",
        ]

    def _is_approval_invalidated_by_changes(self, fields_changed) -> bool:
        """Amount-bearing changes keep the approval: `_post_check_business_rules`
        compares the move's total with the approved amount at posting, even once
        the change has taken the move out of every category's range. Anything
        else -- another partner, another journal -- is not what was approved."""
        return bool(
            set(fields_changed) - {"currency_id", "line_ids", "invoice_line_ids"}
        )

    def _check_approved_amount(self) -> None:
        self.check_singleton()
        approved_amount = self.approval_request_id.amount
        approved_currency = self.approval_request_id.currency_id
        current_amount = abs(self.amount_total)
        comparable_amount = approved_amount
        if (
            approved_currency
            and self.currency_id
            and approved_currency != self.currency_id
        ):
            comparable_amount = approved_currency._convert(
                approved_amount,
                self.currency_id,
                self.company_id,
                self.date or fields.Date.context_today(self),
            )

        if self.currency_id.compare_amounts(current_amount, comparable_amount) == 0:
            return

        raise UserError(
            self.env._(
                "%(document)s amount has changed since approval was granted.\n\n"
                "Approved amount: %(symbol_approved)s %(approved)s\n"
                "Current amount: %(symbol_current)s %(current)s\n\n"
                "Undo the change, or reset the approval to draft and submit it "
                "again for the updated amount.",
                document=self._move_type_label(),
                symbol_approved=approved_currency.symbol or self.currency_id.symbol,
                symbol_current=self.currency_id.symbol,
                approved=f"{approved_amount:,.2f}",
                current=f"{current_amount:,.2f}",
            ),
        )

    def _get_domain_approval_category(self) -> list[Any]:
        return [
            ("approval_type", "=", "accounting"),
            ("target_model", "=", False),
        ]

    def _get_approval_category_fallback(self, categories):
        self.check_singleton()
        if not self._approval_trigger_fired():
            return self.env["approval.category"].browse()
        return categories.filtered(
            lambda c: (
                not (
                    c.move_amount_min
                    or c.move_amount_max
                    or c.move_partner_ids
                    or c.journal_ids
                )
            ),
        )[:1]

    def _raise_approval_category_not_configured(self) -> None:
        self.check_singleton()
        raise UserError(
            self.env._(
                "No accounting approval category is available for %(company)s, "
                "but %(document)s requires approval.\n\n"
                "Create one for that company, or make an existing category "
                "global by clearing its Company field.\n\n"
                "Go to: Accounting → Configuration → Approval Types",
                company=self.company_id.display_name,
                document=self.display_name,
            ),
        )

    def _prepare_approval_request_values(self, category: Any) -> dict[str, Any]:
        vals = super()._prepare_approval_request_values(category)

        vals.update(
            {
                "partner_id": self.partner_id.id if self.partner_id else False,
                "amount": abs(self.amount_total),
                "date": self.date or fields.Date.today(),
                "reference": self.ref or self.payment_reference or "",
            },
        )

        if category.has_journal != "no" and self.journal_id:
            vals["journal_id"] = self.journal_id.id

        return vals

    def _get_approval_reason_html(self) -> str:
        self.check_singleton()

        move_type_label = dict(self._fields["move_type"].selection).get(
            self.move_type,
            self.move_type,
        )

        currency_symbol = self.currency_id.symbol if self.currency_id else ""

        reason_parts = [
            f"<h4>{escape(move_type_label)}: {escape(self.name)}</h4>",
        ]

        if self.partner_id:
            reason_parts.append(
                f"<p><strong>Partner:</strong> {escape(self.partner_id.name)}</p>",
            )

        reason_parts.append(
            f"<p><strong>Total Amount:</strong> {escape(currency_symbol)} {self.amount_total:,.2f}</p>",
        )

        if self.date:
            reason_parts.append(f"<p><strong>Date:</strong> {self.date}</p>")

        if self.journal_id:
            reason_parts.append(
                f"<p><strong>Journal:</strong> {escape(self.journal_id.name)}</p>",
            )

        if self.ref:
            reason_parts.append(
                f"<p><strong>Reference:</strong> {escape(self.ref)}</p>"
            )

        reason_parts.extend(self._get_approval_notes_html())

        invoice_lines = self.line_ids.filtered(
            lambda line: (
                not line.display_type
                and line.account_id
                and line.account_id.account_type
                in [
                    "asset_receivable",
                    "liability_payable",
                    "income",
                    "expense",
                ]
            ),
        )

        if len(invoice_lines) <= MAX_DETAIL_LINES and invoice_lines:
            reason_parts.append("<p><strong>Lines:</strong></p><ul>")
            for line in invoice_lines:
                if line.product_id:
                    reason_parts.append(
                        f"<li>{escape(line.product_id.name)} - "
                        f"Qty: {line.quantity} - "
                        f"{escape(currency_symbol)} {line.balance:,.2f}</li>",
                    )
                else:
                    reason_parts.append(
                        f"<li>{escape(line.name)} - {escape(currency_symbol)} {line.balance:,.2f}</li>",
                    )
            reason_parts.append("</ul>")
        elif invoice_lines:
            reason_parts.append(
                f"<p><strong>Number of Lines:</strong> {len(invoice_lines)}</p>",
            )

        return "".join(reason_parts)

    def _get_approval_notes_html(self) -> list[str]:
        self.check_singleton()
        notes = []
        for label, note in (
            (self.env._("Partner Notes"), self.partner_id.invoice_approval_notes),
            (self.env._("Journal Notes"), self.journal_id.approval_notes),
        ):
            if note:
                notes.append(
                    f"<p><strong>{escape(label)}:</strong> {escape(note)}</p>",
                )
        return notes

    def _check_can_request_approval(self, candidates=None):
        if (
            self.approval_request_id
            and self.approval_request_id.target_model == "account.move"
        ):
            raise UserError(
                self.env._(
                    "This invoice/bill was created from an approval request (%s). "
                    "It does not need a separate approval.",
                    self.approval_request_id.name,
                ),
            )

        return super()._check_can_request_approval(candidates)

    def action_view_approval(self) -> dict[str, Any]:
        self.check_singleton()
        approvals_ids = (
            self.env["approval.request.line"]
            .search([("account_move_id", "=", self.id)])
            .mapped("approval_request_id")
            .ids
        )
        domain = [("id", "in", approvals_ids)]
        return {
            "name": self.env._("Approvals"),
            "type": "ir.actions.act_window",
            "res_model": "approval.request",
            "view_mode": "list,form",
            "view_type": "list",
            "context": clean_context(self.env.context),
            "domain": domain,
        }

    def _get_approval_snapshot(self, operation: str) -> dict[str, Any]:
        snapshot = super()._get_approval_snapshot(operation)
        return snapshot | {
            "partner_id": self.partner_id.id,
            "currency_id": self.currency_id.id,
            "journal_id": self.journal_id.id,
            "lines": sorted(
                [
                    line.product_id.id or 0,
                    line.account_id.id or 0,
                    line.quantity,
                    line.price_unit,
                    line.discount,
                    sorted(line.tax_ids.ids),
                ]
                for line in self.invoice_line_ids
                if line.display_type == "product"
            ),
        }

    def _check_approval_covers(self, operation: str) -> None:
        # the amount first: when it moved, saying so is the more useful refusal
        if self.approval_request_id.target_model != "account.move":
            self._check_approved_amount()
        super()._check_approval_covers(operation)

    def _is_approval_reasked_after_refusal(self, operation: str) -> bool:
        return True

    def _get_operation_failure_note(self, operation: str) -> str:
        return self.env._(
            "Approval was granted but the document could not be auto-posted: %(error)s"
        )

    def _is_operation_run_on_approval(self, operation: str) -> bool:
        return bool(
            self.approval_request_id.category_id.move_auto_post
            and self.state == "draft"
        )

    def action_cancel(self) -> None:
        result = super().action_cancel()
        self._refuse_pending_approval()
        return result

    def action_draft(self) -> None:
        result = super().action_draft()
        self._clear_refused_approval_link()
        return result

    def _move_type_label(self) -> str:
        self.check_singleton()
        return dict(self._fields["move_type"].selection).get(
            self.move_type,
            self.move_type,
        )

    def _approval_approved_message_values(self) -> dict:
        move_type_label = self._move_type_label()

        approver_names = self._approval_decider_names("approved")

        currency_symbol = self.currency_id.symbol if self.currency_id else ""

        return {
            "body": Markup(
                "<p>✅ <strong>%s %s</strong></p><p>%s: %s</p><p>%s: %s %s</p>"
            )
            % (
                escape(move_type_label),
                self.env._("Approved"),
                self.env._("Approved by"),
                escape(approver_names),
                self.env._("Approved amount"),
                escape(currency_symbol),
                f"{self.amount_total:,.2f}",
            ),
            "subject": self.env._("%s Approved", move_type_label),
            "message_type": "notification",
            "subtype_xmlid": "approval_account.mt_invoice_approved",
        }

    def _on_approval_refused(self) -> None:
        self.check_singleton()
        refused_approver = self.approval_request_id.approver_ids.filtered(
            lambda a: a.state == "refused",
        )
        move_type_label = self._move_type_label()

        rejector_name = (
            refused_approver[0].user_id.name
            if refused_approver and refused_approver[0].user_id
            else self.env._("Unknown")
        )
        self.message_post(
            body=Markup("<p>❌ <strong>%s %s</strong></p><p>%s: %s</p>")
            % (
                escape(move_type_label),
                self.env._("Rejected"),
                self.env._("Rejected by"),
                escape(rejector_name),
            ),
            subject=self.env._("%s Rejected", move_type_label),
            message_type="notification",
            subtype_xmlid="approval_account.mt_invoice_refused",
        )
