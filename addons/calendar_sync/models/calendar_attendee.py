from odoo import models


class CalendarAttendee(models.Model):
    _inherit = "calendar.attendee"

    def do_tentative(self):
        result = super().do_tentative()
        self._calendar_sync_answered()
        return result

    def do_accept(self):
        result = super().do_accept()
        self._calendar_sync_answered()
        return result

    def do_decline(self):
        result = super().do_decline()
        self._calendar_sync_answered()
        return result

    def _calendar_sync_answered(self) -> None:
        """An answer changes the event in every calendar holding it, which
        only its organizer may write: it goes out through the organizer, or
        through the one answering when the event has none."""
        Account = self.env["calendar.sync.account"]
        Link = self.env["calendar.sync.link"]
        for code in Account._engine_providers():
            for event in self.event_id:
                sender = event.user_id or self.env.user
                links = Link._of(event, code)
                if not (links and sender._calendar_sync_active(code)):
                    continue
                links.write({"pending": True, "error": False})
                Account._for(sender, code)._as_engine()._queue_push(event)
