from odoo import models


class HrApplicant(models.Model):
    _inherit = "hr.applicant"

    def _prepare_offer_vals(self):
        self.check_singleton()
        vals = super()._prepare_offer_vals()
        contract_template = self._get_contract_template()
        if contract_template:
            monthly_wage = contract_template.sudo()._get_gross_from_employer_costs(
                vals["final_yearly_costs"]
            )
            vals.update({"monthly_wage": monthly_wage})
        return vals
