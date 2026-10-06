import hashlib
import logging
import uuid

from odoo import api, fields, models

from ..lib.ical_builder import ICalBuilder
from ..lib.webdav_utils import store_dav_record

_logger = logging.getLogger(__name__)


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    ical_etag = fields.Char(
        compute="_compute_ical_etag",
        store=True,
        help="Entity tag for CalDAV synchronization (unquoted SHA-256 hash)",
    )
    ical_uid = fields.Char(
        index=True,
        copy=False,
        help="Unique identifier for iCalendar synchronization (RFC 5545). "
        "Auto-generated on creation if not provided. Multiple NULL values are allowed.",
    )

    _ical_uid_unique = models.Constraint(
        "UNIQUE(ical_uid)",
        "iCalendar UID must be unique across all events!",
    )

    @api.depends("write_date", "create_date")
    def _compute_ical_etag(self) -> None:
        for event in self:
            timestamp = event.write_date or event.create_date
            content = f"calendar.event-{event.id}-{timestamp}"
            event.ical_etag = hashlib.sha256(content.encode()).hexdigest()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("ical_uid"):
                vals["ical_uid"] = f"{uuid.uuid4()}@odoo"

        return super().create(vals_list)

    @api.model
    def _filter_ical_vals(self, vals) -> dict:
        vals.pop("recurrency", None)
        vals.pop("rrule", None)
        return {
            key: value
            for key, value in vals.items()
            if not key.startswith("_") and key in self._fields
        }

    def to_icalendar(self):
        self.check_singleton()
        try:
            builder = ICalBuilder()
            return builder.event_to_ical(self)
        except Exception:
            _logger.exception("Failed to convert event %s to iCalendar", self.id)
            raise

    @api.model
    def create_from_icalendar(self, ical_data, user_id=None):
        builder = ICalBuilder()
        vals = self._filter_ical_vals(
            builder.ical_to_event_vals(ical_data, env=self.env)
        )
        if user_id:
            vals["user_id"] = user_id
        return store_dav_record(self.env, lambda: self.create(vals))

    def from_icalendar(self, ical_data) -> None:
        self.check_singleton()
        builder = ICalBuilder()
        vals = self._filter_ical_vals(
            builder.ical_to_event_vals(ical_data, env=self.env)
        )
        vals.pop("ical_uid", None)
        store_dav_record(self.env, lambda: self.write(vals))
