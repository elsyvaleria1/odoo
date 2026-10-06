from odoo import fields, models


class ResUsersSettings(models.Model):
    _inherit = "res.users.settings"

    onsip_auth_username = fields.Char(string="OnSIP Auth Username")
