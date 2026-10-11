from odoo import api, models


class ResCountry(models.Model):
    _name = "res.country"
    _inherit = ["res.country", "mixin.pos.load"]

    @api.model
    def _load_pos_self_data_fields(self, config):
        fields = super()._load_pos_self_data_fields(config)
        return fields + ["state_ids"]

    @api.model
    def _load_pos_self_data_domain(self, data, config):
        return []
