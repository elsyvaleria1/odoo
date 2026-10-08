from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    captcha_turnstile_site_key = fields.Char(
        string="Site Key",
        config_parameter="captcha_turnstile.site_key",
    )
    captcha_turnstile_secret_key = fields.Char(
        string="Secret Key",
        classification="secret.credential",
        secret_parameter="captcha_turnstile.secret_key",
        groups="base.group_system",
    )
