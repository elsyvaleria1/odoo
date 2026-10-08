from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    captcha_provider = fields.Selection(
        selection="_selection_captcha_provider",
        string="Captcha Provider",
        config_parameter="captcha.provider",
        help="Which installed provider checks that a person sent a public form; "
        "none checks nothing.",
    )

    @api.model
    def _selection_captcha_provider(self) -> list[tuple[str, str]]:
        return [
            (code, provider.label)
            for code, provider in self.env["ir.http"]._captcha_providers().items()
        ]
