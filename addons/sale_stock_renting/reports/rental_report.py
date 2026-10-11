from odoo import fields, models
from odoo.tools import frozendict


class SaleRentalReport(models.Model):
    _inherit = "sale.rental.report"
    _depends = frozendict(
        {
            "sale.order.line": [
                "pickedup_trace_ids",
                "reserved_trace_ids",
                "returned_trace_ids",
            ],
        }
    )

    trace_id = fields.Many2one(
        comodel_name="product.trace",
        string="Serial Number",
        readonly=True,
    )

    def _get_fields_select(self) -> dict:
        select = super()._get_fields_select()
        base_price = select["price"]
        select.update(
            {
                "id": "row_number() OVER (ORDER BY sol.id, d.date, res.product_trace_id)",
                "quantity": """CASE
                WHEN res.product_trace_id IS NOT NULL
                THEN 1.0
                ELSE sol.product_qty / (u.factor * u2.factor)
                END""",
                "qty_transferred": """CASE
                WHEN res.product_trace_id IS NULL
                THEN sol.qty_transferred / (u.factor * u2.factor)
                WHEN returned.product_trace_id IS NULL AND pickedup.product_trace_id IS NULL
                THEN 0.0
                ELSE 1.0
                END""",
                "qty_returned": """CASE
                WHEN res.product_trace_id IS NULL
                THEN sol.qty_returned / (u.factor * u2.factor)
                WHEN returned.product_trace_id IS NOT NULL
                THEN 1.0
                ELSE 0.0
                END""",
                "price": f"""CASE
                WHEN res.product_trace_id IS NOT NULL AND sol.product_qty != 0
                THEN ({base_price}) / (sol.product_qty / (u.factor * u2.factor))
                ELSE ({base_price})
                END""",
                "trace_id": "res.product_trace_id",
            }
        )
        return select

    def _get_from_tables(self) -> list:
        return super()._get_from_tables() + [
            (
                "rental_reserved_lot_rel",
                "res",
                "LEFT JOIN",
                "res.sale_order_line_id=sol.id",
            ),
            (
                "rental_pickedup_lot_rel",
                "pickedup",
                "LEFT JOIN",
                (
                    "pickedup.sale_order_line_id=sol.id"
                    " AND pickedup.product_trace_id = res.product_trace_id"
                ),
            ),
            (
                "rental_returned_lot_rel",
                "returned",
                "LEFT JOIN",
                (
                    "returned.sale_order_line_id=sol.id"
                    " AND returned.product_trace_id = res.product_trace_id"
                ),
            ),
        ]
