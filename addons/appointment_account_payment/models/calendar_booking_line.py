from odoo import fields, models


class CalendarBookingLine(models.Model):
    _name = "calendar.booking.line"
    _description = "Meeting User/Resource Booking"
    _order = "create_date DESC, id DESC"
    _rec_name = "calendar_booking_id"

    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        readonly=True,
        ondelete="cascade",
    )
    appointment_user_id = fields.Many2one(
        comodel_name="res.users",
        related="calendar_booking_id.staff_user_id",
        string="Users",
    )
    calendar_booking_id = fields.Many2one(
        comodel_name="calendar.booking",
        string="Meeting Booking",
        index=True,
        required=True,
        ondelete="cascade",
    )
    capacity_reserved = fields.Integer(
        default=1,
        readonly=True,
    )
    capacity_used = fields.Integer(readonly=True)
