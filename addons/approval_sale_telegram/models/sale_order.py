from typing import TYPE_CHECKING

from odoo import models

if TYPE_CHECKING:
    from odoo.addons.approval.models.res_users import ResUsers


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _on_approval_approved(self) -> None:
        super()._on_approval_approved()
        if self.state == "draft":
            self.env["telegram.sale.confirm.notifier"]._notify_ready_to_confirm(self)

    def _get_telegram_confirm_users(self) -> ResUsers:
        self.check_singleton()
        return self.approval_request_id.category_id.telegram_confirm_user_ids
