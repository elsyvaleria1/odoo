from odoo import api, models

from odoo.addons.telegram.tools import keyboard as kb


class TelegramApprovalNotifier(models.AbstractModel):
    _inherit = "telegram.approval.notifier"

    @api.model
    def _summary_review_lines(self, request, env):
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
    def _prepare_keyboard(self, approver, request, bot, env=None):
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
    def _awaits_bank_line(self, request) -> bool:
        return request.has_bsl == "required" and not request.bank_statement_line_id
