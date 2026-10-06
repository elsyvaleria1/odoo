from odoo import api, models


class ProductAttribute(models.Model):
    _name = "product.attribute"
    _inherit = ["product.attribute", "mixin.pos.load"]

    @api.model
    def _load_pos_preparation_data_fields(self):
        return ["name"]
