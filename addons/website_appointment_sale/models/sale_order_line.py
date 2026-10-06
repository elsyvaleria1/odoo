from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    calendar_booking_ids = fields.One2many(
        comodel_name="calendar.booking",
        inverse_name="order_line_id",
        string="Bookings",
    )
    calendar_event_id = fields.Many2one(
        comodel_name="calendar.event",
        string="Meeting",
        index="btree_not_null",
    )

    @api.depends("calendar_booking_ids")
    def _compute_product_uom_readonly(self) -> None:
        booking_so_lines = self.filtered("calendar_booking_ids")
        booking_so_lines.product_uom_readonly = True
        super(SaleOrderLine, self - booking_so_lines)._compute_product_uom_readonly()

    def _is_zero_price_allowed(self) -> bool:
        return bool(self.calendar_booking_ids) or super()._is_zero_price_allowed()

    def _is_sellable(self) -> bool:
        return super()._is_sellable() and not self.calendar_booking_ids

    def unlink(self):
        self.calendar_booking_ids.unlink()
        return super().unlink()

    def _is_reorder_allowed(self) -> bool:
        return bool(not self.calendar_booking_ids and super()._is_reorder_allowed())
