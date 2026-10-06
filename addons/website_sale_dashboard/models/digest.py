from odoo import models


class DigestDigest(models.Model):
    _inherit = "digest.digest"

    def _get_kpi_actions(self, company, user):
        res = super()._get_kpi_actions(company, user)
        res["kpi_website_sale_total"] = (
            "website_sale_dashboard.sale_dashboard?menu_id=%s"
            % self.env.ref("website.menu_website_configuration").id
        )
        return res
