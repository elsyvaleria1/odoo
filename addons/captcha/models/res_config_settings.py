from odoo import api, fields, models

from .ir_http import NO_PROVIDER


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    captcha_provider = fields.Selection(
        selection="_selection_captcha_provider",
        config_parameter="captcha.provider",
        help="Which installed provider checks that a person sent a public form. "
        "Left empty, the first one with a site key and a secret checks them; "
        "None checks nothing.",
    )

    @api.model
    def _selection_captcha_provider(self) -> list[tuple[str, str]]:
        return [
            (NO_PROVIDER, self.env._("None")),
            *(
                (code, provider.label)
                for code, provider in self.env["ir.http"]._captcha_providers().items()
            ),
        ]
