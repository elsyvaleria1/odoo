from odoo import api, fields, models


class WizardResPartnerSendFollowup(models.TransientModel):
    _inherit = "wizard.res.partner.send.followup"

    snailmail = fields.Boolean()
    snailmail_cost = fields.Float(
        string="Stamps",
        compute="_compute_snailmail_cost",
        default=1,
        readonly=True,
    )

    @api.depends("snailmail")
    def _compute_show_send_button(self) -> None:
        super()._compute_show_send_button()
        for wizard in self:
            wizard.show_send_button = wizard.show_send_button or wizard.snailmail

    def _get_defaults_from_followup_line(self, followup_line):
        defaults = super()._get_defaults_from_followup_line(followup_line)
        defaults["print_letter"] = followup_line.send_letter
        return defaults

    @api.depends("partner_id")
    def _compute_snailmail_cost(self) -> None:
        for record in self:
            record.snailmail_cost = len(record.partner_id._get_followup_contact()) + 1

    def _get_followup_request(self):
        return super()._get_followup_request().with_channel("snailmail", self.snailmail)
