from odoo import api, fields, models

from odoo.addons.snailmail.country_utils import SNAILMAIL_COUNTRIES


class ResPartner(models.Model):
    _inherit = "res.partner"

    snailmail_unsent_letter_ids = fields.One2many(
        comodel_name="snailmail.letter",
        inverse_name="partner_id",
        domain=[("state", "not in", ["sent", "canceled"])],
    )

    def write(self, vals):
        letter_address_vals = {}
        address_fields = ["street", "street2", "city", "zip", "state_id", "country_id"]
        for field in address_fields:
            if field in vals:
                letter_address_vals[field] = vals[field]

        if letter_address_vals:
            self.snailmail_unsent_letter_ids.write(letter_address_vals)

        return super().write(vals)

    def _get_country_name(self):
        country_code = self.country_id.code
        if (
            self.env.context.get("snailmail_layout")
            and country_code in SNAILMAIL_COUNTRIES
        ):
            return SNAILMAIL_COUNTRIES.get(country_code)

        return super()._get_country_name()

    @api.model
    def _get_address_format(self):
        if self.env.context.get("snailmail_layout") and self.country_id.code == "DE":
            result = "%(street)s"
            if self.street2:
                result += " // %(street2)s"
            return result + "\n%(zip)s %(city)s\n%(country_name)s"
        if self.env.context.get("snailmail_layout") and self.street2:
            return "%(street)s, %(street2)s\n%(city)s %(state_code)s %(zip)s\n%(country_name)s"

        return super()._get_address_format()
