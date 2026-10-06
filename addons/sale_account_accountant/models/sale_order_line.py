from itertools import batched

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    product_invoice_policy = fields.Selection(related="product_id.invoice_policy")

    deferred_revenue = fields.Boolean(
        search="_search_deferred_revenue",
        store=False,
    )
    invoice_to_be_issued = fields.Boolean(
        string="Invoice to be Issued",
        search="_search_invoice_to_be_issued",
        store=False,
    )

    def _search_deferred_revenue(self, operator, value):
        if operator != "in":
            return NotImplemented
        return [("id", "in", self._get_accrual_line_ids("deferred"))]

    def _search_invoice_to_be_issued(self, operator, value):
        if operator != "in":
            return NotImplemented
        return [("id", "in", self._get_accrual_line_ids("invoice_issued"))]

    @api.model
    def _read_group(
        self,
        domain,
        groupby=(),
        aggregates=(),
        having=None,
        offset=0,
        limit=None,
        order=None,
    ) -> list[tuple]:
        return self._read_group_for_accrual(
            domain, groupby, aggregates, having, offset, limit, order
        )

    @api.model
    def _get_accrual_line_ids(self, mode):
        result_ids = []
        so_lines = self.env["sale.order.line"].search_fetch(
            self._get_domain_accrual(),
            ["qty_invoiced", "qty_transferred"],
            order="id",
        )
        for lines in batched(so_lines, 5000, strict=False):
            for line in lines:
                if mode == "deferred":
                    if line.qty_invoiced_at_date > line.qty_transferred_at_date:
                        result_ids.append(line.id)
                elif mode == "invoice_issued":
                    if line.qty_invoiced_at_date < line.qty_transferred_at_date:
                        result_ids.append(line.id)
                else:
                    _debug.logic("accrual_mode_refused", mode=mode)
                    raise ValueError("Invalid accrual mode")
        _debug.perf.count(
            "accrual_lines_scanned",
            mode=mode,
            scanned=len(so_lines),
            matched=len(result_ids),
        )
        return result_ids

    @api.model
    def _get_domain_accrual(self) -> list:
        return [
            *super()._get_domain_accrual(),
            ("state", "=", "done"),
            *self._get_accrual_date_window("order_id.date_order"),
        ]

    @api.model
    def _get_aggregates_to_skip_and_fields_to_patch(self) -> tuple:
        aggregates_to_skip, fields_to_patch = (
            super()._get_aggregates_to_skip_and_fields_to_patch()
        )
        aggregates_to_skip.insert(0, "qty_transferred_at_date:sum")
        fields_to_patch.insert(0, "qty_transferred_at_date")
        return (aggregates_to_skip, fields_to_patch)
