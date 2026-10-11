from odoo import api, models


class ResCountryState(models.Model):
    _name = "res.country.state"
    _inherit = ["res.country.state", "mixin.pos.load"]

    @api.model
    def _load_pos_self_data_domain(self, data, config):
        return []
