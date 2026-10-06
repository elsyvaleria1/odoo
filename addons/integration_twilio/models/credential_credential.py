import logging

from odoo import models

from odoo.addons.integration.tools import CommError

_logger = logging.getLogger(__name__)


class CredentialCredential(models.Model):
    _inherit = "credential.credential"

    def _probe_health(self):
        # the hourly probe proves the credential; a Twilio account's status
        # and balance, which stop SMS and calls before any call fails, are read
        # on the same round
        result = super()._probe_health()
        if not result.get("success") or self.endpoint_id.code != "twilio":
            return result
        configs = self.env["integration.twilio.config"].search(
            [("credential_id", "=", self.id)]
        )
        for config in configs:
            try:
                config._refresh_account_state()
            except CommError as error:
                _logger.warning(
                    "Twilio: %s's account state was not read: %s",
                    config.company_id.display_name,
                    error,
                )
        return result
