from odoo import models


class IrDefault(models.Model):
    _name = "ir.default"
    _inherit = ["mixin.studio", "ir.default"]
