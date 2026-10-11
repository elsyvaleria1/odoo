import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.integration_microsoft.models.integration_service import (
    LEGACY_CALLBACK_PATH,
)

_logger = logging.getLogger(__name__)

CLIENT_ID_KEY = "microsoft_calendar_client_id"
CLIENT_SECRET_KEY = "microsoft_calendar_client_secret"
ENDPOINT_KEYS = {
    "oauth_auth_endpoint": "integration_microsoft.auth_endpoint",
    "oauth_token_endpoint": "integration_microsoft.token_endpoint",
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    service = env.ref("integration_microsoft.service_microsoft")
    ICP = env["ir.config_parameter"]
    Credential = env["credential.credential"]
    values = {"oauth_redirect_path": LEGACY_CALLBACK_PATH}
    for field, key in ENDPOINT_KEYS.items():
        if endpoint := ICP.get_param(key):
            values[field] = endpoint
    service.write(values)
    client_id = ICP.get_param(CLIENT_ID_KEY)
    client_secret = Credential._get_system_secret(CLIENT_SECRET_KEY)
    if client_id and client_secret:
        service._set_oauth_client(client_id, client_secret, company=False)
    elif client_id or client_secret:
        _logger.warning(
            "Microsoft OAuth client left unconfigured: client ID %r had no "
            "secret, or a secret had no client ID",
            client_id,
        )
    ICP.search(
        [
            (
                "key",
                "in",
                [CLIENT_ID_KEY, "microsoft_redirect_uri", *ENDPOINT_KEYS.values()],
            )
        ]
    ).unlink()
    Credential._set_system_secret(CLIENT_SECRET_KEY, False)
