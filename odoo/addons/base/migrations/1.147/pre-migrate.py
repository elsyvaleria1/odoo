from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    rename_module(cr, "google_recaptcha", "captcha_recaptcha")
    rename_module(cr, "website_cf_turnstile", "captcha_turnstile")
