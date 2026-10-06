from odoo import fields, models
from odoo.tools import view_validation

view_validation.register_schema("map", "web_map/rng/map_view.rng")


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    type = fields.Selection(selection_add=[("map", "Map")])

    def _get_view_info(self):
        return {"map": {"icon": "fa-solid fa-location-dot"}} | super()._get_view_info()
