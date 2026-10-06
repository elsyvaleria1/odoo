import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.integration_google.models.integration_service import (
    LEGACY_CALLBACK_PATH,
)

_logger = logging.getLogger(__name__)

CLIENT_ID_KEY = "google_calendar_client_id"
CLIENT_SECRET_KEY = "google_calendar_client_secret"


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    service = env.ref("integration_google.service_google")
    # Google consoles list the old callback: a new one would refuse every
    # authorization until an admin adds it there
    service.oauth_redirect_path = LEGACY_CALLBACK_PATH
    ICP = env["ir.config_parameter"]
    Credential = env["credential.credential"]
    client_id = ICP.get_param(CLIENT_ID_KEY)
    client_secret = Credential._get_system_secret(CLIENT_SECRET_KEY)
    if client_id and client_secret:
        # one global parameter served every company: so does its client
        service._set_oauth_client(client_id, client_secret, company=False)
    elif client_id or client_secret:
        # it never authorized anything: report what is dropped, to enter again
        _logger.warning(
            "Google OAuth client left unconfigured: client ID %r had no secret, "
            "or a secret had no client ID",
            client_id,
        )
    ICP.search([("key", "=", CLIENT_ID_KEY)]).unlink()
    Credential._set_system_secret(CLIENT_SECRET_KEY, False)
