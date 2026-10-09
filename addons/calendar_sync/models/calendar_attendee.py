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
        through the one answering when the event has none. A provider with
        an answer endpoint hears it from the attendee's own calendar instead."""
        Account = self.env["calendar.sync.account"]
        Link = self.env["calendar.sync.link"]
        for code, provider in Account._engine_providers().items():
            if provider.capabilities.answer_endpoint:
                self._calendar_sync_answer_in_own_calendar(code)
                continue
            for event in self.event_id:
                sender = event.user_id or self.env.user
                links = Link._of(event, code)
                if not links or sender._calendar_sync_stopped(code):
                    continue
                # owed like an edit: sent when the synchronization runs
                links.write({"pending": True, "error": False})
                if sender._calendar_sync_active(code):
                    Account._for(sender, code)._as_engine()._queue_push(event)

    def _calendar_sync_answer_in_own_calendar(self, code: str) -> None:
        """The current user's answers, owed from their own calendar while they
        synchronize with `code`, paused or not; the organizer has none to
        give."""
        user = self.env.user
        if not user._calendar_sync_connection(code) or user._calendar_sync_stopped(
            code
        ):
            return
        Link = self.env["calendar.sync.link"]
        account = self.env["calendar.sync.account"]._for(user, code)._as_engine()
        for attendee in self.filtered(
            lambda attendee: (
                attendee.partner_id == user.partner_id
                and attendee.event_id.user_id != user
            )
        ):
            if Link._of(attendee.event_id, code):
                account._owe_answer(attendee.event_id, attendee.state)
