from odoo import api, models


class MixinPosLoad(models.AbstractModel):
    _inherit = "mixin.pos.load"

    @api.model
    def _load_pos_preparation_data_domain(self, data):
        return False

    @api.model
    def _load_pos_preparation_data_fields(self):
        return []

    def _load_pos_preparation_data(self, data):
        domain = self._load_pos_preparation_data_domain(data)
        fields = self._load_pos_preparation_data_fields()
        return (
            self.search_read(domain, fields, load=False) if domain is not False else []
        )
