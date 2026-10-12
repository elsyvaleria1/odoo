from typing import Self

from odoo import api, models


class ProductSupplierinfo(models.Model):
    _inherit = "product.supplierinfo"

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        self.currency_id = (
            self.partner_id.property_purchase_currency_id.id
            or self.env.company.currency_id.id
        )

    def _filtered_for_company_and_product(self, company, product, params=False) -> Self:
        if params and "order_id" in params and params["order_id"].company_id:
            company = params["order_id"].company_id
        return super()._filtered_for_company_and_product(company, product, params)
