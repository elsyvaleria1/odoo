from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["mixin.account.external.tax", "sale.order"]

    def action_confirm(self):
        """Ensure confirmed orders have the right taxes."""
        self._get_and_set_external_taxes_on_eligible_records()
        return super().action_confirm()

    def action_send_quotation(self):
        """Calculate taxes before presenting order to the customer."""
        self._get_and_set_external_taxes_on_eligible_records()
        return super().action_send_quotation()

    def _get_and_set_external_taxes_on_eligible_records(self):
        """mixin.account.external.tax override."""
        eligible_orders = self.filtered(
            lambda order: (
                order.is_tax_computed_externally
                and order.state in ("draft", "done")
                and not order.locked
            )
        )
        _debug.pipeline(
            "external_taxes_eligible_orders",
            orders=self,
            eligible=eligible_orders,
        )
        eligible_orders._set_external_taxes(eligible_orders._get_external_taxes())
        return super()._get_and_set_external_taxes_on_eligible_records()

    def _prepare_line_data_for_external_taxes(self):
        """mixin.account.external.tax override."""
        AccountTax = self.env["account.tax"]
        order_lines = self.line_ids.filtered(
            lambda line: not line.display_type and not line.is_downpayment
        )
        base_lines = [
            line._prepare_base_line_for_taxes_computation() for line in order_lines
        ]
        _debug.perf.count(
            "external_tax_base_lines",
            order=self,
            lines=len(order_lines),
            base_lines=len(base_lines),
        )
        base_lines += self._add_base_lines_for_early_payment_discount()
        AccountTax._add_tax_details_in_base_lines(base_lines, self.company_id)
        AccountTax._round_base_lines_tax_details(base_lines, self.company_id)
        return [
            {"base_line": base_line, "description": base_line["record"].name}
            for base_line in base_lines
        ]
