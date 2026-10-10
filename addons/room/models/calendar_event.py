from collections import defaultdict
from typing import Literal, Self, TypedDict

from odoo import api, fields, models

KIOSK_EVENT_FIELDS = {"name", "start", "stop", "active", "privacy", "user_id"}


class RoomBookingData(TypedDict):
    id: int
    name: str
    start_datetime: str | Literal[False]
    stop_datetime: str | Literal[False]


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    def _prepare_room_booking_data(self) -> RoomBookingData:
        # A kiosk is public and reads its bookings elevated, past the masking
        # calendar applies to a private event's name for anyone not invited.
        self.check_singleton()
        hidden = self.effective_privacy in ("private", "confidential")
        return {
            "id": self.id,
            "name": self.env._("Busy") if hidden else self.name,
            "start_datetime": fields.Datetime.to_string(self.start),
            "stop_datetime": fields.Datetime.to_string(self.stop),
        }

    def _get_kiosk_rooms(self):
        return self.sudo().booking_line_ids.resource_id.filtered("access_token")

    def _notify_room_kiosks(self, method) -> None:
        events_by_room = defaultdict(self.browse)
        for event in self:
            for room in event.sudo().booking_line_ids.resource_id:
                events_by_room[room] |= event
        for room in self._get_kiosk_rooms():
            room._notify_booking_view(method, events_by_room[room])

    def write(self, vals):
        if not KIOSK_EVENT_FIELDS & vals.keys():
            return super().write(vals)
        rooms_before = {event.id: event._get_kiosk_rooms() for event in self}
        res = super().write(vals)
        for event in self:
            rooms_now = event._get_kiosk_rooms()
            if not event.active:
                rooms_now = rooms_now.browse()
            for room in rooms_before[event.id] - rooms_now:
                room._notify_booking_view("delete", event)
            for room in rooms_now:
                room._notify_booking_view("update", event)
        return res

    def unlink(self):
        self._notify_room_kiosks("delete")
        return super().unlink()

    @api.model
    def _create_room_booking(self, room, name, start, stop) -> Self:
        return (
            self.sudo()
            .with_context(no_mail_to_attendees=True, mail_create_nosubscribe=True)
            .create(
                {
                    "name": name,
                    "start": start,
                    "stop": stop,
                    "user_id": False,
                    "partner_ids": [],
                    "appointment_type_id": self.env.ref(
                        "room.appointment_type_room"
                    ).id,
                    "booking_line_ids": [
                        fields.Command.create(
                            {"resource_id": room.id, "capacity_reserved": 1}
                        )
                    ],
                }
            )
        )
