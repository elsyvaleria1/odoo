from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _prepare_invoice_vals(self):
        # Override to prevent adding the avatax localisation for orders made through Amazon.
        # If there's no fiscal position on the order, the fiscal position of the partner is normally
        # used instead if any.
        values = super()._prepare_invoice_vals()
        values_fp = self.env["account.fiscal.position"].browse(
            values["fiscal_position_id"]
        )
        if (
            self.amazon_order_ref
            and not self.fiscal_position_id
            and values_fp.is_avatax
        ):
            _debug.logic(
                "avatax_fiscal_position_dropped",
                order=self,
                ref=self.amazon_order_ref,
                position=values_fp,
            )
            values["fiscal_position_id"] = False
        return values
