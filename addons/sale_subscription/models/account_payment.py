from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _link_matched_invoices(self, invoices_per_payment) -> None:
        super()._link_matched_invoices(invoices_per_payment)
        self.env["account.move"].union(
            *invoices_per_payment
        )._reopen_subscriptions_of_paid_invoices()
