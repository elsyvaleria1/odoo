from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["mixin.account.avatax.unique.code", "sale.order"]

    def _get_invoice_grouping_keys(self):
        res = super()._get_invoice_grouping_keys()
        _debug.logic(
            "avatax_invoice_grouping_keys",
            orders=self,
            avatax=bool(self.filtered("fiscal_position_id.is_avatax")),
        )
        if self.filtered("fiscal_position_id.is_avatax"):
            res += ["partner_shipping_id"]
        return res

    def _prepare_avatax_service_params(self, commit=False):
        # EXTENDS 'mixin.account.external.tax'
        res = super()._prepare_avatax_service_params(commit=commit)
        res.update(
            {
                "document_type": "SalesOrder",
                "document_date": self.date_order,
                "tax_date": self.date_order,
            }
        )
        return res
