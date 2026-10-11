from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    integration_log_retention_days = fields.Integer(
        string="Request Log Retention (days)",
        default=90,
        config_parameter="integration.log_retention_days",
        help="How long to keep request logs before automatic deletion",
    )
    integration_max_cache_entries = fields.Integer(
        string="API Max Cache Entries",
        default=10000,
        config_parameter="integration.max_cache_entries",
        help="Maximum number of cached API responses to keep",
    )

    @api.model
    def _oauth_client_settings(self) -> dict[str, str]:
        return {}

    @api.model
    def get_values(self):
        res = super().get_values()
        for prefix, xmlid in self._oauth_client_settings().items():
            client_id = self.env.ref(xmlid)._oauth_client_id()
            res[f"{prefix}_client_id"] = client_id or False
        return res

    def set_values(self):
        super().set_values()
        for prefix, xmlid in self._oauth_client_settings().items():
            service = self.env.ref(xmlid)
            client_id = self[f"{prefix}_client_id"] or ""
            client_secret = self[f"{prefix}_client_secret"]
            if client_secret or client_id != service._oauth_client_id():
                service._set_oauth_client(client_id, client_secret)
