from odoo import api, fields, models
from odoo.tools import frozendict


class PlanningAnalysisReport(models.Model):
    _inherit = "planning.analysis.report"
    _depends = frozendict(
        {
            "planning.slot": ["sale_line_id"],
            "sale.order.line": ["order_id"],
        }
    )

    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sales Order",
        readonly=True,
    )
    sale_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sales Order Item",
        readonly=True,
    )
    # Not using a related as we want to avoid having a depends.
    role_product_ids = fields.One2many(
        comodel_name="product.template",
        compute="_compute_role_product_ids",
        search="_search_role_product_ids",
    )

    def _compute_role_product_ids(self) -> None:
        for slot in self:
            slot.role_product_ids = slot.role_id.product_ids

    @api.model
    def _search_role_product_ids(self, operator, value) -> list:
        return [("role_id.product_ids", operator, value)]

    @property
    def _table_query(self):
        return "%s %s %s %s %s" % (
            self._select(),
            self._from(),
            self._join(),
            self._where(),
            self._group_by(),
        )

    @api.model
    def _select(self):
        return (
            super()._select()
            + """,
            SOL.order_id AS sale_order_id,
            S.sale_line_id AS sale_line_id
        """
        )

    @api.model
    def _join(self):
        return (
            super()._join()
            + """
            LEFT JOIN sale_order_line SOL ON SOL.id = S.sale_line_id
        """
        )

    @api.model
    def _where(self):
        return """
            WHERE start_datetime IS NOT NULL
        """

    @api.model
    def _group_by(self):
        return (
            super()._group_by()
            + """,
            SOL.order_id, S.sale_line_id
        """
        )
