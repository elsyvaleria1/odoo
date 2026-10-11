from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _send_followup_snailmail(self, request) -> None:
        report = self.env["account.followup.report"]
        for record in self:
            report._send_snailmail(request.replace(partner=record))

    def _send_followup(self, request) -> None:
        super()._send_followup(request)
        if request.is_channel_enabled("snailmail", request.followup_line.send_letter):
            self._send_followup_snailmail(request)

    def _followup_needs_documents(self, request):
        return super()._followup_needs_documents(request) or request.is_channel_enabled(
            "snailmail", request.followup_line.send_letter
        )

    def _has_missing_followup_info(self) -> bool:
        res = super()._has_missing_followup_info()
        contact = self._get_followup_contact() or self
        if self.followup_line_id.send_letter and not self.env[
            "snailmail.letter"
        ]._is_valid_address(contact):
            return True
        return bool(res)
