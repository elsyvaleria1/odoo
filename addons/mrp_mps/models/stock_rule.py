from odoo import models


class StockRule(models.Model):
    _inherit = "stock.rule"

    def _get_domain_po(self, company_id, values, partner):
        domain = super()._get_domain_po(company_id, values, partner)
        if self.env.context.get("skip_lead_time") and values.get("date_planned"):
            domain += (("date_planned_mps", "=", values["date_planned"]),)
        return domain
