from odoo import SUPERUSER_ID, api

from odoo.addons.mail_oauth2.migration import refuse_without_client


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    has_client = env.ref("integration_google.service_google")._has_oauth_client(
        False
    ) or bool(
        env["ir.config_parameter"].get_param("google_gmail_client_id")
        and env["credential.credential"]._get_system_secret(
            "google_gmail_client_secret"
        )
    )
    refuse_without_client(env, "gmail", "Gmail", has_client)
