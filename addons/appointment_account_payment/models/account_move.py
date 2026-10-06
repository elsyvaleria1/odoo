from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    calendar_booking_ids = fields.One2many(
        comodel_name="calendar.booking",
        inverse_name="account_move_id",
        string="Meeting Booking",
    )

    def _post_entries(self):
        """Override: turn the bookings of the posted invoices into calendar events."""
        # Reached either when posting manually or when the transaction is done.
        posted = super()._post_entries()
        posted.calendar_booking_ids._create_event_from_paid_booking()
        return posted
