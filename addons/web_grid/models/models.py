from odoo import api, models


class Base(models.AbstractModel):
    _inherit = "base"

    @api.model
    def grid_update_cell(self, domain, measure_field_name, value):
        raise NotImplementedError

    @api.model
    def grid_unavailability(self, start_date, end_date, groupby="", res_ids=()):
        return {}
