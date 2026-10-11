from odoo import models


class WizardWhatsappMessageSend(models.TransientModel):
    _inherit = "wizard.whatsapp.message.send"
    _description = "Send WhatsApp Wizard"

    def _send_whatsapp_template(self, force_send_by_cron=False):
        res = super()._send_whatsapp_template(force_send_by_cron=force_send_by_cron)
        if len(res) and self.res_model == "pos.order":
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("WhatsApp messages triggered successfully!"),
                    "type": "success",
                    "next": {
                        "type": "ir.actions.act_window_close"
                    },
                },
            }
        return res
