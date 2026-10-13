from odoo import api, models
from odoo.tools import iap


class IapEnrichApi(models.AbstractModel):
    _name = "iap.enrich.api"
    _description = "IAP Lead Enrichment API"
    _DEFAULT_ENDPOINT = "https://iap-services.odoo.com"

    @api.model
    def _contact_iap(self, local_endpoint, params):
        account = self.env["iap.account"].acquire_account("reveal")
        dbuuid = self.env.registry.settings.get(self.env, "database.uuid", False)
        params["account_token"] = account.sudo().account_token
        params["dbuuid"] = dbuuid
        base_url = self.env.registry.settings.get(
            self.env, "enrich.endpoint", self._DEFAULT_ENDPOINT
        )
        return iap.jsonrpc(
            base_url + local_endpoint, params=params, timeout=300, env=self.env
        )

    @api.model
    def _request_enrich(self, lead_emails):
        params = {
            "domains": lead_emails,
        }
        return self._contact_iap("/iap/clearbit/1/lead_enrichment_email", params=params)
