from odoo import Command, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _add_payment_link(self, line_vals):
        super()._add_payment_link(line_vals)
        line_vals["payment_lines_ids"] = [Command.set(self.ids)]
