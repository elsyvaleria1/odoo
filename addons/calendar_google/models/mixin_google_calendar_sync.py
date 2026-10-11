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
        self.check_singleton()
        google_ids = set(self._google_links().mapped("remote_id")) - {False}
        if len(google_ids) > 1:
            raise ValueError(
                f"{self} is held by Google under several ids: {google_ids}"
            )
        return next(iter(google_ids), False)

    @api.model
    def _google_records(self, google_ids):
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
        fk = self.env["calendar.sync.link"]._field_of(self)
        self.env["calendar.sync.link"]._engine().create(
            [
                {"account_id": account.id, fk: record_id, "remote_id": google_id}
                for record_id, google_id in google_ids.items()
            ]
        )

    def _google_unlink(self) -> None:
        self._google_links().unlink()

    def _google_link_instances(self) -> None:
        pass

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
        return {}

    def _write_from_google(self, gevent, vals) -> None:
        self.write(vals)

    @api.model
    def _create_from_google(self, gevents, vals_list):
        return self.create(vals_list)

    @api.model
    def _get_sync_partner(self, emails) -> dict:
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
        raise NotImplementedError

    def _google_values(self):
        raise NotImplementedError

    def _get_fields_google_synced(self):
        raise NotImplementedError
