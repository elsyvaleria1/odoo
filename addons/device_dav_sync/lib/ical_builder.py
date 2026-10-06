import contextlib
import logging
from datetime import UTC, datetime, timedelta

from icalendar import Alarm as VAlarm
from icalendar import Calendar, vRecur
from icalendar import Event as IEvent

from odoo.fields import Command
from odoo.libs.datetime import timezone as get_timezone
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


class ICalBuilder:
    def event_to_ical(self, event, timezone=None):
        cal = Calendar()
        cal.add("prodid", "-//Odoo//DAV Sync//EN")
        cal.add("version", "2.0")
        cal.add("method", "PUBLISH")

        if hasattr(event, "calendar_id") and event.calendar_id:
            cal.add("x-wr-calname", event.calendar_id.name)

        tz = get_timezone(timezone) if timezone else UTC
        ical_event = IEvent()

        ical_event.add("uid", event.ical_uid or f"event-{event.id}@odoo")

        ical_event.add("dtstamp", datetime.now(UTC))

        if hasattr(event, "sequence") and event.sequence:
            ical_event.add("sequence", event.sequence)
        else:
            ical_event.add("sequence", 0)

        if event.start:
            if event.allday:
                ical_event.add("dtstart", event.start.date())
            else:
                start_dt = event.start
                if not start_dt.tzinfo:
                    start_dt = start_dt.replace(tzinfo=UTC)
                if tz and tz != UTC:
                    start_dt = start_dt.astimezone(tz)
                ical_event.add("dtstart", start_dt)

        if event.stop:
            if event.allday:
                end_date = event.stop.date() + timedelta(days=1)
                ical_event.add("dtend", end_date)
            else:
                stop_dt = event.stop
                if not stop_dt.tzinfo:
                    stop_dt = stop_dt.replace(tzinfo=UTC)
                if tz and tz != UTC:
                    stop_dt = stop_dt.astimezone(tz)
                ical_event.add("dtend", stop_dt)

        if event.name:
            ical_event.add("summary", event.name)

        if event.description:
            ical_event.add("description", self._html_to_text(event.description))

        if event.location:
            ical_event.add("location", event.location)

        if hasattr(event, "privacy") and event.privacy:
            privacy_map = {
                "public": "PUBLIC",
                "private": "PRIVATE",
                "confidential": "CONFIDENTIAL",
            }
            ical_event.add("class", privacy_map.get(event.privacy, "PUBLIC"))
        else:
            ical_event.add("class", "PUBLIC")

        if hasattr(event, "active") and not event.active:
            ical_event.add("status", "CANCELLED")
        else:
            ical_event.add("status", "CONFIRMED")

        if hasattr(event, "show_as") and event.show_as:
            transp_map = {"free": "TRANSPARENT", "busy": "OPAQUE"}
            ical_event.add("transp", transp_map.get(event.show_as, "OPAQUE"))

        if event.user_id and event.user_id.partner_id:
            organizer_partner = event.user_id.partner_id
            if organizer_partner.email:
                ical_event.add(
                    "organizer",
                    f"mailto:{organizer_partner.email}",
                    parameters={"CN": organizer_partner.name},
                )

        for attendee in event.attendee_ids:
            if attendee.partner_id and attendee.partner_id.email:
                attendee_params = {
                    "CN": attendee.partner_id.name,
                    "ROLE": "REQ-PARTICIPANT",
                    "RSVP": "TRUE",
                }
                if hasattr(attendee, "state"):
                    partstat_map = {
                        "needsAction": "NEEDS-ACTION",
                        "accepted": "ACCEPTED",
                        "declined": "DECLINED",
                        "tentative": "TENTATIVE",
                    }
                    attendee_params["PARTSTAT"] = partstat_map.get(
                        attendee.state, "NEEDS-ACTION"
                    )
                ical_event.add(
                    "attendee",
                    f"mailto:{attendee.partner_id.email}",
                    parameters=attendee_params,
                )

        if (
            hasattr(event, "recurrency")
            and event.recurrency
            and hasattr(event, "rrule")
        ):
            rrule = self._odoo_rrule_to_ical(event)
            if rrule:
                ical_event.add("rrule", rrule)

        if hasattr(event, "recurrent_id") and event.recurrent_id:
            if event.recurrent_id.start:
                recur_id = event.recurrent_id.start
                if not recur_id.tzinfo and not event.allday:
                    recur_id = recur_id.replace(tzinfo=tz)
                ical_event.add("recurrence-id", recur_id)

        if hasattr(event, "categ_ids") and event.categ_ids:
            ical_event.add("categories", [cat.name for cat in event.categ_ids])

        if hasattr(event, "alarm_ids"):
            for alarm in event.alarm_ids:
                valarm = self._create_valarm(alarm)
                if valarm:
                    ical_event.add_component(valarm)

        if hasattr(event, "get_base_url"):
            base_url = event.get_base_url()
            ical_event.add(
                "url",
                f"{base_url}/web#id={event.id}&model=calendar.event&view_type=form",
            )

        ical_event.add("x-odoo-id", str(event.id))

        if event.write_date:
            modified_dt = event.write_date
            if not modified_dt.tzinfo:
                modified_dt = modified_dt.replace(tzinfo=UTC)
            ical_event.add("last-modified", modified_dt)

        if event.create_date:
            created_dt = event.create_date
            if not created_dt.tzinfo:
                created_dt = created_dt.replace(tzinfo=UTC)
            ical_event.add("created", created_dt)

        cal.add_component(ical_event)
        return cal.to_ical().decode("utf-8")

    def _html_to_text(self, html):
        if not html:
            return ""
        return html2plaintext(html)

    def _odoo_rrule_to_ical(self, event):
        if not event.rrule:
            return None

        try:
            return vRecur.from_ical(event.rrule)
        except ValueError as exc:
            _logger.warning("Failed to parse rrule for event %s: %s", event.id, exc)
            return None

    def _create_valarm(self, alarm):
        try:
            valarm = VAlarm()
            valarm.add("action", "DISPLAY")

            if alarm.name:
                valarm.add("description", alarm.name)

            if hasattr(alarm, "interval") and hasattr(alarm, "duration"):
                duration_value = alarm.duration
                if alarm.interval == "minutes":
                    delta = timedelta(minutes=-duration_value)
                elif alarm.interval == "hours":
                    delta = timedelta(hours=-duration_value)
                elif alarm.interval == "days":
                    delta = timedelta(days=-duration_value)
                else:
                    delta = timedelta(minutes=-duration_value)
                valarm.add("trigger", delta)

            return valarm
        except (TypeError, ValueError) as exc:
            _logger.warning("Failed to create VALARM: %s", exc)
            return None

    def ical_to_event_vals(self, ical_data, env=None):
        try:
            cal = Calendar.from_ical(ical_data)
        except Exception as exc:
            _logger.error("Failed to parse iCalendar: %s", exc)
            raise ValueError(f"Invalid iCalendar data: {exc}") from exc

        vals = {}
        component = next(
            (component for component in cal.walk() if component.name == "VEVENT"),
            None,
        )
        if component is None:
            return vals

        if "uid" in component:
            vals["ical_uid"] = str(component.get("uid"))

        if "summary" in component:
            vals["name"] = str(component.get("summary"))

        if "description" in component:
            vals["description"] = str(component.get("description"))

        if "location" in component:
            vals["location"] = str(component.get("location"))

        if "dtstart" in component:
            dtstart = component.get("dtstart")
            if hasattr(dtstart, "dt"):
                start = dtstart.dt
                if isinstance(start, datetime):
                    if start.tzinfo:
                        start = start.astimezone(UTC).replace(tzinfo=None)
                    vals["start"] = start
                    vals["allday"] = False
                else:
                    vals["start"] = datetime.combine(start, datetime.min.time())
                    vals["allday"] = True

        if "dtend" in component:
            dtend = component.get("dtend")
            if hasattr(dtend, "dt"):
                stop = dtend.dt
                if isinstance(stop, datetime):
                    if stop.tzinfo:
                        stop = stop.astimezone(UTC).replace(tzinfo=None)
                    vals["stop"] = stop
                else:
                    vals["stop"] = datetime.combine(
                        stop - timedelta(days=1), datetime.min.time()
                    )
        elif "duration" in component and "start" in vals:
            duration = component.get("duration")
            if hasattr(duration, "dt"):
                vals["stop"] = vals["start"] + duration.dt

        if "class" in component:
            class_val = str(component.get("class")).upper()
            privacy_map = {
                "PUBLIC": "public",
                "PRIVATE": "private",
                "CONFIDENTIAL": "confidential",
            }
            vals["privacy"] = privacy_map.get(class_val, "public")

        if "status" in component:
            if str(component.get("status")).upper() == "CANCELLED":
                vals["active"] = False

        if "transp" in component:
            transp = str(component.get("transp")).upper()
            vals["show_as"] = {"TRANSPARENT": "free", "OPAQUE": "busy"}.get(
                transp, "busy"
            )

        if "organizer" in component and env:
            organizer = component.get("organizer")
            if isinstance(organizer, str) and organizer.startswith("mailto:"):
                email = organizer[7:]
                user = (
                    env["res.users"]
                    .sudo()
                    .search([("partner_id.email", "=", email)], limit=1)
                )
                if user:
                    vals["user_id"] = user.id

        attendee_data = []
        if "attendee" in component:
            attendees = component.get("attendee")
            if not isinstance(attendees, list):
                attendees = [attendees]
            attendee_data.extend(
                {"email": attendee[7:], "partstat": "NEEDS-ACTION"}
                for attendee in attendees
                if isinstance(attendee, str) and attendee.startswith("mailto:")
            )

        if attendee_data and env:
            attendee_vals = []
            partstat_map = {
                "NEEDS-ACTION": "needsAction",
                "ACCEPTED": "accepted",
                "DECLINED": "declined",
                "TENTATIVE": "tentative",
            }
            partner_by_email = {}
            for partner in (
                env["res.partner"]
                .sudo()
                .search([("email", "in", [info["email"] for info in attendee_data])])
            ):
                partner_by_email.setdefault(partner.email, partner)
            for att_info in attendee_data:
                partner = partner_by_email.get(att_info["email"])
                if partner:
                    attendee_vals.append(
                        Command.create(
                            {
                                "partner_id": partner.id,
                                "state": partstat_map.get(
                                    att_info["partstat"], "needsAction"
                                ),
                            }
                        )
                    )
            if attendee_vals:
                vals["attendee_ids"] = attendee_vals

        if "rrule" in component:
            rrule = component.get("rrule")
            if rrule:
                vals["recurrency"] = True
                if hasattr(rrule, "to_ical"):
                    raw = rrule.to_ical()
                    vals["rrule"] = raw.decode() if isinstance(raw, bytes) else str(raw)
                else:
                    vals["rrule"] = str(rrule)

        if "categories" in component and env:
            categories = component.get("categories")
            if isinstance(categories, str):
                categories = [categories]
            elif hasattr(categories, "cats"):
                categories = categories.cats

            if categories:
                EventType = env["calendar.event.type"].sudo()
                names = list(dict.fromkeys(str(name) for name in categories))
                by_name = {}
                for event_type in EventType.search([("name", "in", names)]):
                    by_name.setdefault(event_type.name, event_type)
                missing = [name for name in names if name not in by_name]
                for event_type in EventType.create([{"name": n} for n in missing]):
                    by_name[event_type.name] = event_type
                vals["categ_ids"] = [Command.set([by_name[n].id for n in names])]

        if "sequence" in component:
            with contextlib.suppress(ValueError, TypeError):
                vals["sequence"] = int(component.get("sequence"))

        if "recurrence-id" in component:
            vals["_is_recurrence_exception"] = True

        if "x-odoo-id" in component:
            with contextlib.suppress(ValueError, TypeError):
                vals["_original_odoo_id"] = int(component.get("x-odoo-id"))

        return vals
