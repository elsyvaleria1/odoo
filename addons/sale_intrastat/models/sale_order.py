from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _prepare_invoice_vals(self):
        res = super()._prepare_invoice_vals()
        if (
            self.partner_shipping_id.country_id
            and "INTRASTAT" in self.partner_shipping_id.country_id.country_group_codes
        ):
            _debug.logic(
                "intrastat_country_from_shipping",
                order=self,
                country=self.partner_shipping_id.country_id,
            )
            res["intrastat_country_id"] = self.partner_shipping_id.country_id.id
        return res


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _prepare_aml_vals(self, **optional_values):
        invoice_line = super()._prepare_aml_vals(**optional_values)
        invoice_line["intrastat_product_origin_country_id"] = (
            self.product_id.intrastat_origin_country_id.id
        )
        return invoice_line
