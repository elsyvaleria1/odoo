from itertools import batched

from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    prepaid_expense = fields.Boolean(
        search="_search_prepaid_expense",
        store=False,
    )
    bill_to_receive = fields.Boolean(
        string="Bill to Receive",
        search="_search_bill_to_receive",
        store=False,
    )

    def _search_prepaid_expense(self, operator, value):
        if operator != "in":
            return NotImplemented
        return [("id", "in", self._get_accrual_line_ids("prepaid"))]

    def _search_bill_to_receive(self, operator, value):
        if operator != "in":
            return NotImplemented
        return [("id", "in", self._get_accrual_line_ids("bill_to_receive"))]

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

        po_lines = self.env["purchase.order.line"].search_fetch(
            self._get_domain_accrual(),
            ["qty_invoiced_at_date", "qty_transferred_at_date"],
            order="id",
        )

        for lines in batched(po_lines, 5000, strict=False):
            for line in lines:
                if mode == "prepaid":
                    if (
                        line.qty_invoiced_at_date
                        and line.qty_invoiced_at_date > line.qty_transferred_at_date
                    ):
                        result_ids.append(line.id)
                elif mode == "bill_to_receive":
                    if (
                        line.qty_transferred_at_date
                        and line.qty_invoiced_at_date < line.qty_transferred_at_date
                    ):
                        result_ids.append(line.id)
                else:
                    raise ValueError("Invalid accrual mode")
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
