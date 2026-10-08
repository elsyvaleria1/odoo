import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import str2bool

_logger = logging.getLogger(__name__)

SETTINGS = {
    "recaptcha_public_key": "captcha_recaptcha.site_key",
    "recaptcha_min_score": "captcha_recaptcha.min_score",
}


def migrate(cr, version):
    """reCAPTCHA's keys take the captcha module's names, and reCAPTCHA becomes
    the provider when it was the one checking the forms."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    ICP = env["ir.config_parameter"]
    Credential = env["credential.credential"]
    site_key = ICP.get_param("recaptcha_public_key")
    enabled = str2bool(ICP.get_param("enable_recaptcha") or "True", default=True)
    for old, new in SETTINGS.items():
        if value := ICP.get_param(old):
            ICP.set_param(new, value)
    if secret := Credential._get_system_secret("recaptcha_private_key"):
        Credential._set_system_secret("captcha_recaptcha.secret_key", secret)
        Credential._set_system_secret("recaptcha_private_key", False)
    if site_key and enabled and not ICP.get_param("captcha.provider"):
        ICP.set_param("captcha.provider", "recaptcha")
        _logger.info("captcha: reCAPTCHA checks the forms, as it did")
    ICP.search(
        [("key", "in", [*SETTINGS, "enable_recaptcha", "recaptcha_private_key"])]
    ).unlink()
