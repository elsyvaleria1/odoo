from collections import defaultdict

from odoo import api, fields, models

from odoo.addons.base.models.mixin_format_address import ADDRESS_FIELDS
from odoo.addons.base.models.res_partner import POSITION_FIELDS


class ResPartner(models.Model):
    _inherit = "res.partner"

    contact_address_complete = fields.Char(
        compute="_compute_contact_address_complete",
        store=True,
    )

    @api.model
    def _address_fields(self):
        return super()._address_fields() + list(POSITION_FIELDS)

    @api.model
    def _formatting_address_fields(self):
        return [
            field
            for field in super()._formatting_address_fields()
            if field not in POSITION_FIELDS
        ]

    @api.model
    def update_latitude_longitude(self, partners) -> dict:
        coordinates_by_id = {}
        for entry in partners:
            position = self._get_partner_position(entry)
            if position:
                coordinates_by_id[entry["id"]] = position

        readable_partners = self.browse(list(coordinates_by_id)).exists()
        readable_partners.check_access("read")
        if self.env.user._is_internal():
            readable_partners = readable_partners.sudo()

        ids_by_position = defaultdict(list)
        for partner in readable_partners:
            ids_by_position[coordinates_by_id[partner.id]].append(partner.id)
        for (latitude, longitude), partner_ids in ids_by_position.items():
            readable_partners.browse(partner_ids).write(
                {
                    "partner_latitude": latitude,
                    "partner_longitude": longitude,
                }
            )
        return {}

    @api.model
    def _get_partner_position(self, entry) -> tuple | None:
        if not isinstance(entry, dict):
            return None
        if not isinstance(entry.get("id"), int) or isinstance(entry["id"], bool):
            return None
        latitude = entry.get("partner_latitude")
        longitude = entry.get("partner_longitude")
        for value in (latitude, longitude):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return None
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            return None
        return float(latitude), float(longitude)

    @api.onchange(*ADDRESS_FIELDS)
    def _onchange_address(self) -> None:
        self.partner_latitude = False
        self.partner_longitude = False

    @api.depends(*ADDRESS_FIELDS, "state_id.name", "country_id.name")
    def _compute_contact_address_complete(self) -> None:
        for record in self:
            locality = " ".join(part for part in (record.zip, record.city) if part)
            parts = (
                record.street,
                record.street2,
                locality,
                record.state_id.name,
                record.country_id.name,
            )
            record.contact_address_complete = ", ".join(part for part in parts if part)
