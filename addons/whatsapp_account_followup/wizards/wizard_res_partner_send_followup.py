from odoo import api, fields, models


class WizardResPartnerSendFollowup(models.TransientModel):
    _name = "wizard.res.partner.send.followup"
    _inherit = ["wizard.res.partner.send.followup", "wizard.whatsapp.message.send"]

    def _raise_no_template_error(self, res_model) -> None:
        return

    whatsapp = fields.Boolean()
    attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="WhatsApp attachment",
        index=True,
    )

    @api.depends("whatsapp")
    def _compute_show_send_button(self) -> None:
        super()._compute_show_send_button()
        for wizard in self:
            wizard.show_send_button = wizard.show_send_button or wizard.whatsapp

    @api.depends("partner_id")
    def _compute_number(self) -> None:
        for composer in self:
            composer.phone = composer.partner_id._get_followup_whatsapp_number()

    def _get_followup_request(self):
        return (
            super()
            ._get_followup_request()
            .with_channel("whatsapp", self.whatsapp)
            .with_extra(whatsapp_composer=self)
        )
