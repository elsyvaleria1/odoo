from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_mondialrelay = fields.Boolean(compute="_compute_is_mondialrelay")

    @api.depends("ref")
    def _compute_is_mondialrelay(self) -> None:
        for p in self:
            p.is_mondialrelay = p.ref and p.ref.startswith("MR#")

    def _mondialrelay_search_or_create(self, data):
        _debug.pipeline("mondialrelay_partner_resolve", partners=self)
        self.check_singleton()
        country = self.env["res.country"].search(
            [("code", "=", data["country_code"].upper())],
            limit=1,
        )
        if not country:
            raise ValidationError(self.env._("The pickup point country is invalid."))
        address_values = {
            "ref": "MR#%s" % data["id"],
            "name": data["name"],
            "street": data["street"],
            "street2": data["street2"] or False,
            "zip": data["zip"],
            "city": data["city"],
            "country_id": country.id,
            "type": "delivery",
            "parent_id": self.id,
        }
        partner = self.search(
            [(field, "=", value) for field, value in address_values.items()],
            limit=1,
        )
        partner = partner or self.create(address_values)
        if phone_values := partner._prepare_phone_replacement_vals(
            self._phone_get_number()
        ):
            partner.write(phone_values)
        return partner

    def _get_avatar_placeholder_path(self):
        if self.is_mondialrelay:
            return "delivery_mondialrelay/static/src/img/truck_mr.png"
        return super()._get_avatar_placeholder_path()

    def _filter_editable_by_current_customer(self, **kwargs):
        editable = super()._filter_editable_by_current_customer(**kwargs)
        return editable.filtered(lambda partner: not partner.is_mondialrelay)
