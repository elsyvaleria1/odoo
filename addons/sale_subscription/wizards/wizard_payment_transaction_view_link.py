from odoo import api, models


class WizardPaymentTransactionViewLink(models.TransientModel):
    _inherit = "wizard.payment.transaction.view.link"

    @api.depends("res_model", "res_id")
    def _compute_warning_message(self) -> None:
        subscription_wizard = self.env["wizard.payment.transaction.view.link"]
        for wizard in self:
            if wizard.res_model != "sale.order":
                continue
            order = self.env["sale.order"].browse(wizard.res_id)
            if not order.plan_id and (
                order.has_recurring_line and not order._subscription_is_one_time_sale()
            ):
                wizard.warning_message = self.env._(
                    "You cannot generate a payment link for a recurring product without a recurring plan."
                )
                subscription_wizard |= wizard
                continue
            if order.plan_id and not order.has_recurring_line:
                wizard.warning_message = self.env._(
                    "You cannot generate a payment link for a recurring plan without a recurring product."
                )
                subscription_wizard |= wizard
                continue
            if order.subscription_state == "5_renewed":
                wizard.warning_message = self.env._(
                    "You cannot generate a payment link for a renewed subscription"
                )
                subscription_wizard |= wizard
        super(
            WizardPaymentTransactionViewLink, self - subscription_wizard
        )._compute_warning_message()
