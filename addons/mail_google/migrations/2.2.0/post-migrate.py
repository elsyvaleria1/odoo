from odoo import SUPERUSER_ID, api

from odoo.addons.mail_google.models.integration_service import LEGACY_CALLBACK_PATH
from odoo.addons.mail_google.models.mixin_mail_google import GMAIL
from odoo.addons.mail_oauth2.migration import adopt_servers, move_client


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    service = env.ref("integration_google.service_google")
    client = move_client(
        env, service, "google_gmail_client_id", "google_gmail_client_secret", "Gmail"
    )
    adopt_servers(
        env,
        "gmail",
        service,
        lambda record: GMAIL.resolve(GMAIL.scope, record),
        LEGACY_CALLBACK_PATH,
        "google_gmail_access_token_expiration",
        client,
    )
    env["ir.config_parameter"].search(
        [("key", "=", "mail.server.gmail.iap.endpoint")]
    ).unlink()
