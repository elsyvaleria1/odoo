from typing import TYPE_CHECKING, Any

from markupsafe import Markup

from odoo import _lt, api, fields, models

if TYPE_CHECKING:
    from odoo.addons.approval.models.approval_approver import ApprovalApprover

_HIDDEN_KEYS = frozenset(
    {
        "partner_fx_id",
        "partner_cn_id",
        "cfdi_use_code",
        "file_b64",
        "file_mimetype",
    }
)

_LABELS = {
    "partner_fx_name": _lt("Billed to"),
    "product_category": _lt("Product category"),
    "cfdi_use": _lt("CFDI use"),
    "company": _lt("Company"),
    "partner_cn_name": _lt("Payment applied to"),
    "payment_method": _lt("Payment method"),
    "date": _lt("Date"),
    "amount": _lt("Amount"),
    "product_reference": _lt("Product reference"),
}


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    telegram_data = fields.Json()
    telegram_data_formatted = fields.Html(
        compute="_compute_telegram_data_formatted",
        readonly=True,
    )

    tg_change_note = fields.Char(
        string="Telegram Change Note",
        copy=False,
        help="Latest approver comment explaining the requested change, shown "
        "to the owner in the Telegram correction panel.",
    )

    def action_request_change(
        self, approver: ApprovalApprover | None = None
    ) -> dict[str, Any] | None:
        result = super().action_request_change(approver=approver)
        notifier = self.env["telegram.approval.notifier"]
        note = self.env.context.get("change_note")
        for request in self:
            if not request.pending_change_field:
                continue
            request.write({"tg_change_note": note or False})
            notifier._notify_owner_change(
                request, request.pending_change_field, note=note
            )
        return result

    def _notify_if_terminal_transition(self, old_state: str) -> None:
        result = super()._notify_if_terminal_transition(old_state)
        if self.state != old_state and self.state in self._TERMINAL_STATES:
            self.env["telegram.approval.notifier"]._notify_owner_outcome(self)
        return result

    def action_resubmit(self) -> None:
        super(
            ApprovalRequest, self.with_context(approval_telegram_hold_push=True)
        ).action_resubmit()
        self.write({"tg_change_note": False})
        notifier = self.env["telegram.approval.notifier"]
        if not notifier._feature_active():
            return
        for request in self:
            asked = (
                request.approver_ids & request._get_approval_activities().approver_id
            )
            for approver in asked.filtered(lambda row: row.state == "pending"):
                notifier._notify_approver(approver, resubmitted=True)

    @api.depends("telegram_data")
    def _compute_telegram_data_formatted(self) -> None:
        for request in self:
            if not request.telegram_data:
                request.telegram_data_formatted = False
                continue

            rows = Markup()
            for key, value in request.telegram_data.items():
                if key in _HIDDEN_KEYS:
                    continue
                label = _LABELS.get(key, key)
                rows += Markup(
                    "<tr>"
                    '<td style="padding: 4px; font-weight: bold;">{label}</td>'
                    '<td style="padding: 4px;">{value}</td>'
                    "</tr>"
                ).format(label=label, value=value)

            request.telegram_data_formatted = Markup(
                '<div style="font-family: sans-serif; font-size: 14px;">'
                '<table class="o_list_table table table-sm table-hover">'
                "<tbody>{rows}</tbody>"
                "</table></div>"
            ).format(rows=rows)
