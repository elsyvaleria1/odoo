from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    wa_sale_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        domain=[("model", "=", "sale.order"), ("status", "=", "approved")],
    )
