from typing import Literal

from odoo import models
from odoo.api import ValuesType


class ResCurrency(models.Model):
    _inherit = "res.currency"

    def write(self, vals: ValuesType) -> Literal[True]:
        res = super().write(vals)

        if self and "active" in vals and not vals["active"]:
            self.env["product.pricelist"].with_context(
                allowed_company_ids=self.env.user.company_ids.ids
            ).search([("currency_id", "in", self.ids)]).action_archive()

        return res

    def _activate_group_multi_currency(self) -> None:
        super()._activate_group_multi_currency()
        if not self.env.user.has_group("product.group_product_pricelist"):
            group_user = self.env.ref("base.group_user").sudo()
            group_user._add_implied_group(
                self.env.ref("product.group_product_pricelist")
            )
            self.env["res.company"]._activate_or_create_pricelists()
