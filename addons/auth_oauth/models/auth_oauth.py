from odoo import fields, models


class AuthOauthProvider(models.Model):

    _name = "auth.oauth.provider"
    _description = "OAuth2 provider"
    _order = "sequence, name"

    name = fields.Char(
        string="Provider name",
        required=True,
    )
    client_id = fields.Char(string="Client ID")
    auth_endpoint = fields.Char(
        string="Authorization URL",
        required=True,
    )
    scope = fields.Char(
        default="openid profile email"
    )
    validation_endpoint = fields.Char(
        string="UserInfo URL",
        required=True,
    )
    data_endpoint = fields.Char()
    enabled = fields.Boolean(string="Allowed")
    css_class = fields.Char(
        string="CSS class",
        default="fa-solid fa-right-to-bracket text-primary",
    )
    body = fields.Char(
        string="Login button label",
        translate=True,
        required=True,
        help="Link text in Login Dialog",
    )
    sequence = fields.Integer(default=10)
