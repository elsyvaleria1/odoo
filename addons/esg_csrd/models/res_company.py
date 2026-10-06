from odoo import models


class ResCompany(models.Model):
    _inherit = "res.company"

    @property
    def ESG_REPORT_DEFAULT_COMPANY(self):
        esg_company_id = False
        try:
            esg_company_id = int(
                self.env.registry.settings.get(
                    self.env, "esg_csrd.esg_main_company", False
                )
            )
        except ValueError:
            return self.browse()
        return self.browse(esg_company_id) or self.env.company
