from odoo import api, models

from odoo.addons.captcha.provider import CaptchaProvider

RECAPTCHA = CaptchaProvider(
    code="recaptcha", label="reCAPTCHA", adapter="captcha.adapter.recaptcha"
)


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def _captcha_providers(self) -> dict:
        return {**super()._captcha_providers(), "recaptcha": RECAPTCHA}
