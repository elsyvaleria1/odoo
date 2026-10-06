from odoo import api, models


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _get_model_names_to_load(self, config):
        data = super()._get_model_names_to_load(config)
        data += ["calendar.event"]
        return data
