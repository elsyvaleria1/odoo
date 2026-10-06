from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    lot_properties_definition = fields.PropertiesDefinition(string="Lot Properties")
    trace_ids = fields.One2many(
        comodel_name="product.trace",
        inverse_name="product_id",
        string="Lot/Serial Numbers",
    )

    def get_next_lot_preview(self):
        self.check_singleton()
        sequence = self.lot_sequence_id
        return sequence.preview_next() if sequence else False
