from odoo import SUPERUSER_ID, api

from odoo.addons.mail_oauth2.migration import refuse_without_client


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    has_client = env.ref("integration_microsoft.service_microsoft")._has_oauth_client(
        False
    ) or bool(
        env["ir.config_parameter"].get_param("microsoft_outlook_client_id")
        and env["credential.credential"]._get_system_secret(
            "microsoft_outlook_client_secret"
        )
    )
    refuse_without_client(env, "outlook", "Outlook", has_client)
