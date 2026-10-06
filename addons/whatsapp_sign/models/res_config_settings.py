from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    send_request_wa_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="Request template",
        default=lambda self: self.env.ref(
            "whatsapp_sign.sign_request_whatsapp_template", raise_if_not_found=False
        ),
        config_parameter="whatsapp_sign.whatsapp_template_id",
        domain=[("model", "=", "sign.request.item"), ("status", "=", "approved")],
        help="Choose an approved WhatsApp template to send signature requests",
    )

    request_completion_wa_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="Completed template",
        default=lambda self: self.env.ref(
            "whatsapp_sign.sign_request_completion_whatsapp_template",
            raise_if_not_found=False,
        ),
        config_parameter="whatsapp_sign.whatsapp_completion_template_id",
        domain=[("model", "=", "sign.request.item"), ("status", "=", "approved")],
        help="Choose an approved WhatsApp template to send the signature request completion",
    )

    request_refusal_wa_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="Refusal template",
        default=lambda self: self.env.ref(
            "whatsapp_sign.sign_request_refusal_whatsapp_template",
            raise_if_not_found=False,
        ),
        config_parameter="whatsapp_sign.whatsapp_refusal_template_id",
        domain=[("model", "=", "sign.request.item"), ("status", "=", "approved")],
        help="Choose an approved WhatsApp template to send the signature request refusal",
    )
