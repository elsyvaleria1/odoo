from odoo import api, models


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.depends("sale_line_id.order_id.amazon_channel")
    def _compute_reference(self) -> None:
        super()._compute_reference()
        for record in self:
            if (
                record.sale_line_id
                and record.sale_line_id.order_id.amazon_channel == "fba"
            ):
                record.reference = self.env._("Amazon move: %s", record.reference)
