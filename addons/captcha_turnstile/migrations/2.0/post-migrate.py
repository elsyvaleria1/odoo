import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import str2bool

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Turnstile's keys take the captcha module's names. One provider checks
    the forms now, where both used to run: with none chosen, reCAPTCHA when it
    is configured too."""
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
    # reCAPTCHA's keys under their old names or their new ones, whichever
    # migration ran first
    recaptcha = (
        (
            ICP.get_param("recaptcha_public_key")
            or ICP.get_param("captcha_recaptcha.site_key")
        )
        and (
            Credential._has_system_secret("recaptcha_private_key")
            or Credential._has_system_secret("captcha_recaptcha.secret_key")
        )
        and str2bool(ICP.get_param("enable_recaptcha") or "True", default=True)
    )
    provider = ICP.get_param("captcha.provider")
    if site_key and (
        provider not in (False, "", "turnstile", "none") or (not provider and recaptcha)
    ):
        _logger.warning(
            "captcha: Turnstile and another provider were both configured; the "
            "other alone checks the forms now, Turnstile can be chosen in the "
            "settings"
        )
    ICP.search([("key", "=", "cf.turnstile_site_key")]).unlink()
