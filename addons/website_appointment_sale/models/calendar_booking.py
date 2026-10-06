from markupsafe import Markup, escape

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class CalendarBooking(models.Model):
    _inherit = "calendar.booking"

    order_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sale Order Line",
        index="btree_not_null",
        ondelete="cascade",
    )

    def _cancel_pending_booking(self):
        """Cart bookings must be removed with their order line through the cart."""
        self.check_singleton()
        if self.order_line_id:
            _debug.logic(
                "booking_cancel_deferred",
                reason="owned_by_cart_line",
                booking=self.id,
            )
            return False
        return super()._cancel_pending_booking()

    def _create_event_from_paid_booking(self) -> None:
        super()._create_event_from_paid_booking()
        for booking in self.filtered("order_line_id"):
            booking.order_line_id.calendar_event_id = booking.calendar_event_id

    def _log_booking_collisions(self) -> None:
        super()._log_booking_collisions()
        odoobot = self.env.ref("base.partner_root")
        for order, order_lines in self.order_line_id.grouped("order_id").items():
            order._message_log(
                body=Markup("<p>%s</p>")
                % escape(
                    self.env._(
                        "The following bookings were not confirmed due to insufficient availability or configuration changes: %s"
                    )
                )
                % Markup(", ").join(
                    [
                        booking._get_html_link()
                        for booking in order_lines.calendar_booking_ids
                    ]
                ),
                author_id=odoobot.id,
            )
