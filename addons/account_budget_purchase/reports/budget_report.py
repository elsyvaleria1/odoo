from odoo import fields, models
from odoo.tools import SQL, frozendict


class BudgetReport(models.Model):
    _inherit = "budget.report"
    _depends = frozendict(
        {
            "account.move.line": ["purchase_line_ids"],
            "purchase.order": [
                "company_id",
                "currency_rate",
                "date_order",
                "state",
                "user_id",
            ],
            "purchase.order.line": [
                "analytic_json",
                "name",
                "order_id",
                "price_subtotal",
                "price_unit",
                "product_qty",
                "product_uom_id",
            ],
        }
    )

    line_type = fields.Selection(selection_add=[("committed", "Committed")])
    committed = fields.Float(readonly=True)

    def _get_report_timezone(self):
        tz = self.env.user.tz
        if not tz:
            return "UTC"
        self.env.cr.execute(
            SQL("SELECT 1 FROM pg_timezone_names WHERE name = %(tz)s", tz=tz)
        )
        return tz if self.env.cr.fetchone() else "UTC"

    def _get_pol_query(self, plan_fnames):
        precision_digits = self.env["decimal.precision"].get_precision("Product Unit")
        qty_invoiced_table = SQL(
            """
               SELECT SUM(
                          CASE WHEN COALESCE(uom_aml.id != uom_pol.id, FALSE)
                               THEN ROUND(CAST((aml.quantity / uom_aml.factor) * uom_pol.factor AS NUMERIC), %(precision_digits)s)
                               ELSE COALESCE(aml.quantity, 0)
                          END
                          * CASE WHEN am.move_type = 'in_invoice' THEN 1
                                 WHEN am.move_type = 'in_refund' THEN -1
                                 ELSE 0 END
                      ) AS qty_invoiced,
                      pol.id AS pol_id
                 FROM purchase_order po
            LEFT JOIN purchase_order_line pol ON pol.order_id = po.id
            LEFT JOIN account_move_line_purchase_order_line_rel rel ON rel.order_line_id = pol.id
            LEFT JOIN account_move_line aml ON aml.id = rel.move_line_id
            LEFT JOIN account_move am ON aml.move_id = am.id
            LEFT JOIN uom_uom uom_aml ON uom_aml.id = aml.product_uom_id
            LEFT JOIN uom_uom uom_pol ON uom_pol.id = pol.product_uom_id
                WHERE aml.parent_state = 'posted'
             GROUP BY pol.id
        """,
            precision_digits=precision_digits,
        )

        return SQL(
            """
            SELECT ('pol' || pol.id::TEXT || '-' || COALESCE(bl.id, 0)::TEXT
                    || '-' || ROW_NUMBER() OVER (PARTITION BY pol.id, bl.id ORDER BY pol.id)) AS id,
                   bl.budget_analytic_id AS budget_analytic_id,
                   bl.id AS budget_line_id,
                   'purchase.order' AS res_model,
                   po.id AS res_id,
                   po.date_order::DATE AS date,  -- `budget.report.date` is a Date; a timestamp here promotes the whole UNION column
                   pol.name AS description,
                   po.company_id AS company_id,
                   po.user_id AS user_id,
                   'committed' AS line_type,
                   0 AS budget,
                   COALESCE(pol.price_subtotal::FLOAT, pol.price_unit::FLOAT * pol.product_qty)
                        / COALESCE(NULLIF(pol.product_qty, 0), 1)
                        * (pol.product_qty - COALESCE(qty_invoiced_table.qty_invoiced, 0))
                        / po.currency_rate
                        * (a.rate)
                        * CASE WHEN ba.budget_type = 'both' THEN -1 ELSE 1 END AS committed,
                   0 AS achieved,
                   %(analytic_fields)s
              FROM purchase_order_line pol
         LEFT JOIN (%(qty_invoiced_table)s) qty_invoiced_table ON qty_invoiced_table.pol_id = pol.id
              JOIN purchase_order po ON pol.order_id = po.id AND po.state = 'done'
        CROSS JOIN JSONB_TO_RECORDSET(pol.analytic_json) AS a(rate FLOAT, %(field_cast)s)
         LEFT JOIN (budget_line bl
                    JOIN budget_analytic ba ON ba.id = bl.budget_analytic_id)
                ON (ba.company_id IS NULL OR po.company_id = ba.company_id)
               -- one conversion, both bounds: `date_order` is UTC and the budget
               -- bounds are plain dates, so an order placed in the evening local
               -- time otherwise lands in the next day's period -- or falls out of
               -- its own. The double `AT TIME ZONE` is deliberate: the first
               -- reads the naive column as UTC, the second renders it local.
               AND (po.date_order AT TIME ZONE 'UTC' AT TIME ZONE %(report_tz)s)::DATE
                   BETWEEN ba.date_from AND ba.date_to
               AND %(condition)s
             WHERE pol.product_qty > COALESCE(qty_invoiced_table.qty_invoiced, 0)
               -- `ba` comes from a LEFT JOIN: plain `!=` is NULL for a commitment
               -- under no budget and drops it, while the analytic branch keeps its
               -- uncovered rows. IS DISTINCT FROM keeps both grains the same.
               AND ba.budget_type IS DISTINCT FROM 'revenue'
            """,
            analytic_fields=SQL(", ").join(
                self.env["account.analytic.line"]._field_to_sql("a", fname)
                for fname in plan_fnames
            ),
            qty_invoiced_table=qty_invoiced_table,
            report_tz=self._get_report_timezone(),
            field_cast=SQL(", ").join(
                SQL("%s FLOAT", SQL.identifier(fname)) for fname in plan_fnames
            ),
            condition=SQL(" AND ").join(
                SQL(
                    "(%(bl)s IS NULL OR %(a)s = %(bl)s)",
                    bl=self.env["budget.line"]._field_to_sql("bl", fname),
                    a=self.env["account.analytic.line"]._field_to_sql("a", fname),
                )
                for fname in plan_fnames
            ),
        )

    @property
    def _table_query(self):
        if self._get_scoped_analytic_line_ids() is not None:
            return super()._table_query
        self.env["account.move.line"].flush_model()
        self.env["purchase.order"].flush_model()
        self.env["purchase.order.line"].flush_model()
        project_plan, other_plans = self.env["account.analytic.plan"]._get_all_plans()
        plan_fnames = [plan._column_name() for plan in project_plan | other_plans]
        return SQL(
            "%s UNION ALL %s",
            super()._table_query,
            self._get_pol_query(plan_fnames),
        )
