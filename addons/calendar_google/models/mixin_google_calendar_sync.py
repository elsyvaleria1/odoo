import logging

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.tools import email_normalize

from odoo.addons.calendar_google.utils.google_event import GoogleEvent

_logger = logging.getLogger(__name__)


class MixinGoogleCalendarSync(models.AbstractModel):
    _name = "mixin.google.calendar.sync"
    _description = "Synchronize a record with Google Calendar"

    active = fields.Boolean(default=True)

    def _google_links(self):
        """The Google links of these records, elevated: one per calendar holding
        a record, each under the record's one Google id."""
        fk = self.env["calendar.sync.link"]._field_of(self)
        return (
            self.env["calendar.sync.link"]
            ._engine()
            .search_fetch(
                [(fk, "in", self.ids), ("account_id.provider", "=", "google")],
                [fk, "account_id", "remote_id"],
            )
        )

    def _google_id(self) -> str | bool:
        """This record's id in Google, the same in every calendar holding it;
        False while Google does not hold it."""
        self.check_singleton()
        google_ids = set(self._google_links().mapped("remote_id")) - {False}
        if len(google_ids) > 1:
            raise ValueError(
                f"{self} is held by Google under several ids: {google_ids}"
            )
        return next(iter(google_ids), False)

    @api.model
    def _google_records(self, google_ids):
        """The records of this model Google holds under `google_ids`."""
        fk = self.env["calendar.sync.link"]._field_of(self)
        links = (
            self.env["calendar.sync.link"]
            ._engine()
            .search_fetch(
                [
                    ("remote_id", "in", list(google_ids)),
                    ("account_id.provider", "=", "google"),
                    (fk, "!=", False),
                ],
                [fk],
            )
        )
        return self.browse(links[fk].ids)

    def _google_link(self, account, google_ids) -> None:
        """Link records to their Google id in `account`'s calendar, given as
        {record id: Google id}."""
        fk = self.env["calendar.sync.link"]._field_of(self)
        self.env["calendar.sync.link"]._engine().create(
            [
                {"account_id": account.id, fk: record_id, "remote_id": google_id}
                for record_id, google_id in google_ids.items()
            ]
        )

    def _google_unlink(self) -> None:
        """These records forget their Google id."""
        self._google_links().unlink()

    def _google_link_instances(self) -> None:
        """Link the records Google identifies through another record's id."""

    def write(self, vals):
        result = super().write(vals)
        if "recurrence_id" in vals:
            self._google_link_instances()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._google_link_instances()
        return records

    def _prepare_post_sync_vals(self, request_values, google_values) -> ValuesType:
        """The values this record takes from Google's answer to its insert."""
        return {}

    def _is_video_call_required(self) -> bool:
        """Implement this method to return True if the event needs a video call
        :return: bool
        """
        self.check_singleton()
        return True

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

    def _get_fields_google_synced(self):
        """Return a set of field names. Changing one of these fields
        marks the record to be re-synchronized.
        """
        raise NotImplementedError
