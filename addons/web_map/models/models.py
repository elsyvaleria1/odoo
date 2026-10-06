from lxml.builder import E

from odoo import api, models
from odoo.exceptions import UserError


class Base(models.AbstractModel):
    _inherit = "base"

    @api.model
    def _get_default_map_view(self):
        if "partner_id" not in self._fields:
            raise UserError(
                self.env._(
                    "%(model)s has no Contact field, so it cannot be shown on a map.",
                    model=self._description or self._name,
                )
            )
        view = E.map()
        view.set("res_partner", "partner_id")
        return view
