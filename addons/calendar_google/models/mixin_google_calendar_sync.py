import logging
from contextlib import contextmanager
from functools import wraps
from typing import Self

from markupsafe import Markup
from requests import HTTPError

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.db import BaseCursor
from odoo.fields import NEGATIVE_CONDITION_OPERATORS, Domain
from odoo.modules.registry import Registry
from odoo.tools import email_normalize

from odoo.addons.calendar_google.utils.calendar_google import (
    TIMEOUT,
    GoogleCalendarService,
)
from odoo.addons.calendar_google.utils.google_event import GoogleEvent

_logger = logging.getLogger(__name__)


# API requests are sent to Google Calendar after the current transaction ends.
# This ensures changes are sent to Google only if they really happened in the Odoo database.
# It is particularly important for event creation , otherwise the event might be created
# twice in Google if the first creation crashed in Odoo.
def after_commit(func):
    @wraps(func)
    def wrapped(self, *args, **kwargs):
        assert isinstance(self.env.cr, BaseCursor)
        dbname = self.env.cr.dbname
        context = self.env.context
        uid = self.env.uid

        if self.env.context.get("no_calendar_sync"):
            return

        @self.env.cr.postcommit.add
        def called_after():
            db_registry = Registry(dbname)
            with db_registry.cursor() as cr:
                env = api.Environment(cr, uid, context)
                try:
                    func(self.with_env(env), *args, **kwargs)
                except Exception:
                    _logger.warning("Could not sync record now: %s", self)
                    _logger.exception("Sync error")

    return wrapped


@contextmanager
def google_calendar_connection(user):
    yield user._calendar_sync_connection("google")


class MixinGoogleCalendarSync(models.AbstractModel):
    _name = "mixin.google.calendar.sync"
    _description = "Synchronize a record with Google Calendar"

    google_id = fields.Char(
        string="Google Calendar Id",
        compute="_compute_google_id",
        inverse="_inverse_google_id",
        search="_search_google_id",
        copy=False,
    )
    need_sync = fields.Boolean(
        default=True,
        copy=False,
    )
    active = fields.Boolean(default=True)

    def _google_link_field(self) -> str:
        return "event_id" if self._name == "calendar.event" else "recurrence_id"

    def _google_links(self):
        """The Google links of these records, elevated: one per record, in the
        calendar of whoever gave it its Google id."""
        fk = self._google_link_field()
        return (
            self.env["calendar.sync.link"]
            ._engine()
            .search_fetch(
                [(fk, "in", self.ids), ("account_id.provider", "=", "google")],
                [fk, "account_id", "remote_id"],
            )
        )

    @api.depends("calendar_sync_link_ids.remote_id")
    def _compute_google_id(self) -> None:
        fk = self._google_link_field()
        remote_ids = {link[fk].id: link.remote_id for link in self._google_links()}
        for record in self:
            record.google_id = remote_ids.get(record.id, False)

    def _inverse_google_id(self) -> None:
        fk = self._google_link_field()
        links = self._google_links().grouped(fk)
        for record in self:
            link = links.get(record)
            if not record.google_id:
                if link:
                    link.unlink()
            elif link:
                link.remote_id = record.google_id
            else:
                self._google_link(
                    self.env["calendar.sync.account"]._for(self.env.user, "google"),
                    {record.id: record.google_id},
                )

    def _google_link(self, account, google_ids) -> None:
        """Link records to their Google id in `account`'s calendar, given as
        {record id: Google id}."""
        fk = self._google_link_field()
        self.env["calendar.sync.link"]._engine().create(
            [
                {"account_id": account.id, fk: record_id, "remote_id": google_id}
                for record_id, google_id in google_ids.items()
            ]
        )

    def _google_link_instances(self) -> None:
        """Link the records Google identifies through another record's id."""

    def _search_google_id(self, operator, value):
        fk = self._google_link_field()
        Link = self.env["calendar.sync.link"]._engine()
        google = Domain("account_id.provider", "=", "google")
        if operator == "=":
            operator, value = "in", [value]
        if operator in NEGATIVE_CONDITION_OPERATORS:
            return NotImplemented
        if operator != "in":
            return Domain(
                "id",
                "in",
                Link._search(google & Domain("remote_id", operator, value)).subselect(
                    fk
                ),
            )
        values = [v for v in value if v]
        domain = Domain.FALSE
        if values:
            domain |= Domain(
                "id",
                "in",
                Link._search(google & Domain("remote_id", "in", values)).subselect(fk),
            )
        if len(values) < len(value):
            domain |= Domain(
                "id",
                "not in",
                Link._search(google & Domain(fk, "!=", False)).subselect(fk),
            )
        return domain

    def write(self, vals):
        google_service = GoogleCalendarService(self.env)
        synced_fields = self._get_fields_google_synced()
        if (
            "need_sync" not in vals
            and vals.keys() & synced_fields
            and not self.env.user._calendar_sync_stopped("google")
        ):
            vals["need_sync"] = True

        result = super().write(vals)
        if "recurrence_id" in vals:
            self._google_link_instances()
        if self.env.user._calendar_sync_status("google") != "sync_paused":
            for record in self:
                if record.need_sync and record.google_id:
                    record.with_user(record._get_event_user())._google_patch(
                        google_service,
                        record.google_id,
                        record._google_values(),
                        timeout=3,
                    )

        return result

    @api.model_create_multi
    def create(self, vals_list):
        user_ids = {v["user_id"] for v in vals_list if v.get("user_id")}
        users_with_sync = (
            self.env["res.users"]
            .browse(user_ids)
            .filtered(lambda u: not u._calendar_sync_stopped("google"))
        )
        users_with_sync_set = set(users_with_sync.ids)

        for vals in vals_list:
            if (
                vals.get("user_id", False)
                and vals["user_id"] not in users_with_sync_set
            ):
                vals.update({"need_sync": False})
        records = super().create(vals_list)
        records._google_link_instances()
        self._handle_allday_recurrences_edge_case(records, vals_list)

        google_service = GoogleCalendarService(self.env)
        if self.env.user._calendar_sync_status("google") != "sync_paused":
            for record in records:
                if record.need_sync and record.active:
                    record.with_user(record._get_event_user())._google_insert(
                        google_service, record._google_values(), timeout=3
                    )
        return records

    def _handle_allday_recurrences_edge_case(self, records, vals_list) -> None:
        """
        When creating 'All Day' recurrent event, the first event is wrongly synchronized as
        a single event and then its recurrence creates a duplicated event. We must manually
        set the 'need_sync' attribute as False in order to avoid this unwanted behavior.
        """
        if vals_list and self._name == "calendar.event":
            forbid_sync = all(not vals.get("need_sync", True) for vals in vals_list)
            records_to_skip = records.filtered(
                lambda r: (
                    r.need_sync and r.allday and r.recurrency and not r.recurrence_id
                )
            )
            if forbid_sync and records_to_skip:
                records_to_skip.with_context(send_updates=False).need_sync = False

    def unlink(self):
        """We can't delete an event that is also in Google Calendar. Otherwise we would
        have no clue that the event must must deleted from Google Calendar at the next sync.
        """
        synced = self.filtered("google_id")
        # LUL TODO find a way to get rid of this context key
        if self.env.context.get("archive_on_error") and self._active_name:
            synced.write({self._active_name: False})
            self -= synced
        elif synced:
            # Since we can not delete such an event (see method comment), we archive it.
            # Notice that archiving an event will delete the associated event on Google.
            # Then, since it has been deleted on Google, the event is also deleted on Odoo DB (_sync_google2odoo).
            self.action_archive()
            return True
        return super().unlink()

    def _sync_odoo2google(self, google_service: GoogleCalendarService) -> None:
        if not self:
            return
        if self._active_name:
            records_to_sync = self.filtered(self._active_name)
        else:
            records_to_sync = self
        cancelled_records = self - records_to_sync

        updated_records = records_to_sync.filtered("google_id")
        new_records = records_to_sync - updated_records
        if self.env.user._calendar_sync_status("google") != "sync_paused":
            for record in cancelled_records:
                if record.google_id and record.need_sync:
                    record.with_user(record._get_event_user())._google_delete(
                        google_service, record.google_id
                    )
            for record in new_records:
                if record._is_google_insertion_blocked(sender_user=self.env.user):
                    continue
                record.with_user(record._get_event_user())._google_insert(
                    google_service, record._google_values()
                )
            for record in updated_records:
                record.with_user(record._get_event_user())._google_patch(
                    google_service, record.google_id, record._google_values()
                )

    def _google_error_handling(self, http_error) -> None:
        # We only handle the most problematic errors of sync events.
        if http_error.response.status_code in (403, 400):
            response = http_error.response.json()
            if not self.exists():
                reason = "Google gave the following explanation: %s" % response[
                    "error"
                ].get("message")
                error_log = (
                    "Error while syncing record. It does not exists anymore in the database. %s"
                    % reason
                )
                _logger.error(error_log)
                return

            if self._name == "calendar.event":
                start = (
                    self.start and self.start.strftime("%Y-%m-%d at %H:%M")
                ) or self.env._("undefined time")
                event_ids = self.id
                name = self.name
                error_log = "Error while syncing event: "
                event = self
            else:
                # calendar recurrence is triggering the error
                event = self.base_event_id or self._get_first_event(
                    include_outliers=True
                )
                start = (
                    event.start and event.start.strftime("%Y-%m-%d at %H:%M")
                ) or self.env._("undefined time")
                event_ids = self.env._(
                    "%(id)s and %(length)s following",
                    id=event.id,
                    length=len(self.calendar_event_ids.ids),
                )
                name = event.name
                # prevent to sync other events
                self.calendar_event_ids.need_sync = False
                error_log = f"Error while syncing recurrence [{self.id} - {self.name} - {self.rrule}]: "

            # We don't have right access on the event or the request paramaters were bad.
            # https://developers.google.com/calendar/v3/errors#403_forbidden_for_non-organizer
            if (
                http_error.response.status_code == 403
                and "forbiddenForNonOrganizer" in http_error.response.text
            ):
                reason = self.env._(
                    "you don't seem to have permission to modify this event on Google Calendar"
                )
            else:
                reason = self.env._(
                    "Google gave the following explanation: %s",
                    response["error"].get("message"),
                )

            error_log += (
                "The event (%(id)s - %(name)s at %(start)s) could not be synced. It will not be synced while "
                "it is not updated. Reason: %(reason)s"
            ) % {"id": event_ids, "start": start, "name": name, "reason": reason}
            _logger.warning(error_log)

            body = (
                self.env._(
                    "The following event could not be synced with Google Calendar."
                )
                + Markup("<br/>")
                + self.env._("It will not be synced as long at it is not updated.")
                + Markup("<br/>")
                + reason
            )

            if event:
                event.message_post(
                    body=body,
                    message_type="comment",
                    subtype_xmlid="mail.mt_note",
                )

    @after_commit
    def _google_delete(
        self, google_service: GoogleCalendarService, google_id, timeout=TIMEOUT
    ) -> None:
        with google_calendar_connection(self.env.user.sudo()) as connection:
            if connection:
                is_recurrence = self.env.context.get("is_recurrence", False)
                google_service.env = google_service.env(
                    context={
                        **google_service.env.context,
                        "is_recurrence": is_recurrence,
                    }
                )
                google_service.delete(google_id, connection=connection, timeout=timeout)
                # When the record has been deleted on our side, we need to delete it on google but we don't want
                # to raise an error because the record don't exists anymore.
                self.exists().with_context(
                    dont_notify=True, google_calendar_syncing=True
                ).need_sync = False

    @after_commit
    def _google_patch(
        self, google_service: GoogleCalendarService, google_id, values, timeout=TIMEOUT
    ) -> None:
        with google_calendar_connection(self.env.user.sudo()) as connection:
            if connection:
                try:
                    send_updates = not self._is_event_over()
                    google_service.env = google_service.env(
                        context={
                            **google_service.env.context,
                            "send_updates": send_updates,
                        }
                    )
                    google_service.patch(
                        google_id, values, connection=connection, timeout=timeout
                    )
                except HTTPError as e:
                    if e.response.status_code in (400, 403):
                        self._google_error_handling(e)
                if values:
                    self.exists().with_context(
                        dont_notify=True, google_calendar_syncing=True
                    ).need_sync = False

    def _prepare_post_sync_vals(self, request_values, google_values) -> ValuesType:
        """Return the values to be written in the event right after its insertion in Google side."""
        return {
            "google_id": request_values["id"],
            "need_sync": False,
        }

    def _is_video_call_required(self) -> bool:
        """Implement this method to return True if the event needs a video call
        :return: bool
        """
        self.check_singleton()
        return True

    @after_commit
    def _google_insert(
        self, google_service: GoogleCalendarService, values, timeout=TIMEOUT
    ) -> None:
        if not values:
            return
        with google_calendar_connection(self.env.user.sudo()) as connection:
            if connection:
                try:
                    send_updates = (
                        self.env.context.get("send_updates", True)
                        and not self._is_event_over()
                    )
                    google_service.env = google_service.env(
                        context={
                            **google_service.env.context,
                            "send_updates": send_updates,
                        }
                    )
                    google_values = google_service.insert(
                        values,
                        connection=connection,
                        timeout=timeout,
                        need_video_call=self._is_video_call_required(),
                    )
                    self.with_context(
                        dont_notify=True, google_calendar_syncing=True
                    ).write(self._prepare_post_sync_vals(values, google_values))
                except HTTPError as e:
                    if e.response.status_code in (400, 403):
                        self._google_error_handling(e)
                        self.with_context(
                            dont_notify=True, google_calendar_syncing=True
                        ).need_sync = False

    def _get_records_to_sync(self, full_sync=False) -> Self:
        """Return records that should be synced from Odoo to Google

        :param full_sync: If True, all events attended by the user are returned
        :return: events
        """
        domain = self._get_domain_sync()
        if not full_sync:
            is_active_clause = (
                Domain(self._active_name, "=", True)
                if self._active_name
                else Domain.TRUE
            )
            domain &= (Domain("google_id", "=", False) & is_active_clause) | Domain(
                "need_sync", "=", True
            )
        # We want to limit to 200 event sync per transaction, it shouldn't be a problem for the day to day
        # but it allows to run the first synchro within an acceptable time without timeout.
        # If there is a lot of event to synchronize to google the first time,
        # they will be synchronized eventually with the cron running few times a day
        return self.with_context(active_test=False).search(domain, limit=200)

    def _check_any_records_to_sync(self) -> bool:
        """Returns True if there are pending records to be synchronized from Odoo to Google, False otherwise."""
        is_active_clause = (
            Domain(self._active_name, "=", True) if self._active_name else Domain.TRUE
        )
        domain = self._get_domain_sync()
        domain &= (Domain("google_id", "=", False) & is_active_clause) | Domain(
            "need_sync", "=", True
        )
        return self.search_count(domain, limit=1) > 0

    def _write_from_google(self, gevent, vals) -> None:
        self.write(vals)

    @api.model
    def _create_from_google(self, gevents, vals_list):
        return self.create(vals_list)

    @api.model
    def _get_sync_partner(self, emails) -> dict:
        """Map each address in `emails` to its partner, keyed as Google spelled it.

        This returned a *recordset*, and both callers then walked it with
        `zip(emails, partners, google_attendees)`. That is only correct when the
        resolver gives back exactly one partner per address, in the order asked,
        and it guarantees neither: two attendees sharing an address collapse to
        one partner, and an address that normalises to nothing contributes none.
        Either shortens the recordset, and from the first gap onwards every
        attendee was handed the partner belonging to some other attendee --
        silently, because the `zip` passed `strict=False` and the sort key
        (`k.get(p.email_normalized, -1)`) compared a *normalised* address
        against a dict built from the raw ones, so anything Google spelled with
        a display name or different case sorted to the front rather than raising.

        A mapping has no positions to misalign. An address with no partner maps
        to an empty recordset, which is the answer, not a missing row.
        """
        normalized = {email: email_normalize(email) for email in emails}
        partners = self.env[
            "mixin.mail.thread"
        ]._partner_get_or_create_from_emails_single(
            list({norm for norm in normalized.values() if norm})
        )
        by_normalized = {partner.email_normalized: partner for partner in partners}
        empty = self.env["res.partner"]
        return {
            email: by_normalized.get(norm, empty) for email, norm in normalized.items()
        }

    @api.model
    def _odoo_values(self, google_event: GoogleEvent, default_reminders=()):
        """Implements this method to return a dict of Odoo values corresponding
        to the Google event given as parameter
        :return: dict of Odoo formatted values
        """
        raise NotImplementedError

    def _google_values(self):
        """Implements this method to return a dict with values formatted
        according to the Google Calendar API
        :return: dict of Google formatted values
        """
        raise NotImplementedError

    def _get_domain_sync(self):
        """Return a domain used to search records to synchronize.
        e.g. return a domain to synchronize records owned by the current user.
        """
        raise NotImplementedError

    def _get_fields_google_synced(self):
        """Return a set of field names. Changing one of these fields
        marks the record to be re-synchronized.
        """
        raise NotImplementedError

    @api.model
    def _restart_google_sync(self):
        """Turns on the google synchronization for all the events of
        a given user.
        """
        raise NotImplementedError

    def _get_event_user(self):
        """Return the correct user to send the request to Google.
        It's possible that a user creates an event and sets another user as the organizer. Using self.env.user will
        cause some issues, and It might not be possible to use this user for sending the request, so this method gets
        the appropriate user accordingly.
        """
        raise NotImplementedError

    def _is_google_insertion_blocked(self, sender_user) -> bool:
        """
        Returns True if the record insertion to Google should be blocked.
        This is a necessary step for ensuring data match between Odoo and Google,
        as it avoids that events have permanently the wrong organizer in Google
        by not synchronizing records through owner and not through the attendees.
        """
        raise NotImplementedError
