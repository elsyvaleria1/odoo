from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LazadaOrderItem(models.Model):
    _name = "lazada.order.item"
    _description = "Lazada Order Item"

    sale_order_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        index=True,
        required=True,
        ondelete="cascade",
    )
    stock_move_id = fields.Many2one(
        comodel_name="stock.move",
        index="btree_not_null",
        ondelete="cascade",
    )
    status = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("processing", "Processing"),
            ("delivered", "Delivered"),
            ("canceled", "Canceled"),
            ("manual", "Manual"),
        ],
        required=True,
        help="The status of the order item on Lazada:\n"
        "- Draft: The order item is in draft status by default.\n"
        "- Confirmed: The order item has been packed.\n"
        "- Processing: The order item is ready to ship.\n"
        "- Delivered: The order item has been shipped or delivered.\n"
        "- Canceled: The order item has been canceled.\n"
        "- Manual: The order item has to be processed manually on Lazada.",
    )
    order_item_extern_id = fields.Char(
        string="Lazada Order Item ID",
        required=True,
    )

    @api.constrains("sale_order_line_id", "stock_move_id")
    def _check_stock_move(self) -> None:
        for order_item in self:
            if (
                order_item.stock_move_id
                and order_item.stock_move_id.sale_line_id
                != order_item.sale_order_line_id
            ):
                raise ValidationError(
                    self.env._(
                        "The stock move must be related to the same sale order line as the Lazada"
                        " order item."
                    )
                )

    def write(self, vals):
        if "status" in vals:
            new_status = vals["status"]
            diff_order_items = self.filtered(
                lambda order_item: order_item.status != new_status
            )
            for order_item in diff_order_items:
                if new_status == "canceled":
                    if order_item.sale_order_line_id.order_id.locked:
                        order_item.sale_order_line_id.order_id.action_unlock()
                        order_item.sale_order_line_id.product_qty = max(
                            order_item.sale_order_line_id.product_qty - 1, 0
                        )
                        order_item.sale_order_line_id.order_id.action_lock()
                    else:
                        order_item.sale_order_line_id.product_qty = max(
                            order_item.sale_order_line_id.product_qty - 1, 0
                        )
        return super().write(vals)
