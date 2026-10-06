from odoo import api, fields, models
from odoo.exceptions import UserError


class WizardSignRequestSend(models.TransientModel):
    _inherit = "wizard.sign.request.send"

    is_whatsapp_feature_enabled = fields.Boolean(
        compute="_compute_is_whatsapp_feature_enabled"
    )

    @api.depends("template_id")
    def _compute_is_whatsapp_feature_enabled(self) -> None:
        """
        Checks if all required WhatsApp templates are configured and approved.
        """
        self.is_whatsapp_feature_enabled = self.env[
            "sign.request.item"
        ]._check_whatsapp_template_exists(check_if_approved=True)

    def send_via_whatsapp(self):
        self.check_singleton()
        self._check_whatsapp_requirements()
        request = self.with_context(send_channel="whatsapp").create_request()
        return self._create_log_and_close(request)

    def _check_whatsapp_requirements(self) -> None:
        signers = self.signer_ids.mapped("partner_id")
        if any(not signer.phone_ids for signer in signers):
            raise UserError(
                self.env._(
                    "All signers must have a phone number to send messages via WhatsApp."
                )
            )
