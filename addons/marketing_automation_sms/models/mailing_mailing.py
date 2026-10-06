from odoo import models


class MailingMailing(models.Model):
    _inherit = "mailing.mailing"

    def _send_sms_get_composer_values(self, res_ids):
        composer_values = super()._send_sms_get_composer_values(res_ids)
        if self.env.context.get("default_marketing_activity_id"):
            composer_values["marketing_activity_id"] = self.env.context[
                "default_marketing_activity_id"
            ]
        return composer_values
