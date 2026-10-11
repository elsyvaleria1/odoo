import logging

from odoo import SUPERUSER_ID, api
from odoo.libs.web import urljoin

from odoo.addons.mail_microsoft.models.integration_service import (
    LEGACY_CALLBACK_PATH,
)
from odoo.addons.mail_microsoft.models.mixin_mail_microsoft import OUTLOOK
from odoo.addons.mail_oauth2.migration import adopt_servers, move_client

_logger = logging.getLogger(__name__)

COMMON_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/"
ENDPOINT_KEY = "mail_microsoft.endpoint"


def _carry_tenant(env, service) -> None:
    ICP = env["ir.config_parameter"]
    endpoint = ICP.get_param(ENDPOINT_KEY)
    ICP.search([("key", "=", ENDPOINT_KEY)]).unlink()
    if not endpoint or endpoint == COMMON_ENDPOINT:
        return
    authorize, token = urljoin(endpoint, "authorize"), urljoin(endpoint, "token")
    if service.oauth_token_endpoint == urljoin(COMMON_ENDPOINT, "token"):
        service.write({"oauth_auth_endpoint": authorize, "oauth_token_endpoint": token})
    elif service.oauth_token_endpoint != token:
        _logger.warning(
            "Outlook mail used the tenant endpoint %s, the calendar %s: one "
            "Microsoft service keeps the calendar's",
            endpoint,
            service.oauth_token_endpoint,
        )


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    service = env.ref("integration_microsoft.service_microsoft")
    _carry_tenant(env, service)
    client = move_client(
        env,
        service,
        "microsoft_outlook_client_id",
        "microsoft_outlook_client_secret",
        "Outlook",
    )
    adopt_servers(
        env,
        "outlook",
        service,
        lambda record: OUTLOOK.resolve(OUTLOOK.scope, record),
        LEGACY_CALLBACK_PATH,
        "microsoft_outlook_access_token_expiration",
        client,
    )
    env["ir.config_parameter"].search(
        [("key", "=", "mail.server.outlook.iap.endpoint")]
    ).unlink()
