from odoo import api, models


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _get_model_names_to_load(self, config):
        data = super()._get_model_names_to_load(config)
        if self.config_id.module_pos_restaurant:
            data.remove("calendar.event")
            data += ["resource.resource", "calendar.event"]
        return data
