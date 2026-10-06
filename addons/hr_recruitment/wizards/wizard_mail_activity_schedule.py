from odoo import models


class WizardMailActivitySchedule(models.TransientModel):
    _inherit = "wizard.mail.activity.schedule"

    def _compute_plan_department_filterable(self) -> None:
        super()._compute_plan_department_filterable()
        for wizard in self:
            if not wizard.plan_department_filterable:
                wizard.plan_department_filterable = wizard.res_model == "hr.applicant"
