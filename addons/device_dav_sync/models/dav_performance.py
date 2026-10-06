import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

_PREFETCH_FIELDS = {
    "res.partner": [
        "name",
        "display_name",
        "email",
        "phone_ids",
        "street",
        "street2",
        "city",
        "zip",
        "state_id",
        "country_id",
        "function",
        "website",
        "comment",
        "category_id",
        "is_company",
        "parent_id",
        "image_128",
        "write_date",
        "create_date",
        "vcard_uid",
        "vcard_etag",
    ],
    "calendar.event": [
        "name",
        "start",
        "stop",
        "allday",
        "location",
        "description",
        "user_id",
        "partner_ids",
        "attendee_ids",
        "categ_ids",
        "alarm_ids",
        "privacy",
        "show_as",
        "write_date",
        "create_date",
        "ical_uid",
        "ical_etag",
    ],
}


class DAVPerformance(models.AbstractModel):
    _name = "dav.performance"
    _description = "DAV Performance Optimization"

    @api.model
    def _get_sync_batch_size(self):
        raw = self.env.registry.settings.get(
            self.env, "device_dav_sync.sync_batch_size", default="100"
        )
        try:
            return max(1, int(raw))
        except TypeError, ValueError:
            return 100

    @api.model
    def _get_fields_prefetch(self, model_name):
        return _PREFETCH_FIELDS.get(model_name, [])

    @api.model
    def prefetch_for_serialization(self, records):
        if not records:
            return records
        fields = self._get_fields_prefetch(records._name)
        if fields:
            try:
                records.read(fields)
            except Exception:
                _logger.debug("Prefetch skipped for %s", records._name, exc_info=True)
        return records
