from odoo import fields, models
from odoo.tools import view_validation

view_validation.register_schema("grid", "web_grid/rng/grid_view.rng")


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    type = fields.Selection(selection_add=[("grid", "Grid")])

    def _get_view_info(self):
        return {"grid": {"icon": "fa-solid fa-th"}} | super()._get_view_info()
