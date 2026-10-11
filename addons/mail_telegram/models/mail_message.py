from odoo import fields, models


class MailMessage(models.Model):
    _inherit = "mail.message"

    telegram_message_ids = fields.One2many(
        comodel_name="telegram.message",
        inverse_name="mail_message_id",
        classification="mail_telegram.delivery",
        groups="base.group_system",
    )

    def _telegram_tracking_lines(self):
        self.check_singleton()
        lines = []
        for value in self.tracking_value_ids._tracking_value_format():
            old, new = value["oldValue"], value["newValue"]
            field = value["fieldInfo"]["changedField"]
            lines.append(f"{field}: {old or '—'} → {new or '—'}")
        return lines
