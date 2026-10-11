from odoo import models
from odoo.http import request


class IntegrationReceiver(models.Model):
    _inherit = "integration.receiver"

    def _inbound_auth_mode(self, parameter_key=None):
        if (
            self.res_model == "iot.box"
            and request
            and "Authorization" not in request.httprequest.headers
        ):
            return self.AUTH_MODE_AUDIT
        return super()._inbound_auth_mode(parameter_key)
