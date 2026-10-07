import logging

from odoo import api, models
from odoo.fields import Command
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)


class CalendarRecurrence(models.Model):
    _name = "calendar.recurrence"
    _inherit = ["calendar.recurrence", "mixin.google.calendar.sync"]

    def _apply_recurrence(
        self,
        specific_values_creation=None,
        no_send_edit=False,
        generic_values_creation=None,
    ):
        detached_events = super()._apply_recurrence(
            specific_values_creation, no_send_edit, generic_values_creation
        )
        if self.env.context.get("calendar_sync_applying") != "google":
            self._google_retire_single_ids()
        return detached_events

    def _google_retire_single_ids(self) -> None:
        """An event Google holds alone that became an event of a series leaves
        Google under its own id: its links become tombstones, deleted by the
        next push, and the series is sent for it."""
        Link = self.env["calendar.sync.link"]
        for recurrence in self:
            if (links := Link._of(recurrence, "google")) and not links.filtered(
                "pending"
            ):
                # Google holds the series as it is: its events' ids are its own
                continue
            events = recurrence.calendar_event_ids.filtered(
                lambda event, recurrence=recurrence: (
                    event.active
                    and event.google_id
                    and event.google_id != recurrence._get_event_google_id(event)
                )
            )
            if not events:
                continue
            retired = Link._of(events, "google")
            retired.write({"event_id": False})
            retired.account_id._queue_push(events.browse())

    def _inverse_google_id(self) -> None:
        super()._inverse_google_id()
        self.filtered("google_id").calendar_event_ids._google_link_instances()

    def _get_event_google_id(self, event):
        """Return the Google id of recurring event.
        Google ids of recurrence instances are formatted as: {recurrence google_id}_{UTC starting time in compacted ISO8601}
        """
        if self.google_id:
            if event.allday:
                time_id = event.start_date.isoformat().replace("-", "")
            else:
                # '-' and ':' are optional in ISO8601
                start_compacted_iso8601 = (
                    event.start.isoformat().replace("-", "").replace(":", "")
                )
                # Z at the end for UTC
                time_id = "%sZ" % start_compacted_iso8601
            return "%s_%s" % (self.google_id, time_id)
        return False

    def _write_events(self, values, dtstart=None):
        values.pop("google_id", False)
        return super()._write_events(values, dtstart=dtstart)

    def _get_fields_google_synced(self):
        return {"rrule"}

    def _write_from_google(self, gevent, vals) -> None:
        current_rrule = self.rrule
        current_parsed_rrule = self._rrule_parse(
            current_rrule, self.dtstart, tz=self._get_timezone()
        )
        # event_tz is written on event in Google but on recurrence in Odoo
        vals["event_tz"] = gevent.start.get("timeZone")
        super()._write_from_google(gevent, vals)

        base_event_time_fields = ["start", "stop", "allday"]
        new_event_values = self.env["calendar.event"]._odoo_values(
            gevent, event=self.base_event_id
        )
        new_parsed_rrule = self._rrule_parse(
            self.rrule, self.dtstart, tz=self._get_timezone()
        )
        # We update the attendee status for all events in the recurrence
        google_attendees = gevent.attendees or []
        emails = [a.get("email") for a in google_attendees]
        partner_by_email = self._get_sync_partner(emails)
        existing_attendees = self.calendar_event_ids.attendee_ids
        attendees_by_email = existing_attendees.grouped(
            lambda attendee: email_normalize(attendee.email)
        )
        for email, google_attendee in zip(emails, google_attendees, strict=True):
            if (normalized := email_normalize(email)) in attendees_by_email:
                # Update existing attendees
                attendees_by_email[normalized].write(
                    {"state": google_attendee.get("responseStatus")}
                )
            else:
                # Create new attendees
                if google_attendee.get("self"):
                    partner = self.env.user.partner_id
                elif partner_by_email.get(email):
                    partner = partner_by_email[email]
                else:
                    continue
                self.calendar_event_ids.write(
                    {
                        "attendee_ids": [
                            Command.create(
                                {
                                    "state": google_attendee.get("responseStatus"),
                                    "partner_id": partner.id,
                                }
                            )
                        ]
                    }
                )
                if google_attendee.get("displayName") and not partner.name:
                    partner.name = google_attendee.get("displayName")

        organizers = self.calendar_event_ids.user_id.partner_id
        google_emails = {email_normalize(email) for email in emails}
        for email, attendees in attendees_by_email.items():
            # Sometimes, several partners have the same email. Remove old attendees except organizer, otherwise the events will disappear.
            if email not in google_emails:
                attendees = attendees.exists().filtered_domain(
                    [("partner_id", "not in", organizers.ids)]
                )
                self.calendar_event_ids.write(
                    {
                        "partner_ids": [
                            Command.unlink(att.partner_id.id) for att in attendees
                        ],
                    }
                )

        old_event_values = (
            self.base_event_id and self.base_event_id.read(base_event_time_fields)[0]
        )
        if old_event_values and any(
            new_event_values.get(key) and new_event_values[key] != old_event_values[key]
            for key in base_event_time_fields
        ):
            # we need to recreate the recurrence, time_fields were modified.
            base_event_id = self.base_event_id
            non_equal_values = [
                (
                    key,
                    old_event_values[key]
                    and old_event_values[key].strftime("%m/%d/%Y, %H:%M:%S"),
                    "-->",
                    new_event_values[key]
                    and new_event_values[key].strftime("%m/%d/%Y, %H:%M:%S"),
                )
                for key in ["start", "stop"]
                if new_event_values[key] != old_event_values[key]
            ]
            log_msg = f"Recurrence {self.id} {self.rrule} has all events ({len(self.calendar_event_ids.ids)})  deleted because of base event value change: {non_equal_values}"
            _logger.info(log_msg)
            # We archive the old events to recompute the recurrence. These events are already deleted on Google side.
            # We can't call _cancel because events without user_id would not be deleted
            (self.calendar_event_ids - base_event_id).google_id = False
            (self.calendar_event_ids - base_event_id).unlink()
            base_event_id.with_context(
                dont_notify=True, google_calendar_syncing=True
            ).write(dict(new_event_values, google_id=False))
            if new_parsed_rrule == current_parsed_rrule:
                # if the rrule has changed, it will be recalculated below
                # There is no detached event now
                self.with_context(
                    dont_notify=True, google_calendar_syncing=True
                )._apply_recurrence()
        else:
            time_fields = (
                self.env["calendar.event"]._get_fields_time()
                | self.env["calendar.event"]._get_fields_recurrent()
            )
            # We avoid to write time_fields because they are not shared between events.
            self._write_events(
                {
                    field: value
                    for field, value in new_event_values.items()
                    if field not in time_fields
                }
            )

        # We apply the rrule check after the time_field check because the google_id are generated according
        # to base_event start datetime.
        if new_parsed_rrule != current_parsed_rrule:
            detached_events = self._apply_recurrence()
            detached_events.google_id = False
            log_msg = f"Recurrence #{self.id} | current rule: {current_rrule} | new rule: {self.rrule} | remaining: {len(self.calendar_event_ids)} | removed: {len(detached_events)}"
            _logger.info(log_msg)
            detached_events.unlink()

    def _create_from_google(self, gevents, vals_list):
        attendee_values = {}
        for gevent, vals in zip(gevents, vals_list, strict=False):
            base_values = self.env["calendar.event"]._odoo_values(gevent)
            # If we convert a single event into a recurrency on Google, we should reuse this event on Odoo
            # Google reuse the event google_id to identify the recurrence in that case
            base_event = self.env["calendar.event"].search(  # noqa: E8507 - one lookup per synced recurrence, on its google id
                [("google_id", "=", vals["google_id"])]
            )
            if not base_event:
                base_event = (
                    self.env["calendar.event"]
                    .with_context(skip_contact_description=True)
                    .create(base_values)
                )
            else:
                # We override the base_event values because they could have been changed in Google interface
                # The event google_id will be recalculated once the recurrence is created
                base_event.write(dict(base_values, google_id=False))
            vals["base_event_id"] = base_event.id
            vals["calendar_event_ids"] = [Command.link(base_event.id)]
            # event_tz is written on event in Google but on recurrence in Odoo
            vals["event_tz"] = gevent.start.get("timeZone")
            attendee_values[base_event.id] = {
                "attendee_ids": base_values.get("attendee_ids")
            }

        recurrence = super(
            CalendarRecurrence,
            self.with_context(dont_notify=True, google_calendar_syncing=True),
        )._create_from_google(gevents, vals_list)
        generic_values_creation = {
            rec.id: attendee_values[rec.base_event_id.id]
            for rec in recurrence
            if attendee_values.get(rec.base_event_id.id)
        }
        recurrence.with_context(
            dont_notify=True, google_calendar_syncing=True
        )._apply_recurrence(generic_values_creation=generic_values_creation)
        return recurrence

    @api.model
    def _odoo_values(self, google_recurrence, default_reminders=()):
        return {
            "rrule": google_recurrence.rrule,
            "google_id": google_recurrence.id,
        }

    def _google_values(self):
        event = self._get_first_event()
        if not event:
            return {}
        values = event._google_values()
        values["id"] = self.google_id
        if not self._is_allday():
            values["start"]["timeZone"] = self.event_tz or "Etc/UTC"
            values["end"]["timeZone"] = self.event_tz or "Etc/UTC"

        # DTSTART is not allowed by Google Calendar API -- event start and end
        # times are specified in the start and end fields -- and UNTIL must be
        # stamped UTC. Both are what `_get_ics_rrule` does for the .ics, off the
        # same stored column, so the two shapes that column can hold are known
        # in one place rather than re-derived here by regex.
        values["recurrence"] = [
            "RRULE:%s" % self.env["calendar.event"]._get_ics_rrule(self.rrule)
        ]
        property_location = "shared" if event.user_id else "private"
        values["extendedProperties"] = {
            property_location: {
                "%s_odoo_id" % self.env.cr.dbname: self.id,
            },
        }
        return values
