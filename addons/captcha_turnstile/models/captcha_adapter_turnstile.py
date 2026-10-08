from odoo import api, models


class CaptchaAdapterTurnstile(models.AbstractModel):
    _name = "captcha.adapter.turnstile"
    _inherit = "captcha.adapter"
    _description = "Cloudflare Turnstile Captcha Adapter"

    @api.model
    def _site_key(self):
        return (
            self.env.registry.settings.get(
                self.env, "captcha_turnstile.site_key", False
            )
            or None
        )

    @api.model
    def _secret(self):
        return self.env["credential.credential"]._get_system_secret(
            "captcha_turnstile.secret_key"
        )

    @api.model
    def _post_verification(self, data):
        return self.env.ref(
            "captcha_turnstile.service_turnstile"
        )._shared_egress_request(
            "POST", "/turnstile/v0/siteverify", data=data, timeout=3.05
        )
