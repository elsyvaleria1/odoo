from odoo import fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

_debug = DebugLog(__name__)


class MrpReport(models.Model):
    _name = "mrp.report"
    _description = "Manufacturing Report"
    _rec_name = "production_id"
    _auto = False
    _depends = frozendict(
        {
            "mrp.bom": ["product_qty"],
            "mrp.bom.line": ["bom_id", "product_id", "product_qty"],
            "mrp.production": [
                "bom_id",
                "company_id",
                "date_end",
                "name",
                "product_id",
                "state",
            ],
            "mrp.routing.workcenter": ["bom_id", "workcenter_id"],
            "mrp.workcenter": ["costs_hour"],
            "mrp.workcenter.productivity": ["duration", "workorder_id"],
            "mrp.workorder": [
                "cost_mode",
                "costs_hour",
                "duration",
                "duration_expected",
                "production_id",
                "workcenter_id",
            ],
            "product.product": ["product_tmpl_id", "standard_price"],
            "product.template": ["uom_id"],
            "res.company": ["currency_id"],
            "stock.location": ["usage"],
            "stock.move": [
                "cost_share",
                "location_dest_id",
                "price_unit",
                "product_id",
                "product_qty",
                "product_uom_id",
                "product_uom_qty",
                "production_id",
                "quantity",
                "raw_material_production_id",
                "state",
                "value",
                "move_dest_ids",
            ],
            "uom.uom": ["factor"],
        }
    )
    _order = "date_end desc"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    id = fields.Id(string="")
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
        required=True,
    )
    production_id = fields.Many2one(
        comodel_name="mrp.production",
        string="Manufacturing Order",
        readonly=True,
    )
    date_end = fields.Datetime(
        string="End Date",
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        readonly=True,
    )
    total_cost = fields.Monetary(
        readonly=True,
        help="Total cost of manufacturing order (component + operation costs)",
    )
    component_cost = fields.Monetary(
        string="Total Component Cost",
        readonly=True,
        help="Total cost of components for manufacturing order",
    )
    operation_cost = fields.Monetary(
        string="Total Operation Cost",
        readonly=True,
        groups="mrp.group_mrp_routings",
        help="Total cost of operations for manufacturing order",
    )
    duration = fields.Float(
        string="Total Duration of Operations",
        readonly=True,
        groups="mrp.group_mrp_routings",
        help="Total duration (minutes) of operations for manufacturing order",
    )

    qty_produced = fields.Float(
        string="Quantity Produced",
        readonly=True,
        help="Total quantity produced in product's UoM",
    )
    qty_demanded = fields.Float(
        string="Quantity Demanded",
        readonly=True,
        help="Total quantity demanded in product's UoM",
    )
    yield_rate = fields.Float(
        string="Yield Percentage(%)",
        readonly=True,
        help="Ratio of quantity produced over quantity demanded",
    )

    # note that unit costs include subtraction of byproduct cost share
    unit_cost = fields.Monetary(
        string="Cost / Unit",
        readonly=True,
        aggregator="avg",
        help="Cost per unit produced (in product UoM) of manufacturing order",
    )
    unit_component_cost = fields.Monetary(
        string="Component Cost / Unit",
        readonly=True,
        aggregator="avg",
        help="Component cost per unit produced (in product UoM) of manufacturing order",
    )
    unit_operation_cost = fields.Monetary(
        string="Total Operation Cost / Unit",
        readonly=True,
        aggregator="avg",
        groups="mrp.group_mrp_routings",
        help="Operation cost per unit produced (in product UoM) of manufacturing order",
    )
    unit_duration = fields.Float(
        string="Duration of Operations / Unit",
        readonly=True,
        aggregator="avg",
        groups="mrp.group_mrp_routings",
        help="Operation duration (minutes) per unit produced of manufacturing order",
    )

    byproduct_cost = fields.Monetary(
        string="By-Products Total Cost",
        readonly=True,
        groups="mrp.group_mrp_byproducts",
    )

    expected_component_cost_unit = fields.Monetary(
        string="Expected Component Cost / Unit",
        readonly=True,
        aggregator="avg",
    )
    expected_employee_cost_unit = fields.Monetary(
        string="Expected Employee Cost / Unit",
        readonly=True,
        aggregator="avg",
        groups="mrp.group_mrp_routings",
    )
    expected_operation_cost_unit = fields.Monetary(
        string="Expected Operation Cost / Unit",
        readonly=True,
        aggregator="avg",
        groups="mrp.group_mrp_routings",
    )
    expected_total_cost_unit = fields.Monetary(
        string="Expected Total Cost / Unit",
        readonly=True,
        aggregator="avg",
        groups="mrp.group_mrp_routings",
    )

    @property
    def _table_query(self):
        """Report needs to be dynamic to take into account multi-company selected + multi-currency rates"""
        _debug.perf.count("mrp_report_view_built", companies=len(self.env.companies))
        return "%s %s %s %s" % (
            self._select(),
            self._from(),
            self._where(),
            self._group_by(),
        )

    def _select_total_cost(self):
        return "comp_cost.total + op_cost.total"

    def _select(self):
        return f"""
            SELECT
                min(mo.id)             AS id,
                mo.id                  AS production_id,
                mo.company_id          AS company_id,
                rc.currency_id         AS currency_id,
                mo.date_end       AS date_end,
                mo.product_id          AS product_id,
                prod_qty.product_qty   AS qty_produced,
                prod_qty.qty_demanded  AS qty_demanded,
                prod_qty.product_qty / prod_qty.qty_demanded * 100                                                                      AS yield_rate,
                comp_cost.total * account_currency_table.rate                                                                                   AS component_cost,
                op_cost.total * account_currency_table.rate                                                                                     AS operation_cost,
                ({self._select_total_cost()}) * account_currency_table.rate                                                                     AS total_cost,
                op_cost.total_duration                                                                                                  AS duration,
                comp_cost.total * (1 - cost_share.byproduct_cost_share) / prod_qty.product_qty * account_currency_table.rate                    AS unit_component_cost,
                op_cost.total * (1 - cost_share.byproduct_cost_share) / prod_qty.product_qty * account_currency_table.rate                      AS unit_operation_cost,
                ({self._select_total_cost()}) * (1 - cost_share.byproduct_cost_share) / prod_qty.product_qty * account_currency_table.rate      AS unit_cost,
                op_cost.total_duration / prod_qty.product_qty                                                                           AS unit_duration,
                ({self._select_total_cost()}) * cost_share.byproduct_cost_share * account_currency_table.rate                                   AS byproduct_cost
                {self._expected_component_cost()}
                {self._expected_employee_cost()}
                {self._expected_operation_cost()}
                {self._expected_total_cost()}

        """

    def _expected_component_cost(self) -> str:
        return """
            , 0   AS expected_component_cost_unit
            """

    def _expected_employee_cost(self) -> str:
        return """
            , 0   AS expected_employee_cost_unit
            """

    def _expected_operation_cost(self) -> str:
        return """
            , 0 AS expected_operation_cost_unit
            """

    def _expected_total_cost(self) -> str:
        return """
            , 0 AS expected_total_cost_unit
            """

    def _from(self):
        """MO costs are quite complicated so the table is built with the following subqueries (per MO):
            1. total component cost (note we cover no components use case)
            2. total operations cost (note we cover no operations use case)
            3. total byproducts cost share
            4. total qty produced based on the product's UoM
            5. expected component cost per unit (standard price x BoM quantities)
        Note subqueries 3 and 4 exist because 3 subqueries use the stock_move table and combining them would result in duplicated SVL values and
        subquery 2 (i.e. the nested subquery) exists to prevent duplication of operation costs (i.e. 2+ comp lines and 2+ operations at diff wc in
        the same MO results in op cost duplication if op cost isn't aggregated first).
        """
        currency_table = self.env["res.currency"]._get_simple_currency_table(
            self.env.companies
        )
        return f"""
            FROM mrp_production AS mo
            JOIN res_company AS rc ON rc.id = {int(self.env.company.id)}
            {self._join_component_cost()}
            {self._join_operations_cost()}
            {self._join_byproducts_cost_share()}
            {self._join_total_qty_produced()}
            LEFT JOIN {currency_table.render()} ON account_currency_table.company_id = mo.company_id
            {self._join_expected_component_cost_unit()}
        """

    def _join_expected_component_cost_unit(self) -> str:
        standard_price_sql = self.env["product.product"]._field_to_sql(
            "product", "standard_price"
        )
        return f"""
            LEFT JOIN (
                SELECT
                    SUM(
                        {standard_price_sql.render()}
                        * bom_line.product_qty
                    ) / bom.product_qty                                                 AS value,
                    MIN(mo.id)                                                          AS mo_id
                FROM mrp_production                                                     AS mo
                JOIN mrp_bom                                                            AS bom
                    ON bom.id = mo.bom_id
                JOIN mrp_bom_line                                                       AS bom_line
                    ON bom_line.bom_id = mo.bom_id
                JOIN product_product                                                    AS product
                    ON product.id = bom_line.product_id
                WHERE mo.state = 'done'
                GROUP BY
                    mo.id,
                    bom.product_qty
            ) product_standard_price
                ON product_standard_price.mo_id = mo.id
        """

    def _join_component_cost(self) -> str:
        return """
            LEFT JOIN (
                SELECT
                    mo.id                                                                    AS mo_id,
                    SUM(sm.value)                                                                 AS total
                FROM mrp_production AS mo
                LEFT JOIN stock_move AS sm on sm.raw_material_production_id = mo.id
                LEFT JOIN stock_location AS dest_loc ON sm.location_dest_id = dest_loc.id
                WHERE mo.state = 'done'
                    AND (sm.state = 'done' or sm.state IS NULL)
                    AND dest_loc.usage != 'inventory'
                GROUP BY
                    mo.id
            ) comp_cost ON comp_cost.mo_id = mo.id
        """

    def _join_operations_cost(self) -> str:
        return """
            LEFT JOIN (
                SELECT
                    mo_id                                                                    AS mo_id,
                    SUM(op_costs_hour / 60. * op_duration)                                   AS total,
                    SUM(op_duration)                                                         AS total_duration
                FROM (
                    SELECT
                        mo.id AS mo_id,
                        CASE
                            WHEN wo.costs_hour != 0.0 AND wo.costs_hour IS NOT NULL THEN wo.costs_hour
                            ELSE COALESCE(wc.costs_hour, 0.0) END                                       AS op_costs_hour,
                        CASE
                            WHEN wo.duration_expected != 0.0 AND wo.duration_expected IS NOT NULL AND wo.cost_mode = 'estimated'
                            THEN wo.duration_expected
                            ELSE COALESCE(wo.duration, 0.0) END                                         AS op_duration
                    FROM mrp_production AS mo
                    LEFT JOIN mrp_workorder wo ON wo.production_id = mo.id
                    LEFT JOIN mrp_workcenter wc ON wc.id = wo.workcenter_id
                    WHERE mo.state = 'done'
                    ) AS op_cost_vars
                GROUP BY mo_id
            ) op_cost ON op_cost.mo_id = mo.id
        """

    def _join_byproducts_cost_share(self) -> str:
        return """
            LEFT JOIN (
                SELECT
                    mo.id AS mo_id,
                    COALESCE(SUM(sm.cost_share), 0.0) / 100.0 AS byproduct_cost_share
                FROM stock_move AS sm
                LEFT JOIN mrp_production AS mo ON sm.production_id = mo.id
                LEFT JOIN stock_location AS dest_loc ON sm.location_dest_id = dest_loc.id
                WHERE
                    mo.state = 'done'
                    AND sm.state = 'done'
                    AND sm.quantity != 0
                    AND dest_loc.usage != 'inventory'
                GROUP BY mo.id
            ) cost_share ON cost_share.mo_id = mo.id
        """

    def _join_total_qty_produced(self) -> str:
        return """
            LEFT JOIN (
                SELECT
                    mo.id AS mo_id,
                    mo.name,
                    SUM(sm.quantity / uom.factor * uom_prod.factor) AS product_qty,
                    SUM(sm.product_uom_qty / uom.factor * uom_prod.factor) AS qty_demanded
                FROM stock_move AS sm
                JOIN mrp_production AS mo ON sm.production_id = mo.id
                JOIN uom_uom AS uom ON uom.id = sm.product_uom_id
                JOIN product_product AS product ON product.id = sm.product_id
                JOIN product_template AS template ON template.id = product.product_tmpl_id
                JOIN uom_uom AS uom_prod ON uom_prod.id = template.uom_id
                LEFT JOIN stock_location AS dest_loc ON sm.location_dest_id = dest_loc.id
                WHERE
                    mo.state = 'done'
                    AND sm.state = 'done'
                    AND sm.quantity != 0
                    AND mo.product_id = sm.product_id
                    AND dest_loc.usage != 'inventory'
                GROUP BY mo.id
            ) prod_qty ON prod_qty.mo_id = mo.id
        """

    def _where(self):
        return """
            WHERE
                mo.state = 'done'
        """

    def _group_by(self):
        return """
            GROUP BY
                mo.id,
                rc.currency_id,
                cost_share.byproduct_cost_share,
                comp_cost.total,
                op_cost.total,
                op_cost.total_duration,
                prod_qty.product_qty,
                prod_qty.qty_demanded,
                account_currency_table.rate
        """

    def _read_group_select(self, aggregate_spec, query):
        if aggregate_spec in (
            "unit_cost:avg",
            "unit_component_cost:avg",
            "unit_operation_cost:avg",
            "unit_duration:avg",
        ):
            # Make a weighted average instead of simple average for these fields
            fname, *__ = models.parse_read_group_spec(aggregate_spec)
            sql_field = self._field_to_sql(self._table, fname, query)
            sql_qty_produced = self._field_to_sql(self._table, "qty_produced", query)
            return SQL(
                "SUM(%s * %s) / SUM(%s)", sql_field, sql_qty_produced, sql_qty_produced
            )
        if aggregate_spec == "yield_rate:sum":
            sql_qty_produced = self._field_to_sql(self._table, "qty_produced", query)
            sql_qty_demanded = self._field_to_sql(self._table, "qty_demanded", query)
            return SQL("SUM(%s) / SUM(%s) * 100", sql_qty_produced, sql_qty_demanded)
        return super()._read_group_select(aggregate_spec, query)
