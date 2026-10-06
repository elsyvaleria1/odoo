from odoo import models


class WizardHrApplicantRefuse(models.TransientModel):
    _inherit = "wizard.hr.applicant.refuse"

    def action_refuse_reason_apply(self) -> dict:
        for applicant in self.applicant_ids:
            if applicant.ref_user_id:
                applicant._send_notification(
                    body=self.env._(
                        "Sorry, your referral %s has been refused in the recruitment process.",
                        applicant.partner_name,
                    ),
                    action_value="hr_referral.action_hr_refused_applicant_employee_referral",
                )
        self.applicant_ids.write({"referral_state": "closed"})
        return super().action_refuse_reason_apply()
