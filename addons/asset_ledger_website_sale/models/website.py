from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    whatsapp_sales_number = fields.Char(
        string="WhatsApp Sales Number",
        help="Destination number in E.164 format without '+' or symbols "
        "(e.g. 521XXXXXXXXXX). Used by the WhatsApp quote button on catalog "
        "products flagged as quote-only.",
    )
