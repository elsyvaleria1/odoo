from odoo import models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _prepare_offer_context(self):
        self.check_singleton()
        vals = super()._prepare_offer_context()
        monthly_wage = self.version_id._get_gross_from_employer_costs(
            self.version_id.final_yearly_costs
        )
        vals.update({"default_monthly_wage": monthly_wage})
        return vals
