import logging

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.fields import NEGATIVE_CONDITION_OPERATORS, Domain
from odoo.tools import email_normalize

from odoo.addons.calendar_google.utils.google_event import GoogleEvent

_logger = logging.getLogger(__name__)


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
