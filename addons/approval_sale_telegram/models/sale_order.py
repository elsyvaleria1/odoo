from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _on_approval_approved(self) -> None:
        super()._on_approval_approved()
        # Auto-confirm on approval has already run inside super(): an order
        # that left draft there needs nobody to confirm it. The push is queued,
        # so Telegram is reached after commit and cannot abort the approval.
        if self.state == "draft":
            self.env["telegram.sale.confirm.notifier"]._notify_ready_to_confirm(self)

    def _get_telegram_confirm_users(self):
        self.check_singleton()
        return self.approval_request_id.category_id.telegram_confirm_user_ids
