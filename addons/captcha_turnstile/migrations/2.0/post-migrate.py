import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Turnstile's keys take the captcha module's names, and Turnstile becomes
    the provider when it was checking the forms and reCAPTCHA was not: one
    provider checks them now, where both used to run."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    ICP = env["ir.config_parameter"]
    Credential = env["credential.credential"]
    site_key = ICP.get_param("cf.turnstile_site_key")
    if site_key:
        ICP.set_param("captcha_turnstile.site_key", site_key)
    if secret := Credential._get_system_secret("cf.turnstile_secret_key"):
        Credential._set_system_secret("captcha_turnstile.secret_key", secret)
        Credential._set_system_secret("cf.turnstile_secret_key", False)
    if site_key:
        provider = ICP.get_param("captcha.provider")
        if not provider:
            ICP.set_param("captcha.provider", "turnstile")
            _logger.info("captcha: Turnstile checks the forms, as it did")
        elif provider != "turnstile":
            _logger.warning(
                "captcha: Turnstile and %s were both configured; %s alone checks "
                "the forms now, Turnstile can be chosen in the settings",
                provider,
                provider,
            )
    ICP.search([("key", "=", "cf.turnstile_site_key")]).unlink()
