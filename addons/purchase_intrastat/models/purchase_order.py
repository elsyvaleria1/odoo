from odoo import models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _prepare_invoice_vals(self):
        res = super()._prepare_invoice_vals()
        if (
            self.partner_id.country_id
            and "INTRASTAT" in self.partner_id.country_id.country_group_codes
        ):
            res["intrastat_country_id"] = self.partner_id.country_id.id
        return res
