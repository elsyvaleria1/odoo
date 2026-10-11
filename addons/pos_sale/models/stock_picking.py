from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _create_move_from_pos_order_lines(self, lines):
        has_move_ids = "move_ids" in self.env["sale.order.line"]._fields
        lines_to_unreserve = self.env["pos.order.line"]
        for line in lines:
            if line.order_id.shipping_date:
                continue
            if has_move_ids and any(
                wh != line.order_id.config_id.warehouse_id
                for wh in line.sale_order_line_id.move_ids.location_id.warehouse_id
            ):
                continue
            lines_to_unreserve |= line
        if has_move_ids:
            lines_to_unreserve.sale_order_line_id.move_ids.filtered(
                lambda ml: ml.state not in ["cancel", "done"]
            )._unreserve()
        return super()._create_move_from_pos_order_lines(lines)
