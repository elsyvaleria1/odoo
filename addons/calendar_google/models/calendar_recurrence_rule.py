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
        Link = self.env["calendar.sync.link"]
        for recurrence in self:
            series = Link._of(recurrence, "google")
            if series and not series.filtered("pending"):
                continue
            series_id = series[:1].remote_id
            retired = recurrence.calendar_event_ids._google_links().filtered(
                lambda link, series_id=series_id: (
                    link.remote_id
                    and link.event_id.active
                    and link.remote_id
                    != self._instance_google_id(series_id, link.event_id)
                )
            )
            if retired:
                events = retired.event_id
                retired.write({"event_id": False})
                retired.account_id._queue_push(events.browse())

    def _get_event_google_id(self, event):
        return self._instance_google_id(self._google_id(), event)

    @api.model
    def _instance_google_id(self, series_id, event):
        if not series_id:
            return False
        if event.allday:
            time_id = event.start_date.isoformat().replace("-", "")
        else:
            start_compacted_iso8601 = (
                event.start.isoformat().replace("-", "").replace(":", "")
            )
            time_id = "%sZ" % start_compacted_iso8601
        return "%s_%s" % (series_id, time_id)

    def _get_fields_google_synced(self):
        return {"rrule"}

    def _write_from_google(self, gevent, vals) -> None:
        current_rrule = self.rrule
        current_parsed_rrule = self._rrule_parse(
            current_rrule,
            self.dtstart,
            tz=self._get_timezone(),
            allday=self._is_allday(),
        )
        vals["event_tz"] = gevent.start.get("timeZone")
        super()._write_from_google(gevent, vals)

        base_event_time_fields = ["start", "stop", "allday"]
        new_event_values = self.env["calendar.event"]._odoo_values(
            gevent, event=self.base_event_id
        )
        new_parsed_rrule = self._rrule_parse(
            self.rrule, self.dtstart, tz=self._get_timezone(), allday=self._is_allday()
        )
        google_attendees = gevent.attendees or []
        emails = [a.get("email") for a in google_attendees]
        partner_by_email = self._get_sync_partner(emails)
        existing_attendees = self.calendar_event_ids.attendee_ids
        attendees_by_email = existing_attendees.grouped(
            lambda attendee: email_normalize(attendee.email)
        )
        for email, google_attendee in zip(emails, google_attendees, strict=True):
            if (normalized := email_normalize(email)) in attendees_by_email:
                attendees_by_email[normalized].write(
                    {"state": google_attendee.get("responseStatus")}
                )
            else:
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
            (self.calendar_event_ids - base_event_id)._google_unlink()
            (self.calendar_event_ids - base_event_id).unlink()
            base_event_id._google_unlink()
            base_event_id.with_context(
                dont_notify=True, google_calendar_syncing=True
            ).write(new_event_values)
            if new_parsed_rrule == current_parsed_rrule:
                self.with_context(
                    dont_notify=True, google_calendar_syncing=True
                )._apply_recurrence()
        else:
            time_fields = (
                self.env["calendar.event"]._get_fields_time()
                | self.env["calendar.event"]._get_fields_recurrent()
            )
            self._write_events(
                {
                    field: value
                    for field, value in new_event_values.items()
                    if field not in time_fields
                }
            )

        if new_parsed_rrule != current_parsed_rrule:
            detached_events = self._apply_recurrence()
            detached_events._google_unlink()
            log_msg = f"Recurrence #{self.id} | current rule: {current_rrule} | new rule: {self.rrule} | remaining: {len(self.calendar_event_ids)} | removed: {len(detached_events)}"
            _logger.info(log_msg)
            detached_events.unlink()

    def _create_from_google(self, gevents, vals_list):
        attendee_values = {}
        for gevent, vals in zip(gevents, vals_list, strict=False):
            base_values = self.env["calendar.event"]._odoo_values(gevent)
            base_event = self.env["calendar.event"]._google_records([gevent.id])
            if not base_event:
                base_event = (
                    self.env["calendar.event"]
                    .with_context(skip_contact_description=True)
                    .create(base_values)
                )
            else:
                base_event._google_unlink()
                base_event.write(base_values)
            vals["base_event_id"] = base_event.id
            vals["calendar_event_ids"] = [Command.link(base_event.id)]
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
        }

    def _google_values(self):
        event = self._get_first_event()
        if not event:
            return {}
        values = event._google_values()
        values["id"] = self._google_id()
        if not self._is_allday():
            values["start"]["timeZone"] = self.event_tz or "Etc/UTC"
            values["end"]["timeZone"] = self.event_tz or "Etc/UTC"

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
