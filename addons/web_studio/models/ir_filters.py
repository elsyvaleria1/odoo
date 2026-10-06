from odoo import models


class IrFilters(models.Model):
    _name = "ir.filters"
    _inherit = ["mixin.studio", "ir.filters"]
