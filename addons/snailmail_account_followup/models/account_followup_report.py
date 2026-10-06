from odoo import api, models
from odoo.exceptions import UserError


class AccountFollowupReport(models.AbstractModel):
    _inherit = "account.followup.report"

    @api.model
    def _send_snailmail(self, request) -> None:
        """
        Send by post the followup to the customer's followup contacts
        """
        partner = request.partner
        contact = partner._get_followup_contact() or partner
        letter = self.env["snailmail.letter"].create(
            {
                "state": "pending",
                "partner_id": contact.id,
                "model": "res.partner",
                "res_id": partner.id,
                "user_id": self.env.user.id,
                "report_template": self.env.ref(
                    "account_followup.action_report_followup"
                ).id,
                "company_id": contact.company_id.id or self.env.company.id,
            }
        )

        # Allow snailmail_letter to generate the attachment using the followup request
        letter.with_context(followup_request=request)._snailmail_print()
        if not self.env["snailmail.letter"]._is_valid_address(letter):
            raise UserError(
                self.env._(
                    "You are trying to send a letter by post, but no follow-up contact has any address set"
                )
            )
