from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _domain_picking_id(self) -> list | None:
        # Add a domain on `picking_id` only if we come from a batch.
        batch_id = self.env.context.get("default_batch_id")
        if batch_id:
            return [
                ("state", "in", ["assigned", "confirmed", "waiting"]),
                ("batch_id", "=", batch_id),
            ]
        return None

    picking_id = fields.Many2one(domain=lambda self: self._domain_picking_id())

    def _get_fields_stock_barcode(self):
        return super()._get_fields_stock_barcode() + ["picking_id"]
