from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    website_address_autocomplete_key = fields.Char(
        related="website_id.address_autocomplete_key",
        string="Website's Address Autocomplete Key",
        readonly=False,
    )
