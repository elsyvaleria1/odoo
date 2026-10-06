from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _get_followup_whatsapp_number(self):
        followup_contacts = (self._get_followup_contact() | self).filtered(
            lambda partner: partner.phone_ids
        )
        return (
            followup_contacts[0]._phone_get_number().number if followup_contacts else ""
        )

    def _send_followup(self, request) -> None:
        # EXTENDS account_followup
        super()._send_followup(request)
        if request.is_channel_enabled("whatsapp", request.followup_line.send_whatsapp):
            self._send_followup_whatsapp(request)

    def _send_followup_whatsapp(self, request) -> None:
        """
        Send a follow-up report by WhatsApp to customers in self
        """
        report = self.env["account.followup.report"]
        for partner in self:
            report._send_whatsapp(
                partner=partner,
                whatsapp_composer=request.extra.get("whatsapp_composer"),
                followup_line=request.followup_line,
            )
