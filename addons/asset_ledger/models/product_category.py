from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    log_type = fields.Selection(
        selection_add=[
            ("fuel", "Fuel"),
            ("highway", "Highway"),
            ("operator", "Operator Assignment"),
        ],
        ondelete={
            "fuel": "set null",
            "highway": "set null",
            "operator": "set null",
        },
    )
