from odoo import models

FAILED = ("error", "bounced", "cancel")


class WhatsappMessage(models.Model):
    _inherit = "whatsapp.message"

    def write(self, vals):
        res = super().write(vals)
        if vals.get("state") in FAILED:
            # a question WhatsApp refused never reached its contact
            self.env["proof.challenge"]._with_proof_privilege().env[
                "proof.delivery"
            ].search(
                [
                    ("ref", "in", [str(message.id) for message in self]),
                    ("method_id.code", "=", "whatsapp_confirm"),
                    ("state", "=", "sent"),
                ]
            ).state = "failed"
        return res
