from odoo import models


class CalendarAttendee(models.Model):
    _inherit = "calendar.attendee"

    def do_tentative(self):
        self._microsoft_check_answer()
        return super().do_tentative()

    def do_accept(self):
        self._microsoft_check_answer()
        return super().do_accept()

    def do_decline(self):
        self._microsoft_check_answer()
        return super().do_decline()

    def _microsoft_check_answer(self) -> None:
        user = self.env.user
        for event in self.event_id._microsoft_held():
            if (
                event.recurrency
                and event._check_microsoft_sync_status()
                and user != event.user_id
                and user.partner_id in event.partner_ids
            ):
                event._forbid_recurrence_update()
