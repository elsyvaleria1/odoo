from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"
    _CREDENTIAL_FIELDS = {
        "pos_urbanpiper_apikey": "pos_urbanpiper_apikey",
    }

    pos_urbanpiper_username = fields.Char(
        string="UrbanPiper Username",
        help="The username of the UrbanPiper api account.",
    )
    pos_urbanpiper_apikey = fields.Char(
        string="UrbanPiper API Key",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        help="The API key for accessing the UrbanPiper services.",
    )
