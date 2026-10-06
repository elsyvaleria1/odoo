from odoo import api, fields, models


class WizardWhatsappTemplatePreview(models.TransientModel):
    _name = "wizard.whatsapp.template.preview"
    _description = "Preview template"

    wa_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="Templates",
    )
    preview_whatsapp = fields.Html(
        string="Message Preview",
        compute="_compute_preview_whatsapp",
    )

    @api.depends("wa_template_id")
    def _compute_preview_whatsapp(self) -> None:
        for record in self:
            if record.wa_template_id:
                record.preview_whatsapp = self.env["ir.qweb"]._render(
                    "whatsapp.template_message_preview",
                    {
                        "body": self.wa_template_id._get_formatted_body(
                            demo_fallback=True
                        ),
                        "buttons": record.wa_template_id.button_ids,
                        "header_type": record.wa_template_id.header_type,
                        "footer_text": record.wa_template_id.footer_text,
                        "language_direction": "rtl"
                        if record.wa_template_id.lang_code in ("ar", "he", "fa", "ur")
                        else "ltr",
                    },
                )
            else:
                record.preview_whatsapp = None
