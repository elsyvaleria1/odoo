from odoo import fields, models
from odoo.libs.sql import SQL
from odoo.tools import frozendict

from odoo.addons.sale import const


class SaleRentalReport(models.Model):
    _name = "sale.rental.report"
    _inherit = "mixin.sql.report"
    _description = "Rental Analysis Report"
    _rec_name = "order_id"
    _auto = False
    _depends = frozendict(
        {
            "product.product": ["product_tmpl_id"],
            "product.template": ["categ_id", "uom_id"],
            "sale.order": [
                "company_id",
                "currency_id",
                "rental_return_date",
                "rental_start_date",
                "state",
                "user_id",
            ],
            "sale.order.line": [
                "is_rental",
                "order_id",
                "partner_id",
                "price_subtotal",
                "product_id",
                "product_qty",
                "product_uom_id",
                "qty_returned",
                "qty_transferred",
            ],
            "uom.uom": ["factor"],
        }
    )
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    date = fields.Date(readonly=True)
    order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Order #",
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit",
        readonly=True,
    )
    quantity = fields.Float(
        string="Daily Ordered Qty",
        readonly=True,
    )
    qty_transferred = fields.Float(
        string="Daily Picked-Up Qty",
        readonly=True,
    )
    qty_returned = fields.Float(
        string="Daily Returned Qty",
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Salesman",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    product_tmpl_id = fields.Many2one(
        comodel_name="product.template",
        string="Product Template",
        readonly=True,
    )
    categ_id = fields.Many2one(
        comodel_name="product.category",
        string="Product Category",
        readonly=True,
    )
    state = fields.Selection(
        selection=const.ORDER_STATE,
        string="Status",
        readonly=True,
    )
    price = fields.Float(
        string="Daily Amount",
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
    )

    # ------------------------------------------------------------
    # REGISTRY METHODS (SQL Report Mixin Pattern)
    # ------------------------------------------------------------

    def _get_fields_select(self) -> dict:
        """Registry of fields for SELECT clause.

        :return: mapping of ``{field_name: sql_expression}``
        :rtype: dict
        """
        return {
            # One row per rental day per line: sol.id is not unique here, so the
            # primary key has to be synthesised over the expanded row set.
            "id": "row_number() OVER (ORDER BY sol.id, d.date)",
            "order_id": "sol.order_id",
            "product_id": "sol.product_id",
            "quantity": "sol.product_qty / (u.factor * u2.factor)",
            "qty_transferred": "sol.qty_transferred / (u.factor * u2.factor)",
            "qty_returned": "sol.qty_returned / (u.factor * u2.factor)",
            "product_uom_id": "sol.product_uom_id",
            "partner_id": "sol.partner_id",
            "user_id": "so.user_id",
            "categ_id": "pt.categ_id",
            "product_tmpl_id": "p.product_tmpl_id",
            "date": "d.date::date",
            "price": """sol.price_subtotal / (
                date_part('day', so.rental_return_date - so.rental_start_date) + 1
            )""",
            "company_id": "so.company_id",
            "state": "so.state",
            "currency_id": "so.currency_id",
        }

    def _get_from_tables(self) -> list:
        """Registry of tables and JOINs for FROM clause.

        :return: tuples ``(table_name, alias, join_type, on_condition)``
        :rtype: list
        """
        return [
            ("sale_order_line", "sol", None, None),  # Base table
            ("sale_order", "so", "JOIN", "sol.order_id=so.id"),
            ("product_product", "p", "JOIN", "p.id=sol.product_id"),
            ("product_template", "pt", "JOIN", "p.product_tmpl_id=pt.id"),
            ("uom_uom", "u", "JOIN", "u.id=sol.product_uom_id"),
            ("uom_uom", "u2", "JOIN", "u2.id=pt.uom_id"),
            # Expands each rental line into one row per day of its period.
            (
                SQL(
                    """LATERAL generate_series(
                so.rental_start_date::date,
                so.rental_return_date::date,
                '1 day'::interval
            ) AS d(date)"""
                ),
                None,
                "CROSS JOIN",
                None,
            ),
        ]

    def _get_where_conditions(self) -> list:
        """Registry of conditions for WHERE clause.

        :return: SQL condition strings that will be AND'ed together
        :rtype: list
        """
        return [
            "sol.is_rental",  # Only rental order lines
        ]

    def _get_fields_group_by(self) -> list:
        """Registry of fields for GROUP BY clause.

        This report doesn't use GROUP BY: it generates one row per day per
        rental line using generate_series.

        :return: an empty list (no grouping needed)
        :rtype: list
        """
        return []
