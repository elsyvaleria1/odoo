from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _invoice_paid_hook(self):
        res = super()._invoice_paid_hook()
        self.mapped("line_ids.sale_line_ids")._update_event_booths(set_paid=True)
        return res
