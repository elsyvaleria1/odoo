import datetime
import hashlib
import logging

from odoo import models

from odoo.addons.integration.tools import CommError
from odoo.addons.mail.tools.discuss import get_twilio_credentials

_logger = logging.getLogger(__name__)

_ICE_CACHE_TTL = datetime.timedelta(hours=1)
_company_ice_servers: dict[tuple, tuple[datetime.datetime, list]] = {}


class MailIceServer(models.Model):
    _inherit = "mail.ice.server"

    def _get_ice_servers(self) -> list:
        if all(
            get_twilio_credentials(self.env)
        ) or not self.env.registry.settings.get_bool(
            self.env, "mail.use_twilio_rtc_servers"
        ):
            return super()._get_ice_servers()
        config = self.env.company.integration_twilio_config_id
        account = config._get_held_secrets()
        if not account.get("username"):
            return super()._get_ice_servers()

        now = datetime.datetime.now(datetime.UTC)
        fingerprint = hashlib.sha256(
            f"{account['username']}:{account.get('password')}".encode()
        ).hexdigest()
        key = (self.env.cr.dbname, config.id, fingerprint)
        cached = _company_ice_servers.get(key)
        if cached and cached[0] > now:
            return cached[1]
        try:
            servers = (
                config._get_twilio_client().call("POST", "Tokens").get("ice_servers")
            )
        except CommError as error:
            _logger.warning(
                "Twilio: no TURN servers from the company account: %s", error
            )
            servers = None
        if not servers:
            return self._get_local_ice_servers()
        _company_ice_servers[key] = (now + _ICE_CACHE_TTL, servers)
        return servers
