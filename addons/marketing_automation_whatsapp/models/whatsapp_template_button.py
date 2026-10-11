from odoo import fields, models


class WhatsappTemplateButton(models.Model):
    _inherit = "whatsapp.template.button"

    url_type = fields.Selection(
        selection_add=[
            ("tracked", "Tracked"),
        ]
    )

    def _filter_dynamic_buttons(self):
        super_urls = super()._filter_dynamic_buttons()
        tracked_urls = self.filtered(
            lambda button: button.button_type == "url" and button.url_type == "tracked"
        )
        return super_urls + tracked_urls
