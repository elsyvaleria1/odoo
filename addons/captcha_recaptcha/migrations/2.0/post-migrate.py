import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import str2bool

_logger = logging.getLogger(__name__)

SETTINGS = {
    "recaptcha_public_key": "captcha_recaptcha.site_key",
    "recaptcha_min_score": "captcha_recaptcha.min_score",
}


def migrate(cr, version):
    """reCAPTCHA's keys take the captcha module's names. With no provider
    chosen, the first one with a site key and a secret checks the forms; a
    reCAPTCHA that was switched off leaves them to Turnstile when Turnstile is
    configured, under its old names or its new ones whichever migration ran
    first, and to none otherwise."""
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
    if site_key and not enabled and not ICP.get_param("captcha.provider"):
        turnstile = (
            ICP.get_param("cf.turnstile_site_key")
            or ICP.get_param("captcha_turnstile.site_key")
        ) and (
            Credential._has_system_secret("cf.turnstile_secret_key")
            or Credential._has_system_secret("captcha_turnstile.secret_key")
        )
        ICP.set_param("captcha.provider", "turnstile" if turnstile else "none")
        _logger.info("captcha: reCAPTCHA was switched off and stays off")
    ICP.search(
        [("key", "in", [*SETTINGS, "enable_recaptcha", "recaptcha_private_key"])]
    ).unlink()
