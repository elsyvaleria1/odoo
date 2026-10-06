from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    module_pos_iot = fields.Boolean(
        related="is_posbox",
        string="IoT Box",
    )
    module_pos_urban_piper = fields.Boolean(string="Is an Urbanpiper")

    @api.model
    def _load_pos_preparation_data_domain(self, data):
        config_ids = data["pos.prep.display"][0]["pos_config_ids"]
        return [("id", "in", config_ids)] if len(config_ids) else []

    @api.model
    def _load_pos_preparation_data_fields(self):
        res = super()._load_pos_preparation_data_fields()
        return res + ["use_presets"]
