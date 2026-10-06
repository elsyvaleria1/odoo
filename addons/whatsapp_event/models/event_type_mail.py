from odoo import fields, models


class EventTypeMail(models.Model):
    _inherit = "event.type.mail"

    notification_type = fields.Selection(selection_add=[("whatsapp", "WhatsApp")])
    template_ref = fields.Reference(
        selection_add=[("whatsapp.template", "WhatsApp")],
        ondelete={"whatsapp.template": "cascade"},
    )

    def _compute_notification_type(self) -> None:
        super()._compute_notification_type()
        wa_schedulers = self.filtered(
            lambda scheduler: (
                scheduler.template_ref
                and scheduler.template_ref._name == "whatsapp.template"
            )
        )
        wa_schedulers.notification_type = "whatsapp"
