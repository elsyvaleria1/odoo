from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    calendar_event_count = fields.Integer(
        string="Meetings",
        compute="_compute_meeting_count",
    )

    @api.depends("line_ids")
    def _compute_meeting_count(self) -> None:
        event_count_per_so = {
            sale_order.id: event_count
            for sale_order, event_count in self.env["sale.order.line"]._read_group(
                [("order_id", "in", self.ids), ("calendar_event_id", "!=", False)],
                ["order_id"],
                ["__count"],
            )
        }
        for sale_order in self:
            sale_order.calendar_event_count = event_count_per_so.get(sale_order.id, 0)

    def action_view_calendar_events(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "calendar.action_calendar_event"
        )
        action["domain"] = [("id", "in", self.line_ids.calendar_event_id.ids)]
        action["views"] = [(False, "list"), (False, "form")]
        action["context"] = {"active_test": False}
        return action

    def _action_cancel(self):
        self.line_ids.calendar_event_id.action_archive()
        return super()._action_cancel()

    def _action_confirm(self):
        self.line_ids.calendar_event_id.action_unarchive()
        self.line_ids.calendar_booking_ids._create_event_from_paid_booking()
        return super()._action_confirm()

    def _check_cart_is_ready_to_be_paid(self):
        self.check_singleton()
        bookings = self.line_ids.calendar_booking_ids
        unavailable_bookings = bookings._filter_unavailable_bookings()
        if unavailable_bookings:
            _debug.logic(
                "booking_cart_refused",
                reason="slots_unavailable",
                order=self.id,
                bookings=unavailable_bookings,
            )
            raise ValidationError(
                self.env._(
                    "The following bookings are not available anymore during the selected period"
                    " and your cart must be updated. We are sorry for the inconvenience.\n\n%(bookings)s",
                    bookings=[
                        booking._get_description() for booking in unavailable_bookings
                    ],
                ),
            )
        return super()._check_cart_is_ready_to_be_paid()

    def _cart_find_product_line(self, *args, calendar_booking_id=False, **kwargs):
        if calendar_booking_id:
            return self.env["sale.order.line"]
        return super()._cart_find_product_line(
            *args,
            calendar_booking_id=calendar_booking_id,
            **kwargs,
        )

    def _prepare_order_line_values(
        self, *args, calendar_booking_id=False, calendar_booking_tz=False, **kwargs
    ):
        values = super()._prepare_order_line_values(
            *args,
            calendar_booking_id=calendar_booking_id,
            calendar_booking_tz=calendar_booking_tz,
            **kwargs,
        )
        if not calendar_booking_id:
            return values
        booking_sudo = self.env["calendar.booking"].sudo().browse(calendar_booking_id)
        values["calendar_booking_ids"] = [Command.link(calendar_booking_id)]
        values["name"] = booking_sudo.with_context(
            tz=calendar_booking_tz, lang=self.partner_id.lang
        )._get_description()
        return values

    def unlink(self):
        self.line_ids.unlink()
        return super().unlink()
