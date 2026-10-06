import hashlib
import logging
import uuid

from odoo import Command, api, fields, models

from ..lib.vcard_builder import VCardBuilder
from ..lib.webdav_utils import store_dav_record

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    vcard_etag = fields.Char(
        compute="_compute_vcard_etag",
        store=True,
        help="Entity tag for CardDAV synchronization (unquoted SHA-256 hash)",
    )
    vcard_uid = fields.Char(
        index=True,
        copy=False,
        help="Unique identifier for vCard synchronization (RFC 6350). "
        "Auto-generated on creation if not provided. Multiple NULL values are allowed.",
    )

    _vcard_uid_unique = models.Constraint(
        "UNIQUE(vcard_uid)",
        "vCard UID must be unique across all contacts!",
    )

    @api.depends("write_date", "create_date")
    def _compute_vcard_etag(self) -> None:
        for partner in self:
            timestamp = partner.write_date or partner.create_date
            content = f"res.partner-{partner.id}-{timestamp}"
            partner.vcard_etag = hashlib.sha256(content.encode()).hexdigest()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("vcard_uid"):
                vals["vcard_uid"] = f"{uuid.uuid4()}@odoo"

        return super().create(vals_list)

    @api.model
    def _filter_vcard_vals(self, vals) -> dict:
        return {key: value for key, value in vals.items() if key in self._fields}

    def to_vcard(self):
        self.check_singleton()
        try:
            builder = VCardBuilder()
            return builder.partner_to_vcard(self)
        except Exception:
            _logger.exception("Failed to convert partner %s to vCard", self.id)
            raise

    @api.model
    def create_from_vcard(self, vcard_data, user_id=None):
        builder = VCardBuilder()
        vals = self._filter_vcard_vals(
            builder.vcard_to_partner_vals(vcard_data, env=self.env)
        )
        if user_id and self._has_field_access(self._fields["user_id"], "write"):
            vals["user_id"] = user_id
        return store_dav_record(self.env, lambda: self.create(vals))

    def from_vcard(self, vcard_data) -> None:
        self.check_singleton()
        builder = VCardBuilder()
        vals = self._filter_vcard_vals(
            builder.vcard_to_partner_vals(vcard_data, env=self.env)
        )
        vals.pop("vcard_uid", None)
        if "phone_ids" in vals:
            vals["phone_ids"] = [Command.clear(), *vals["phone_ids"]]
        store_dav_record(self.env, lambda: self.write(vals))
