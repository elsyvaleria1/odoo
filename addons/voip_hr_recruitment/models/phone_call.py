from odoo import fields, models


class PhoneCall(models.Model):
    _inherit = "phone.call"

    application_count = fields.Integer(
        related="partner_id.applicant_ids.application_count",
        related_sudo=False,
        groups="hr_recruitment.group_hr_recruitment_interviewer",
    )

    def voip_action_view_applications(self):
        return (
            self.partner_id.applicant_ids[0].action_view_applications()
            if self.partner_id.applicant_ids
            else False
        )
