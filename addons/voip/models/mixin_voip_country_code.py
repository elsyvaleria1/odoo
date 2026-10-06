from odoo import api, fields, models

from odoo.addons.voip.models.utils import extract_country_code


class MixinVoipCountryCode(models.AbstractModel):
    """Mixin to link phone number to a res.country record.

    This mixin extracts the country ISO code (e.g. "be" for Belgium) from the
    international dialing prefix of the phone number (e.g. "+32"), and then link
    to a res.country record. This is useful for displaying country flags or
    identifying the origin of a phone number.

    Models inheriting this mixin either hold a phone.number many2many (found
    through `_get_phone_number_fields()`) or name their Char number fields in
    `_voip_get_phone_char_fields()`.
    """

    _name = "mixin.voip.country.code"
    _description = "Phone Country Mixin"

    country_code_from_phone = fields.Char(
        export_string_translation=False,
        compute="_compute_phone_country_id",
        help="Computes the country ISO code (e.g. be for Belgium) from the phone number dialing code (e.g. +32), if any.\n"
        "Useful for displaying the flag associated with a phone number.",
    )
    phone_country_id = fields.Many2one(
        comodel_name="res.country",
        export_string_translation=False,
        compute="_compute_phone_country_id",
    )

    def _voip_get_phone_char_fields(self) -> list:
        return []

    def _voip_get_phone_values(self) -> list:
        self.check_singleton()
        values = []
        for fname in self._get_phone_number_fields():
            phone = self[fname]._primary()
            values += [phone.sanitized, phone.number]
        values += [self[fname] for fname in self._voip_get_phone_char_fields()]
        return [value for value in values if value]

    @api.depends(
        lambda self: [
            *(f"{fname}.sanitized" for fname in self._get_phone_number_fields()),
            *self._voip_get_phone_char_fields(),
        ]
    )
    def _compute_phone_country_id(self) -> None:
        self.phone_country_id = False
        self.country_code_from_phone = ""
        countries_by_code = (
            self.env["res.country"]
            .search_fetch([("code", "!=", False)])
            .grouped("code")
        )
        for record in self:
            for phone_number in record._voip_get_phone_values():
                iso_code = extract_country_code(phone_number)["iso"]
                if not iso_code:
                    continue
                record.country_code_from_phone = iso_code
                record.phone_country_id = countries_by_code.get(iso_code.upper())
                break
