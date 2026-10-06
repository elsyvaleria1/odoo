from odoo import models

from odoo.addons.account_followup.models.followup_request import FollowupRequest


class SnailmailLetter(models.Model):
    _inherit = "snailmail.letter"

    def _generate_report_pdf(self, report):
        followup_report = self.env.ref(
            "account_followup.action_report_followup", raise_if_not_found=False
        )
        if not followup_report or report != followup_report:
            return super()._generate_report_pdf(report)
        partner = self.env["res.partner"].browse(self.res_id)
        request = self.env.context.get("followup_request") or FollowupRequest.build(
            partner
        )
        return partner.with_context(
            snailmail_layout=not self.cover
        )._get_followup_letter_pdf(request.replace(partner=partner))
