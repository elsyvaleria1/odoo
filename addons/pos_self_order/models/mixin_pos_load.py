from odoo import api, models


class MixinPosLoad(models.AbstractModel):
    _inherit = "mixin.pos.load"

    @api.model
    def _load_pos_self_data_search_read(self, data, config):
        if not config:
            raise ValueError("config must be provided to search for PoS data.")

        domain = self._load_pos_self_data_domain(data, config)
        if domain is False:
            return []

        records = self.search(domain)
        return self._load_pos_self_data_read(records, config)

    @api.model
    def _load_pos_self_data_domain(self, data, config):
        return self._load_pos_data_domain(data, config)

    @api.model
    def _load_pos_self_data_read(self, records, config):
        if not config:
            raise ValueError("config must be provided to read PoS data.")

        fields = self._load_pos_self_data_fields(config)
        records = records.read(fields, load=False)
        return records or []

    @api.model
    def _load_pos_self_data_fields(self, config):
        return self._load_pos_data_fields(config)
