from odoo import api, models

from odoo.addons.captcha.provider import CaptchaProvider

TURNSTILE = CaptchaProvider(
    code="turnstile", label="Turnstile", adapter="captcha.adapter.turnstile"
)


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def _captcha_providers(self) -> dict:
        return {**super()._captcha_providers(), "turnstile": TURNSTILE}
