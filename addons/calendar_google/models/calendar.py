from datetime import UTC
from typing import Any
from uuid import uuid4

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.tools.authority_keys import declare_authority_keys

declare_authority_keys("calendar_google", "skip_event_permission")


class CalendarEvent(models.Model):
    _name = "calendar.event"
    _inherit = ["calendar.event", "mixin.google.calendar.sync"]

    MEET_ROUTE = "meet.google.com"

    guests_readonly = fields.Boolean(
        string="Guests Event Modification Permission",
        default=False,
    )
    videocall_source = fields.Selection(
        selection_add=[("google_meet", "Google Meet")],
        ondelete={"google_meet": "set discuss"},
    )

    def _google_link_instances(self) -> None:
        links = self.recurrence_id._google_links().grouped("recurrence_id")
        if not links:
            return
        linked = self._google_links().event_id
        unlinked = self.filtered(
            lambda event: event.recurrence_id in links and event not in linked
        )
        Recurrence = self.env["calendar.recurrence"]
        for recurrence, events in unlinked.grouped("recurrence_id").items():
            series = links[recurrence][:1]
            self._google_link(
                series.account_id,
                {
                    event.id: Recurrence._instance_google_id(series.remote_id, event)
                    for event in events
                },
            )

    @api.depends("videocall_location")
    def _compute_videocall_source(self) -> None:
        events_with_google_url = self.filtered(
            lambda event: self.MEET_ROUTE in (event.videocall_location or "")
        )
        events_with_google_url.videocall_source = "google_meet"
        super(CalendarEvent, self - events_with_google_url)._compute_videocall_source()

    @api.model
    def _get_fields_google_synced(self):
        return {
            "name",
            "description",
            "allday",
            "start",
            "date_end",
            "stop",
            "attendee_ids",
            "alarm_ids",
            "location",
            "privacy",
            "active",
            "show_as",
            "videocall_location",
        }

    @api.model
    def _has_values_to_sync(self, values) -> bool:
        synced_fields = self._get_fields_google_synced()
        return any(key in synced_fields for key in values)

    def write(self, vals):
        syncing = self.env.context.get("google_calendar_syncing") or (
            self.env.context.get("calendar_sync_applying") == "google"
        )
        if not syncing and any(self.env.user != event.user_id for event in self):
            self._check_modify_event_permission(vals)
        return super().write(vals)

    def _check_modify_event_permission(self, values) -> None:
        skip_event_permission = self.env.context.get("skip_event_permission", False)
        is_synchronizable = self._has_values_to_sync(values)
        if skip_event_permission or not is_synchronizable:
            return
        if any(
            event.guests_readonly and self.env.user.id != event.user_id.id
            for event in self
        ):
            raise ValidationError(
                self.env._(
                    "The following event can only be updated by the organizer "
                    "according to the event permissions set on Google Calendar."
                )
            )

    @api.model
    def _odoo_values(self, google_event, default_reminders=(), event=None):
        if google_event.is_cancelled():
            return {"active": False}

        reminder_command = google_event.reminders.get("overrides")
        if not reminder_command:
            reminder_command = (
                google_event.reminders.get("useDefault") and default_reminders
            ) or ()
        alarm_commands = self._odoo_reminders_commands(reminder_command)
        attendee_commands, partner_commands = self._odoo_attendee_commands(
            google_event, event or self.browse()
        )
        related_event = self._google_records([google_event.id])[:1]
        name = (
            google_event.summary
            or (related_event and related_event.name)
            or self.env._("(No title)")
        )
        values = {
            "name": name,
            "description": google_event.description
            and tools.html_sanitize(google_event.description),
            "location": google_event.location,
            "user_id": google_event.owner(self.env).id,
            "privacy": google_event.visibility or False,
            "attendee_ids": attendee_commands,
            "alarm_ids": alarm_commands,
            "recurrency": google_event.is_recurrent(),
            "videocall_location": google_event.get_meeting_url(),
            "show_as": "free" if google_event.is_available() else "busy",
            "guests_readonly": not bool(google_event.guestsCanModify),
        }
        if not values.get("videocall_location"):
            values.pop("videocall_location", False)
        if partner_commands:
            values["partner_ids"] = partner_commands
        if google_event.is_recurrent() and not google_event.is_recurrence():
            values["follow_recurrence"] = google_event.is_recurrence_follower()
        if google_event.start.get("dateTime"):
            start = (
                parse(google_event.start.get("dateTime"))
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
            stop = (
                parse(google_event.end.get("dateTime"))
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
            values["allday"] = False
        else:
            start = parse(google_event.start.get("date"))
            stop = parse(google_event.end.get("date")) - relativedelta(days=1)
            if stop < start:
                stop = parse(google_event.end.get("date"))
            values["allday"] = True
        if related_event["start"] != start:
            values["start"] = start
        if related_event["stop"] != stop:
            values["stop"] = stop
        return values

    @api.model
    def _odoo_attendee_commands(self, google_event, event) -> tuple:
        attendee_commands = []
        partner_commands = []
        google_attendees = google_event.attendees or []
        if (
            len(google_attendees) == 0
            and google_event.organizer
            and google_event.organizer.get("self", False)
        ):
            user = google_event.owner(self.env)
            google_attendees += [
                {
                    "email": user.partner_id.email,
                    "responseStatus": "accepted",
                }
            ]
        emails = [a.get("email") for a in google_attendees]
        existing_attendees = event.attendee_ids
        attendees_by_emails = {
            tools.email_normalize(a.email): a for a in existing_attendees
        }
        partner_by_email = self._get_sync_partner(emails)
        for email, google_attendee in zip(emails, google_attendees, strict=True):
            if (normalized := tools.email_normalize(email)) in attendees_by_emails:
                attendee_commands += [
                    Command.update(
                        attendees_by_emails[normalized].id,
                        {"state": google_attendee.get("responseStatus")},
                    )
                ]
            else:
                if google_attendee.get("self"):
                    partner = self.env.user.partner_id
                elif partner_by_email.get(email):
                    partner = partner_by_email[email]
                else:
                    continue
                attendee_commands += [
                    Command.create(
                        {
                            "state": google_attendee.get("responseStatus"),
                            "partner_id": partner.id,
                        }
                    )
                ]
                partner_commands += [Command.link(partner.id)]
                if google_attendee.get("displayName") and not partner.name:
                    partner.name = google_attendee.get("displayName")
        google_emails = {tools.email_normalize(email) for email in emails}
        user_email = tools.email_normalize(self.env.user.email)
        for email, odoo_attendee in attendees_by_emails.items():
            if email not in google_emails and email != user_email:
                attendee_commands += [Command.delete(odoo_attendee.id)]
                partner_commands += [Command.unlink(odoo_attendee.partner_id.id)]
        return attendee_commands, partner_commands

    @api.model
    def _odoo_reminders_commands(self, reminders=()):
        commands = []
        for reminder in reminders:
            alarm_type = (
                "email" if reminder.get("method") == "email" else "notification"
            )
            alarm_type_label = (
                self.env._("Email")
                if alarm_type == "email"
                else self.env._("Notification")
            )

            minutes = reminder.get("minutes", 0)
            alarm = self.env["calendar.alarm"].search(  # noqa: E8507 -- one lookup per reminder of the synced event
                [("alarm_type", "=", alarm_type), ("duration_minutes", "=", minutes)],
                limit=1,
            )
            if alarm:
                commands += [Command.link(alarm.id)]
            else:
                if minutes % (60 * 24) == 0:
                    interval = "days"
                    duration = minutes / 60 / 24
                    name = self.env._(
                        "%(reminder_type)s - %(duration)s Days",
                        reminder_type=alarm_type_label,
                        duration=duration,
                    )
                elif minutes % 60 == 0:
                    interval = "hours"
                    duration = minutes / 60
                    name = self.env._(
                        "%(reminder_type)s - %(duration)s Hours",
                        reminder_type=alarm_type_label,
                        duration=duration,
                    )
                else:
                    interval = "minutes"
                    duration = minutes
                    name = self.env._(
                        "%(reminder_type)s - %(duration)s Minutes",
                        reminder_type=alarm_type_label,
                        duration=duration,
                    )
                commands += [
                    Command.create(
                        {
                            "duration": duration,
                            "interval": interval,
                            "name": name,
                            "alarm_type": alarm_type,
                        }
                    )
                ]
        return commands

    def action_mass_archive(self, recurrence_update_setting) -> None:
        self.check_singleton()
        archive_future_events = (
            recurrence_update_setting == "subsequent"
            and self == self.recurrence_id.base_event_id
        )
        if recurrence_update_setting == "all" or archive_future_events:
            Link = self.env["calendar.sync.link"]
            Link._of(self.recurrence_id.calendar_event_ids, "google").unlink()
            series = Link._of(self.recurrence_id, "google")
            series.write({"recurrence_id": False})
            series.account_id._queue_push(self.browse())
            if archive_future_events:
                recurrence_update_setting = "all"
        super().action_mass_archive(recurrence_update_setting)

    def _get_google_start_end(self) -> tuple:
        start = {"date": None, "dateTime": None}
        end = {"date": None, "dateTime": None}
        if self.allday:
            start["date"] = self.start_date.isoformat()
            end["date"] = (self.stop_date + relativedelta(days=1)).isoformat()
        else:
            start["dateTime"] = self.start.replace(tzinfo=UTC).isoformat()
            end["dateTime"] = self.stop.replace(tzinfo=UTC).isoformat()
        return start, end

    def _prepare_google_attendee_vals_list(self) -> list[dict[str, Any]]:
        attendee_values = [
            {
                "email": attendee.partner_id.email_normalized,
                "responseStatus": attendee.state or "needsAction",
            }
            for attendee in self.attendee_ids
            if attendee.partner_id.email_normalized
        ]
        attendee_values.sort(key=lambda k: k["email"])
        return attendee_values

    def _update_google_owner_values(self, values):
        if (
            self.user_id
            and self.user_id != self.env.user
            and not self.user_id._calendar_sync_connection("google")
        ):
            values["extendedProperties"]["shared"][
                "%s_owner_id" % self.env.cr.dbname
            ] = self.user_id.id
        elif not self.user_id:
            keep_keys = ["id", "summary", "attendees", "start", "end", "reminders"]
            values = {key: val for key, val in values.items() if key in keep_keys}
            values["extendedProperties"] = {
                "private": {
                    "%s_odoo_id" % self.env.cr.dbname: self.id,
                },
            }
        return values

    def _google_values(self):
        start, end = self._get_google_start_end()
        reminders = [
            {
                "method": "email" if alarm.alarm_type == "email" else "popup",
                "minutes": alarm.duration_minutes,
            }
            for alarm in self.alarm_ids
        ]
        google_id = self._google_id()
        values = {
            "id": google_id,
            "start": start,
            "end": end,
            "summary": self.name,
            "description": self._get_customer_description(),
            "location": self.location or "",
            "guestsCanModify": not self.guests_readonly,
            "organizer": {
                "email": self.user_id.email,
                "self": self.user_id == self.env.user,
            },
            "attendees": self._prepare_google_attendee_vals_list(),
            "extendedProperties": {
                "shared": {
                    "%s_odoo_id" % self.env.cr.dbname: self.id,
                },
            },
            "reminders": {
                "overrides": reminders,
                "useDefault": False,
            },
        }
        if not google_id and not self.videocall_location and not self.location:
            values["conferenceData"] = {"createRequest": {"requestId": uuid4().hex}}
        if google_id and not self.videocall_location:
            values["conferenceData"] = None
        if self.privacy:
            values["visibility"] = self.privacy
        if self.show_as:
            values["transparency"] = (
                "opaque" if self.show_as == "busy" else "transparent"
            )
        if not self.active:
            values["status"] = "cancelled"
        return self._update_google_owner_values(values)
