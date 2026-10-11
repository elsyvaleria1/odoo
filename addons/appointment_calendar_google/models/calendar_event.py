import uuid

from odoo import models
from odoo.api import ValuesType

from odoo.addons.calendar_google.utils.google_event import GoogleEvent


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    def _compute_videocall_redirection(self) -> None:
        events_w_google_url = self.filtered(
            lambda event: event.videocall_source == "google_meet"
        )
        for event in events_w_google_url:
            if event.user_id._calendar_sync_active("google"):
                if not event.access_token:
                    event._update_access_token()
                event.videocall_redirection = (
                    f"{event.get_base_url()}/calendar/videocall/{event.access_token}"
                )
            else:
                event.videocall_redirection = False
        super(
            CalendarEvent, self - events_w_google_url
        )._compute_videocall_redirection()

    def _google_values(self):
        values = super()._google_values()
        if not self.appointment_type_id:
            return values
        if self.appointment_type_id.sudo().event_videocall_source != "google_meet":
            values.pop("conferenceData", None)
        elif (
            not self._google_id()
            and not self.videocall_location
            and not values.get("conferenceData")
        ):
            values["conferenceData"] = {
                "createRequest": {"requestId": uuid.uuid4().hex}
            }
        return values

    def _prepare_post_sync_vals(self, request_values, google_values) -> ValuesType:
        self.check_singleton()
        post_values = super()._prepare_post_sync_vals(request_values, google_values)
        if self.appointment_type_id.sudo().event_videocall_source == "google_meet":
            gevent = GoogleEvent([google_values])
            if gevent.id and gevent.hangoutLink:
                post_values.update({"videocall_location": gevent.hangoutLink})
        return post_values
