import logging
import re
from datetime import UTC, datetime
from typing import Self

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.datetime import timezone
from odoo.tools import email_normalize

from odoo.addons.base.models.mixin_recurrence_rrule import (
    MAX_RECURRENT_OCCURRENCES,
)

ATTENDEE_CONVERTER_O2M = {
    "needsAction": "notresponded",
    "tentative": "tentativelyaccepted",
    "declined": "declined",
    "accepted": "accepted",
}
ATTENDEE_CONVERTER_M2O = {
    "none": "needsAction",
    "notResponded": "needsAction",
    "tentativelyAccepted": "tentative",
    "declined": "declined",
    "accepted": "accepted",
    "organizer": "accepted",
}
VIDEOCALL_URL_PATTERNS = (r"https://teams.microsoft.com",)

_logger = logging.getLogger(__name__)


class CalendarEvent(models.Model):
    _name = "calendar.event"
    _inherit = ["calendar.event", "mixin.microsoft.calendar.sync"]

    @api.model
    def _get_fields_microsoft_synced(self):
        return {
            "name",
            "description",
            "allday",
            "start",
            "date_end",
            "stop",
            "user_id",
            "privacy",
            "attendee_ids",
            "alarm_ids",
            "location",
            "show_as",
            "active",
            "videocall_location",
        }

    def _check_microsoft_sync_status(self):
        """
        Returns True if synchronization with Outlook Calendar is active and False otherwise.
        The user's Microsoft synchronization must not be stopped and Outlook account must be connected.
        """
        outlook_connected = self.env.user._calendar_sync_connection("microsoft")
        return outlook_connected and not self.env.user._calendar_sync_stopped(
            "microsoft"
        )

    @api.model_create_multi
    def create(self, vals_list):
        notify_context = self.env.context.get("dont_notify", False)

        # Forbid recurrence creation in Odoo, suggest its creation in Outlook due to the spam limitation.
        recurrency_in_batch = any(vals.get("recurrency") for vals in vals_list)
        if (
            self._check_microsoft_sync_status()
            and not self._calendar_applying()
            and recurrency_in_batch
        ):
            self._forbid_recurrence_creation()

        vals_check_organizer = self._get_organizer_validation_conditions(vals_list)
        for vals in [
            vals
            for vals, check_organizer in zip(
                vals_list, vals_check_organizer, strict=True
            )
            if check_organizer
        ]:
            # If event has a different organizer, check its sync status and verify if the user is listed as attendee.
            sender_user, partner_ids = self._get_organizer_user_change_info(vals)
            partner_included = (
                partner_ids
                and len(partner_ids) > 0
                and sender_user.partner_id.id in partner_ids
            )
            self._check_organizer_validation(sender_user, partner_included)

        return super(
            CalendarEvent, self.with_context(dont_notify=notify_context)
        ).create(vals_list)

    def _check_organizer_validation(self, sender_user, partner_included) -> None:
        """Check if the proposed event organizer can be set accordingly."""
        # Edge case: events created or updated from Microsoft should not check organizer validation.
        change_from_microsoft = self._microsoft_applying()
        if sender_user and sender_user != self.env.user and not change_from_microsoft:
            current_sync_status = self._check_microsoft_sync_status()
            sender_sync_status = self.with_user(
                sender_user
            )._check_microsoft_sync_status()
            if not sender_sync_status and current_sync_status:
                raise ValidationError(
                    self.env._(
                        "For having a different organizer in your event, it is necessary that "
                        "the organizer have its Odoo Calendar synced with Outlook Calendar."
                    )
                )
            if sender_sync_status and not partner_included:
                raise ValidationError(
                    self.env._(
                        "It is necessary adding the proposed organizer as attendee before saving the event."
                    )
                )

    def _check_recurrence_overlapping(self, new_start) -> None:
        """
        Outlook does not allow to modify time fields of an event if this event crosses
        or overlaps the recurrence. In this case a 400 error with the Outlook code "ErrorOccurrenceCrossingBoundary"
        is returned. That means that the update violates the following Outlook restriction on recurrence exceptions:
        an occurrence cannot be moved to or before the day of the previous occurrence, and cannot be moved to or after
        the day of the following occurrence.
        For example: E1 E2 E3 E4 cannot becomes E1 E3 E2 E4
        """
        before_count = len(
            self.recurrence_id.calendar_event_ids.filtered(
                lambda e: e.start.date() < self.start.date() and e != self
            )
        )
        after_count = len(
            self.recurrence_id.calendar_event_ids.filtered(
                lambda e: (
                    e.start.date() < fields.Datetime.to_datetime(new_start).date()
                    and e != self
                )
            )
        )
        if before_count != after_count:
            raise UserError(
                self.env._(
                    "Outlook limitation: in a recurrence, an event cannot be moved to or before the day of the "
                    "previous event, and cannot be moved to or after the day of the following event."
                )
            )

    def _filtered_matching_timeslot(self, start, stop, allday) -> Self:
        return self.filtered(lambda e: e._is_matching_timeslot(start, stop, allday))

    def _is_matching_timeslot(self, start, stop, allday) -> bool:
        """
        Check if an event matches with the provided timeslot
        """
        self.check_singleton()

        event_start, event_stop = self._range()
        if allday:
            event_start = datetime(
                event_start.year, event_start.month, event_start.day, 0, 0
            )
            event_stop = datetime(
                event_stop.year, event_stop.month, event_stop.day, 0, 0
            )

        return (event_start, event_stop) == (start, stop)

    def _forbid_recurrence_update(self) -> None:
        """
        Suggest user to update recurrences in Outlook due to the Outlook Calendar spam limitation.
        """
        error_msg = self.env._(
            "Due to an Outlook Calendar limitation, recurrence updates must be done directly in Outlook Calendar."
        )
        if self - self._microsoft_held():
            # If any event is not synced, suggest deleting it in Odoo and recreating it in Outlook.
            error_msg = self.env._(
                "Due to an Outlook Calendar limitation, recurrence updates must be done directly in Outlook Calendar.\n"
                "If this recurrence is not shown in Outlook Calendar, you must delete it in Odoo Calendar and recreate it in Outlook Calendar."
            )

        raise UserError(error_msg)

    def _forbid_recurrence_creation(self) -> None:
        """
        Suggest user to update recurrences in Outlook due to the Outlook Calendar spam limitation.
        """
        raise UserError(
            self.env._(
                "Due to an Outlook Calendar limitation, recurrent events must be created directly in Outlook Calendar."
            )
        )

    def write(self, vals):
        values = vals
        recurrence_update_setting = values.get("recurrence_update")
        notify_context = self.env.context.get("dont_notify", False)

        # Forbid recurrence updates through Odoo and suggest user to update it in Outlook.
        if self._check_microsoft_sync_status():
            recurrency_in_batch = self.filtered(lambda ev: ev.recurrency)
            recurrence_update_attempt = (
                recurrence_update_setting
                or "recurrency" in values
                or (recurrency_in_batch and len(recurrency_in_batch) > 0)
            )
            if (
                not self._calendar_applying()
                and recurrence_update_attempt
                and "active" not in values
            ):
                self._forbid_recurrence_update()

        # When changing the organizer, check its sync status and verify if the user is listed as attendee.
        # Updates from Microsoft must skip this check since changing the organizer on their side is not possible.
        change_from_microsoft = self._microsoft_applying()
        deactivated_events_ids = []
        new_user_id = values.get("user_id")
        held = self._microsoft_held() if new_user_id else self.browse()
        for event in held:
            if event.user_id.id != new_user_id and not change_from_microsoft:
                sender_user, partner_ids = event._get_organizer_user_change_info(values)
                partner_included = (
                    sender_user.partner_id in event.attendee_ids.partner_id
                    or sender_user.partner_id.id in partner_ids
                )
                event._check_organizer_validation(sender_user, partner_included)
                event._recreate_event_different_organizer(values, sender_user)
                deactivated_events_ids.append(event.id)

        # check a Outlook limitation in overlapping the actual recurrence
        if recurrence_update_setting == "this" and "start" in values:
            self._check_recurrence_overlapping(values["start"])

        # a single event becoming the base of a series leaves Outlook: the
        # series is what Outlook holds of it now
        if values.get("recurrency"):
            self.filtered(
                lambda event: not event.recurrency and not event.recurrence_id
            )._microsoft_tombstone()

        deactivated_events = self.browse(deactivated_events_ids)
        # Update attendee status before 'values' variable is overridden in super.
        attendee_ids = values.get("attendee_ids")
        if attendee_ids and values.get("partner_ids"):
            (self - deactivated_events)._update_attendee_status(attendee_ids)

        res = super(
            CalendarEvent,
            (self - deactivated_events).with_context(dont_notify=notify_context),
        ).write(values)

        # Deactivate events that were recreated after changing organizer.
        if deactivated_events:
            res |= super(
                CalendarEvent,
                deactivated_events.with_context(dont_notify=notify_context),
            ).write({"active": False})
        return res

    def unlink(self):
        # Forbid recurrent events unlinking from calendar list view with sync active.
        if self and self._check_microsoft_sync_status():
            synced_events = self._microsoft_held()
            change_from_microsoft = self._microsoft_applying()
            recurrence_deletion = any(
                ev.recurrency and ev.recurrence_id and ev.follow_recurrence
                for ev in synced_events
            )
            if not change_from_microsoft and recurrence_deletion:
                self._forbid_recurrence_update()
        return super().unlink()

    def _recreate_event_different_organizer(self, values, sender_user) -> None:
        """Copy current event values, delete it and recreate it with the new organizer user."""
        self.check_singleton()
        self.env["calendar.event"].with_user(sender_user).with_context(
            skip_contact_description=True
        ).create({**self.copy_data()[0], **values})

    @api.model
    def _get_organizer_user_change_info(self, values) -> tuple:
        """Return the sender user of the event and the partner ids listed on the event values."""
        sender_user_id = values.get("user_id")
        if not sender_user_id:
            sender_user_id = self.env.user.id
        sender_user = self.env["res.users"].browse(sender_user_id)
        attendee_values = (
            self._attendees_values(values["partner_ids"])
            if "partner_ids" in values
            else []
        )
        partner_ids = []
        if attendee_values:
            partner_ids.extend(
                command[2].get("partner_id")
                for command in attendee_values
                if len(command) == 3 and isinstance(command[2], dict)
            )
        return sender_user, partner_ids

    def _update_attendee_status(self, attendee_ids) -> None:
        """Merge current status from 'attendees_ids' with new attendees values for avoiding their info loss in write().
        Create a dict getting the state of each attendee received from 'attendee_ids' variable and then update their state.
        :param attendee_ids: List of attendee commands carrying a dict with 'partner_id' and 'state' keys in its third position.
        """
        state_by_partner = {}
        for cmd in attendee_ids:
            if (
                len(cmd) == 3
                and isinstance(cmd[2], dict)
                and all(key in cmd[2] for key in ["partner_id", "state"])
            ):
                state_by_partner[cmd[2]["partner_id"]] = cmd[2]["state"]
        for attendee in self.attendee_ids:
            state_update = state_by_partner.get(attendee.partner_id.id)
            if state_update:
                attendee.state = state_update

    def action_mass_archive(self, recurrence_update_setting) -> None:
        # Do not allow archiving if recurrence is synced with Outlook. Suggest updating directly from Outlook.
        self.check_singleton()
        if self._check_microsoft_sync_status() and self._microsoft_held():
            self._forbid_recurrence_update()
        super().action_mass_archive(recurrence_update_setting)

    @api.model
    def _microsoft_to_odoo_values(self, microsoft_event, event=None):
        if microsoft_event.is_cancelled():
            return {"active": False}

        sensitivity_o2m = {
            "normal": "public",
            "private": "private",
            "confidential": "confidential",
        }

        event = event or self.browse()
        commands_attendee, commands_partner = self._odoo_attendee_commands_m(
            microsoft_event, event
        )
        timeZone_start = timezone(microsoft_event.start.get("timeZone"))
        timeZone_stop = timezone(microsoft_event.end.get("timeZone"))
        start = (
            parse(microsoft_event.start.get("dateTime"))
            .astimezone(timeZone_start)
            .replace(tzinfo=None)
        )
        if microsoft_event.isAllDay:
            stop = parse(microsoft_event.end.get("dateTime")).astimezone(
                timeZone_stop
            ).replace(tzinfo=None) - relativedelta(days=1)
        else:
            stop = (
                parse(microsoft_event.end.get("dateTime"))
                .astimezone(timeZone_stop)
                .replace(tzinfo=None)
            )
        values = {
            "name": microsoft_event.subject or self.env._("(No title)"),
            "description": microsoft_event.body and microsoft_event.body["content"],
            "location": (
                microsoft_event.location and microsoft_event.location.get("displayName")
            )
            or False,
            "user_id": microsoft_event.owner_id(self.env),
            "privacy": sensitivity_o2m.get(microsoft_event.sensitivity, False),
            "attendee_ids": commands_attendee,
            "allday": microsoft_event.isAllDay,
            "start": start,
            "stop": stop,
            "show_as": "free" if microsoft_event.showAs == "free" else "busy",
            "recurrency": microsoft_event.is_recurrent(),
        }
        if commands_partner:
            # Add partner_commands only if set from Microsoft. The write method on calendar_events will
            # override attendee commands if the partner_ids command is set but empty.
            values["partner_ids"] = commands_partner

        if microsoft_event.is_recurrent() and not microsoft_event.is_recurrence():
            # Propagate the follow_recurrence according to the Outlook result
            values["follow_recurrence"] = not microsoft_event.is_recurrence_outlier()

        # if a videocall URL is provided with the Outlook event, use it
        if microsoft_event.isOnlineMeeting and microsoft_event.onlineMeeting.get(
            "joinUrl"
        ):
            values["videocall_location"] = microsoft_event.onlineMeeting["joinUrl"]
        # if a location is a URL matching a specific pattern (i.e a URL to access to a videocall),
        # copy it in the 'videocall_location' instead
        elif values["location"] and any(
            re.match(p, values["location"]) for p in VIDEOCALL_URL_PATTERNS
        ):
            values["videocall_location"] = values["location"]
            values["location"] = False

        alarm_commands = self._odoo_reminders_commands_m(microsoft_event, event)
        if alarm_commands:
            values["alarm_ids"] = alarm_commands

        return values

    @api.model
    def _microsoft_to_odoo_recurrence_values(
        self, microsoft_event, default_values=None
    ):
        timeZone_start = timezone(microsoft_event.start.get("timeZone"))
        timeZone_stop = timezone(microsoft_event.end.get("timeZone"))
        start = (
            parse(microsoft_event.start.get("dateTime"))
            .astimezone(timeZone_start)
            .replace(tzinfo=None)
        )
        if microsoft_event.isAllDay:
            stop = parse(microsoft_event.end.get("dateTime")).astimezone(
                timeZone_stop
            ).replace(tzinfo=None) - relativedelta(days=1)
        else:
            stop = (
                parse(microsoft_event.end.get("dateTime"))
                .astimezone(timeZone_stop)
                .replace(tzinfo=None)
            )
        values = default_values or {}
        values.update({"start": start, "stop": stop})
        return values

    @api.model
    def _odoo_attendee_commands_m(self, microsoft_event, event) -> tuple:
        commands_attendee = []
        commands_partner = []

        microsoft_attendees = [
            a
            for a in microsoft_event.attendees or []
            if email_normalize(a.get("emailAddress").get("address"))
        ]
        emails = [a.get("emailAddress").get("address") for a in microsoft_attendees]
        existing_attendees = self.env["calendar.attendee"]
        if event:
            existing_attendees = event.attendee_ids.filtered(
                lambda attendee: attendee.email in emails
            )
        elif self.env.user.partner_id.email not in emails:
            commands_attendee += [
                Command.create(
                    {"state": "accepted", "partner_id": self.env.user.partner_id.id}
                )
            ]
            commands_partner += [Command.link(self.env.user.partner_id.id)]
        partners = self.env[
            "mixin.mail.thread"
        ]._partner_get_or_create_from_emails_single(emails, no_create=False)
        attendees_by_emails = {a.email: a for a in existing_attendees}
        partners_by_emails = {p.email_normalized: p for p in partners}
        for email, attendee_info in zip(emails, microsoft_attendees, strict=True):
            partner = partners_by_emails.get(
                email_normalize(email) or email, self.env["res.partner"]
            )
            # Responses from external invitations are stored in the 'responseStatus' field.
            # This field only carries the current user's event status because Microsoft hides other user's status.
            if self.env.user.email == email and microsoft_event.responseStatus:
                attendee_microsoft_status = microsoft_event.responseStatus.get(
                    "response", "none"
                )
            elif microsoft_event.isOrganizer is False and email in attendees_by_emails:
                # an attendee's copy says none for the others' answers, which
                # Outlook tracks on the organizer's item alone: Odoo's stand
                continue
            else:
                attendee_microsoft_status = attendee_info.get("status").get("response")
            state = ATTENDEE_CONVERTER_M2O.get(attendee_microsoft_status, "needsAction")

            if email in attendees_by_emails:
                # Update existing attendees
                commands_attendee += [
                    Command.update(attendees_by_emails[email].id, {"state": state})
                ]
            elif partner:
                # Create new attendees
                commands_attendee += [
                    Command.create({"state": state, "partner_id": partner.id})
                ]
                commands_partner += [Command.link(partner.id)]
                if attendee_info.get("emailAddress").get("name") and not partner.name:
                    partner.name = attendee_info.get("emailAddress").get("name")
        for odoo_attendee in attendees_by_emails.values():
            # Remove old attendees
            if odoo_attendee.email not in emails:
                commands_attendee += [Command.delete(odoo_attendee.id)]
                commands_partner += [Command.unlink(odoo_attendee.partner_id.id)]
        return commands_attendee, commands_partner

    @api.model
    def _odoo_reminders_commands_m(self, microsoft_event, event):
        reminders_commands = []
        if microsoft_event.isReminderOn:
            event_id = event
            alarm_type_label = self.env._("Notification")

            minutes = microsoft_event.reminderMinutesBeforeStart or 0
            alarm = self.env["calendar.alarm"].search(
                [
                    ("alarm_type", "=", "notification"),
                    ("duration_minutes", "=", minutes),
                ],
                limit=1,
            )
            if alarm and alarm not in event_id.alarm_ids:
                reminders_commands = [Command.link(alarm.id)]
            elif not alarm:
                if minutes == 0:
                    interval = "minutes"
                    duration = minutes
                    name = self.env._("%s - At time of event", alarm_type_label)
                elif minutes % (60 * 24) == 0:
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
                reminders_commands = [
                    Command.create(
                        {
                            "duration": duration,
                            "interval": interval,
                            "name": name,
                            "alarm_type": "notification",
                        }
                    )
                ]

            alarm_to_rm = event_id.alarm_ids.filtered(
                lambda a: a.alarm_type == "notification" and a.id != alarm.id
            )
            if alarm_to_rm:
                reminders_commands += [Command.unlink(a.id) for a in alarm_to_rm]

        else:
            event_id = event
            alarm_to_rm = event_id.alarm_ids.filtered(
                lambda a: a.alarm_type == "notification"
            )
            if alarm_to_rm:
                reminders_commands = [Command.unlink(a.id) for a in alarm_to_rm]
        return reminders_commands

    def _get_attendee_status_o2m(self, attendee):
        if self.user_id and self.user_id == attendee.partner_id.user_id:
            return "organizer"
        return ATTENDEE_CONVERTER_O2M.get(attendee.state, "None")

    def _microsoft_values(
        self, fields_to_sync, initial_values=(), series_master_id=None
    ):
        values = dict(initial_values)
        if not fields_to_sync:
            return values

        if series_master_id and "type" not in values:
            values["seriesMasterId"] = series_master_id
            values["type"] = "exception"

        if "name" in fields_to_sync:
            values["subject"] = self.name or ""

        if "description" in fields_to_sync:
            values["body"] = {
                "content": self._get_customer_description(),
                "contentType": "html",
            }

        if any(x in fields_to_sync for x in ["allday", "start", "date_end", "stop"]):
            if self.allday:
                start = {
                    "dateTime": self.start_date.isoformat(),
                    "timeZone": "Europe/London",
                }
                end = {
                    "dateTime": (self.stop_date + relativedelta(days=1)).isoformat(),
                    "timeZone": "Europe/London",
                }
            else:
                start = {
                    "dateTime": self.start.replace(tzinfo=UTC).isoformat(),
                    "timeZone": "Europe/London",
                }
                end = {
                    "dateTime": self.stop.replace(tzinfo=UTC).isoformat(),
                    "timeZone": "Europe/London",
                }

            values["start"] = start
            values["end"] = end
            values["isAllDay"] = self.allday

        if "location" in fields_to_sync:
            values["location"] = {"displayName": self.location or ""}

        if (
            not self.location
            and "videocall_location" in fields_to_sync
            and self._is_video_call_required()
        ):
            values["isOnlineMeeting"] = True
            values["onlineMeetingProvider"] = "teamsForBusiness"
        else:
            values["isOnlineMeeting"] = False

        if "alarm_ids" in fields_to_sync:
            alarm_id = self.alarm_ids.filtered(
                lambda a: a.alarm_type == "notification"
            )[:1]
            values["isReminderOn"] = bool(alarm_id)
            values["reminderMinutesBeforeStart"] = alarm_id.duration_minutes

        if "user_id" in fields_to_sync:
            values["organizer"] = {
                "emailAddress": {
                    "address": self.user_id.email or "",
                    "name": self.user_id.display_name or "",
                }
            }
            values["isOrganizer"] = self.user_id == self.env.user

        if "attendee_ids" in fields_to_sync:
            attendees = self.attendee_ids.filtered(
                lambda att: att.partner_id not in self.user_id.partner_id
            )
            values["attendees"] = [
                {
                    "emailAddress": {
                        "address": attendee.email or "",
                        "name": attendee.display_name or "",
                    },
                    "status": {"response": self._get_attendee_status_o2m(attendee)},
                }
                for attendee in attendees
            ]

        if "privacy" in fields_to_sync or "show_as" in fields_to_sync:
            values["showAs"] = self.show_as
            sensitivity_o2m = {
                "public": "normal",
                "private": "private",
                "confidential": "confidential",
            }
            # Set default privacy in event according to the organizer's calendar default privacy if defined.
            if self.user_id:
                sensitivity_o2m[False] = sensitivity_o2m.get(
                    self.user_id.calendar_default_privacy
                )
            else:
                sensitivity_o2m[False] = "normal"
            values["sensitivity"] = sensitivity_o2m.get(self.privacy)

        if "active" in fields_to_sync and not self.active:
            values["isCancelled"] = True

        if values.get("type") == "seriesMaster":
            recurrence = self.recurrence_id
            pattern = recurrence._get_microsoft_pattern()
            dtstart = recurrence.dtstart or fields.Datetime.now()
            rule_range = {"startDate": (dtstart.date()).isoformat()}

            if recurrence.repeat_type == "count":  # e.g. stop after X occurence
                rule_range["numberOfOccurrences"] = min(
                    recurrence.repeat_number, MAX_RECURRENT_OCCURRENCES
                )
                rule_range["type"] = "numbered"
            elif recurrence.repeat_type == "forever":
                rule_range["numberOfOccurrences"] = MAX_RECURRENT_OCCURRENCES
                rule_range["type"] = "numbered"
            elif recurrence.repeat_type == "until":  # e.g. stop after 12/10/2020
                rule_range["endDate"] = recurrence.repeat_until.isoformat()
                rule_range["type"] = "endDate"

            values["recurrence"] = {"pattern": pattern, "range": rule_range}

        return values

    def _microsoft_refusal(self):
        self.check_singleton()
        unreachable = self.attendee_ids.partner_id.filtered(
            lambda partner: not partner.email
        )
        if not unreachable:
            return None
        return self.env._(
            "Outlook needs an email address for every attendee; %(attendees)s "
            "have none.",
            attendees=", ".join(unreachable.mapped("display_name")),
        )
