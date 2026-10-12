from collections import defaultdict

from odoo import models
from odoo.tools import float_is_zero


class AccountMove(models.Model):
    _inherit = "account.move"

    def _prepare_invoice_lot_rows(self):
        res = super()._prepare_invoice_lot_rows()

        if self.state == "draft":
            return res

        sale_orders = self.mapped("invoice_line_ids.sale_line_ids.order_id").filtered(
            "is_rental_order"
        )
        rental_stock_move_lines = sale_orders.line_ids.filtered(
            "is_rental"
        ).move_ids.move_line_ids

        if not rental_stock_move_lines:
            return res

        stock_move_lines = rental_stock_move_lines

        ordered_invoice_ids = (
            sale_orders.mapped("invoice_ids")
            .filtered(lambda i: i.state not in ["draft", "cancel"])
            .sorted(lambda i: (i.invoice_date, i.id))
        )

        self_index = None
        for i, invoice in enumerate(ordered_invoice_ids):
            if invoice.id == self.id:
                self_index = i
                break

        previous_invoices = ordered_invoice_ids[:self_index]
        last_invoice = previous_invoices[-1] if len(previous_invoices) else None

        self_datetime = (
            max(self.invoice_line_ids.mapped("write_date"))
            if self.invoice_line_ids
            else None
        )
        last_invoice_datetime = (
            max(last_invoice.invoice_line_ids.mapped("write_date"))
            if last_invoice
            else None
        )

        def _filter_outgoing_sml(ml):
            if (
                ml.state == "done"
                and ml.trace_id
                and ml.location_dest_id == ml.company_id.rental_loc_id
            ):
                if last_invoice_datetime:
                    return last_invoice_datetime <= ml.date <= self_datetime
                else:
                    return ml.date <= self_datetime
            return False

        outgoing_sml = stock_move_lines.filtered(_filter_outgoing_sml)

        qties_per_lot = defaultdict(lambda: 0)
        for ml in outgoing_sml:
            qties_per_lot[ml.trace_id] += ml.product_uom_id._get_quantity_in_unit(
                ml.quantity, ml.product_id.uom_id
            )

        lot_values = res
        for trace_id, qty in qties_per_lot.items():
            if float_is_zero(
                qty, precision_rounding=trace_id.product_id.uom_id.rounding
            ):
                continue
            lot_values.append(
                {
                    "product_name": trace_id.product_id.display_name,
                    "quantity": qty,
                    "uom_name": trace_id.product_uom_id.name,
                    "lot_name": trace_id.name,
                    "trace_id": trace_id.id,
                }
            )

        return lot_values
