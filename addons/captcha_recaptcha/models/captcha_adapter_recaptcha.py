import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class CaptchaAdapterRecaptcha(models.AbstractModel):
    _name = "captcha.adapter.recaptcha"
    _inherit = "captcha.adapter"
    _description = "reCAPTCHA Captcha Adapter"

    @api.model
    def _site_key(self):
        return (
            self.env.registry.settings.get(
                self.env, "captcha_recaptcha.site_key", False
            )
            or None
        )

    @api.model
    def _secret(self):
        return self.env["credential.credential"]._get_system_secret(
            "captcha_recaptcha.secret_key"
        )

    @api.model
    def _has_secret(self):
        return self.env["credential.credential"]._has_system_secret(
            "captcha_recaptcha.secret_key"
        )

    @api.model
    def _post_verification(self, data):
        return self.env.ref(
            "captcha_recaptcha.service_recaptcha"
        )._shared_egress_request(
            "POST", "/recaptcha/api/siteverify", data=data, timeout=2, budgeted=False
        )

    @api.model
    def _verdict_of_success(self, ip_addr, result, action):
        if "score" not in result:
            _logger.warning(
                "reCAPTCHA verification for ip address %s returned no score; "
                "treating as a failure.",
                ip_addr,
            )
            return "bad_request"
        minimum = self.env.registry.settings.get_float(
            self.env, "captcha_recaptcha.min_score", 0.7
        )
        if result["score"] < minimum:
            _logger.warning(
                "reCAPTCHA verification for ip address %s failed with score %f.",
                ip_addr,
                result["score"],
            )
            return "is_bot"
        return super()._verdict_of_success(ip_addr, result, action)
