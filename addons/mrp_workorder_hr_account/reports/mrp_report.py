from collections import defaultdict

from odoo import fields, models
from odoo.tools import frozendict


class MrpReport(models.Model):
    _inherit = "mrp.report"
    _depends = frozendict(
        {
            "mrp.routing.workcenter": ["employee_ratio"],
            "mrp.workcenter": ["employee_costs_hour"],
            "mrp.workcenter.productivity": ["employee_cost"],
            "mrp.workorder": ["employee_costs_hour"],
        }
    )

    employee_cost = fields.Monetary(
        string="Total Employee Cost",
        readonly=True,
        groups="mrp.group_mrp_routings",
        help="Total cost of employees for manufacturing order",
    )
    unit_employee_cost = fields.Monetary(
        string="Average Employee Cost / Unit",
        readonly=True,
        aggregator="avg",
        groups="mrp.group_mrp_routings",
        help="Employee Cost per unit produced (in product UoM) of manufacturing order",
    )

    def _select_total_cost(self):
        return super()._select_total_cost() + " + op_cost.total_emp"

    def _select(self):
        extra_select = """
                    , op_cost.total_emp * account_currency_table.rate                                                                   AS employee_cost,
                    op_cost.total_emp * (1 - cost_share.byproduct_cost_share) / prod_qty.product_qty * account_currency_table.rate      AS unit_employee_cost
                """
        return super()._select() + extra_select

    def _expected_component_cost(self) -> str:
        return """
            , AVG(COALESCE(product_standard_price.value,0))              AS expected_component_cost_unit
            """

    def _expected_employee_cost(self) -> str:
        return """
            , AVG(COALESCE(operation.employee_cost,0))                   AS expected_employee_cost_unit
            """

    def _expected_operation_cost(self) -> str:
        return """
            , AVG(COALESCE(operation.workcenter_cost,0))                 AS expected_operation_cost_unit
            """

    def _expected_total_cost(self) -> str:
        return """
            ,
                AVG(
                    COALESCE(product_standard_price.value,0) +
                    COALESCE(operation.employee_cost,0) +
                    COALESCE(operation.workcenter_cost,0)
                )                                                          AS expected_total_cost_unit
            """

    def _from(self):
        res = super()._from()
        res += f"""
            {self._join_expected_operation_cost_unit()}
        """
        return res

    def _join_operations_cost(self) -> str:
        return """
            LEFT JOIN (
                SELECT
                    mo_id                                                                    AS mo_id,
                    SUM(op_costs_hour / 60. * op_duration)                                   AS total,
                    SUM(op_duration)                                                         AS total_duration,
                    SUM(emp_costs)                                                           AS total_emp
                FROM (
                    SELECT
                        mo.id AS mo_id,
                        CASE
                            WHEN wo.costs_hour != 0.0 AND wo.costs_hour IS NOT NULL THEN wo.costs_hour
                            ELSE COALESCE(wc.costs_hour, 0.0) END                                       AS op_costs_hour,
                        CASE
                            WHEN wo.duration_expected != 0.0 AND wo.duration_expected IS NOT NULL AND wo.cost_mode = 'estimated'
                            THEN wo.duration_expected
                            ELSE COALESCE(wo.duration, 0.0) END                                         AS op_duration,
                        CASE
                            WHEN wo.duration_expected != 0.0 AND wo.duration_expected IS NOT NULL AND wo.cost_mode = 'estimated'
                            THEN wo.duration_expected / 60. * wo.employee_costs_hour
                            ELSE COALESCE(SUM(t.duration / 60. * t.employee_cost), 0.0) END             AS emp_costs
                    FROM mrp_production AS mo
                    LEFT JOIN mrp_workorder wo ON wo.production_id = mo.id
                    LEFT JOIN mrp_workcenter_productivity t ON t.workorder_id = wo.id
                    LEFT JOIN mrp_workcenter wc ON wc.id = wo.workcenter_id
                    WHERE mo.state = 'done'
                    GROUP BY
                        mo.id,
                        wc.costs_hour,
                        wo.id
                    ) AS op_cost_vars
                GROUP BY mo_id
            ) op_cost ON op_cost.mo_id = mo.id
        """

    def _join_expected_operation_cost_unit(self) -> str:
        minutes_by_key = self._get_expected_operation_minutes()
        operation_ids, product_ids, minutes = (
            [int(key[0]) for key in minutes_by_key],
            [int(key[1]) for key in minutes_by_key],
            [float(value) for value in minutes_by_key.values()],
        )
        return f"""
            LEFT JOIN (
                SELECT
                    mo.id                                                                       AS mo_id,
                    SUM(
                        expected.minutes / 60 * wc.costs_hour
                    )                                                                           AS workcenter_cost,
                    SUM(
                        expected.minutes / 60 * wc.employee_costs_hour * op.employee_ratio
                    )                                                                           AS employee_cost
                FROM mrp_production                                                             AS mo
                JOIN mrp_routing_workcenter                                                     AS op
                    ON op.bom_id = mo.bom_id
                JOIN mrp_workcenter                                                             AS wc
                    ON wc.id = op.workcenter_id
                JOIN unnest(
                    ARRAY[{", ".join(map(str, operation_ids))}]::int[],
                    ARRAY[{", ".join(map(str, product_ids))}]::int[],
                    ARRAY[{", ".join(map(repr, minutes))}]::float8[]
                )                                                                               AS expected(operation_id, product_id, minutes)
                    ON expected.operation_id = op.id
                    AND expected.product_id = mo.product_id
                WHERE mo.state = 'done'
                GROUP BY mo.id
            ) operation
                ON operation.mo_id = mo.id
        """

    def _get_expected_operation_minutes(self):
        products_by_bom = defaultdict(set)
        for bom, product in self.env["mrp.production"]._read_group(
            [("state", "=", "done"), ("bom_id", "!=", False)],
            ["bom_id", "product_id"],
        ):
            products_by_bom[bom].add(product)
        operations = (
            self.env["mrp.routing.workcenter"]
            .with_context(active_test=False)
            .search([("bom_id", "in", [bom.id for bom in products_by_bom])])
        )
        minutes = {}
        for operation in operations:
            for product in products_by_bom[operation.bom_id]:
                _cycles, _overhead, minutes[operation.id, product.id] = (
                    operation.workcenter_id._get_duration_breakdown(
                        product,
                        product.uom_id,
                        1,
                        operation.time_cycle,
                        operation.bom_id,
                    )
                )
        return minutes

    def _group_by(self):
        extra_groupby = """
            , op_cost.total_emp
        """
        return super()._group_by() + extra_groupby
