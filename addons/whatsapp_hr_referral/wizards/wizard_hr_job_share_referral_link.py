from odoo import fields, models


class HrReferralLink(models.TransientModel):
    _inherit = "wizard.hr.job.share.referral.link"

    recipient = fields.Char()

    def _get_fields_whatsapp_safe(self) -> set:
        return {"job_id.name", "job_id.company_id.name", "url", "recipient"}
