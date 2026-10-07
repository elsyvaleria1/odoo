from odoo import fields, models


class CalendarEvent(models.Model):
    _name = "calendar.event"
    _inherit = ["calendar.event", "mixin.calendar.sync"]

    calendar_sync_link_ids = fields.One2many(
        comodel_name="calendar.sync.link",
        inverse_name="event_id",
        string="Calendar Synchronization Links",
        classification="calendar_sync.state",
        groups="base.group_system",
    )

    def _skip_send_mail_status_update(self):
        """A provider the event goes out through invites its attendees itself:
        through its organizer, or the current user when it has none."""
        sender = self.user_id or self.env.user
        if any(
            sender._calendar_sync_active(code)
            for code in self.env["calendar.sync.account"]._engine_providers()
        ):
            return True
        return super()._skip_send_mail_status_update()
