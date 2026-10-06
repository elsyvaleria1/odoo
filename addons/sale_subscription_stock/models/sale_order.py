from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    display_recurring_stock_delivery_warning = fields.Boolean(
        compute="_compute_recurring_stock_products"
    )

    def _upsell_context(self):
        context = super()._upsell_context()
        context["skip_procurement"] = True
        return context

    @api.depends("state", "is_subscription", "start_date", "next_invoice_date")
    def _compute_recurring_stock_products(self) -> None:
        self.display_recurring_stock_delivery_warning = False

    def _handle_post_invoice_hook_exception(self) -> None:
        super()._handle_post_invoice_hook_exception()
        for order in self:
            if not order.line_ids._filtered_stock_subscription_lines()._get_lines_to_launch_stock_rule():
                continue
            post_invoice_fail_summary = self.env._("Delivery creation failed")
            post_invoice_fail_note = self.env._(
                "A system error prevented the automatic creation of delivery orders for this subscription."
                " To ensure your delivery is processed, please trigger it manually by using the"
                ' "Subscription: Generate delivery" action.'
            )
            order.activity_schedule(
                activity_type_id=self.env.ref("mail.mail_activity_data_warning").id,
                summary=post_invoice_fail_summary,
                note=post_invoice_fail_note,
                user_id=order.subscription_id.user_id.id,
            )
