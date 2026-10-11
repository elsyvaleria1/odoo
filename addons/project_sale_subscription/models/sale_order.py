from odoo import models

from odoo.addons.sale_subscription.models.sale_order import SUBSCRIPTION_PROGRESS_STATE


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _can_generate_service(self) -> bool:
        self.check_singleton()
        return (
            not self.subscription_state
            or self.subscription_state in SUBSCRIPTION_PROGRESS_STATE
        )

    def _set_deferred_end_date_from_template(self) -> None:
        self.check_singleton()
        super()._set_deferred_end_date_from_template()
        if self.end_date:
            self.line_ids.task_id.recurrence_id.sudo().write(
                {
                    "repeat_type": "until",
                    "repeat_until": self.end_date,
                }
            )
        else:
            self.line_ids.task_id.recurrence_id.sudo().write(
                {
                    "repeat_type": "forever",
                }
            )

    def set_close(self, close_reason_id=None, renew=False):
        self._unlink_tasks_recurrence()
        return super().set_close(close_reason_id, renew)

    def _action_cancel(self):
        self._unlink_tasks_recurrence()
        return super()._action_cancel()

    def _unlink_tasks_recurrence(self) -> None:
        self.filtered(
            "is_subscription"
        ).line_ids.sudo().task_id.action_unlink_recurrence()

    def _prepare_upsell_renew_order_values(self, subscription_state):
        res = super()._prepare_upsell_renew_order_values(subscription_state)
        subscription = self.with_company(self.company_id)
        return {
            **res,
            "project_id": subscription.project_id.id,
        }
