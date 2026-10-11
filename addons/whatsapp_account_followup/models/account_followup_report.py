from odoo import api, models
from odoo.exceptions import UserError, ValidationError


class AccountFollowupReport(models.AbstractModel):
    _inherit = "account.followup.report"

    @api.model
    def _send_whatsapp(self, partner, whatsapp_composer=None, followup_line=None):
        if not whatsapp_composer:
            if not followup_line:
                raise ValidationError(
                    self.env._(
                        "whatsapp_composer and followup_line cannot both be None"
                    )
                )

            whatsapp_composer = self.env["wizard.whatsapp.message.send"].create(
                {
                    "res_ids": partner.ids,
                    "res_model": "res.partner",
                    "phone": partner._get_followup_whatsapp_number(),
                    "wa_template_id": followup_line.whatsapp_template_id.id,
                }
            )
        if not whatsapp_composer.phone:
            raise UserError(self.env._("A phone number is required to use WhatsApp"))
        if not whatsapp_composer.wa_template_id:
            raise UserError(self.env._("A template is required to use WhatsApp"))

        whatsapp_composer._send_whatsapp_template()
