from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    captcha_recaptcha_site_key = fields.Char(
        string="Site Key",
        config_parameter="captcha_recaptcha.site_key",
    )
    captcha_recaptcha_secret_key = fields.Char(
        string="Secret Key",
        classification="secret.credential",
        secret_parameter="captcha_recaptcha.secret_key",
        groups="base.group_system",
    )
    captcha_recaptcha_min_score = fields.Float(
        string="Minimum score",
        default=0.7,
        config_parameter="captcha_recaptcha.min_score",
        help="By default, should be one of 0.1, 0.3, 0.7, 0.9.\n1.0 is very likely a good interaction, 0.0 is very likely a bot",
    )
