from odoo import api, models


class PosOrder(models.Model):
    _inherit = "restaurant.table"

    @api.model
    def _load_pos_preparation_data_fields(self):
        return ["id"]
