from typing import TYPE_CHECKING, Any

from odoo import api, models

from odoo.addons.telegram.tools import keyboard as kb

if TYPE_CHECKING:
    from odoo.api import Environment

    from odoo.addons.approval.models.approval_approver import ApprovalApprover
    from odoo.addons.approval.models.approval_request import ApprovalRequest
    from odoo.addons.telegram.models.telegram_bot import TelegramBot


class TelegramApprovalNotifier(models.AbstractModel):
    _inherit = "telegram.approval.notifier"

    @api.model
    def _summary_review_lines(
        self, request: ApprovalRequest, env: Environment
    ) -> list[str]:
        lines = super()._summary_review_lines(request, env)
        if self._awaits_bank_line(request):
            lines.append(
                env._(
                    "To approve it, link the bank transaction that shows the payment, "
                    "in Odoo: it cannot be approved from here without it."
                )
            )
        return lines

    @api.model
    def _prepare_keyboard(
        self,
        approver: ApprovalApprover,
        request: ApprovalRequest,
        bot: TelegramBot,
        env: Environment | None = None,
    ) -> dict[str, Any]:
        markup = super()._prepare_keyboard(approver, request, bot, env=env)
        if not self._awaits_bank_line(request):
            return markup
        approve = f"ar:a:{approver.id}"
        return kb.keyboard(
            *(
                [button for button in row if button.get("callback_data") != approve]
                for row in markup["inline_keyboard"]
            )
        )

    @api.model
    def _awaits_bank_line(self, request: ApprovalRequest) -> bool:
        return request.has_bsl == "required" and not request.bank_statement_line_id
