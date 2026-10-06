from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    whatsapp_enabled = fields.Boolean(
        string="WhatsApp Enabled",
        default=False,
    )
    receipt_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="Receipt template",
        domain=[("model", "=", "pos.order"), ("status", "=", "approved")],
    )
    invoice_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="Invoice template",
        domain=[("model", "=", "account.move"), ("status", "=", "approved")],
    )
