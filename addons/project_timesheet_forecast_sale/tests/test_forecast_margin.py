from datetime import date

from odoo.tests import tagged

from odoo.addons.sale_timesheet.tests.common import TestCommonSaleTimesheet


@tagged("post_install", "-at_install")
class TestForecastAnalysisEffectiveMargin(TestCommonSaleTimesheet):
    def test_the_effective_margin_spends_what_the_timesheet_recorded(self):
        employee = self.env["hr.employee"].create(
            {"name": "Margin", "hourly_cost": 10.0}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_delivery_timesheet3.id,
                            "product_qty": 10,
                        },
                    )
                ],
            }
        )
        order.action_confirm()
        sale_line = order.line_ids[0]
        project = sale_line.project_id or self.env["project.project"].search(
            [("sale_order_id", "=", order.id)], limit=1
        )
        self.assertTrue(project)
        project.write({"allow_timesheets": True, "allow_billable": True})
        self.env["project.sale.line.employee.map"].create(
            {
                "project_id": project.id,
                "employee_id": employee.id,
                "cost": 95.0,
                "sale_line_id": sale_line.id,
            }
        )
        timesheet = self.env["account.analytic.line"].create(
            {
                "name": "Margin",
                "project_id": project.id,
                "employee_id": employee.id,
                "unit_amount": 4.0,
                "date": date(2021, 10, 25),
                "so_line": sale_line.id,
            }
        )
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(timesheet.amount, -380.0)

        [row] = self.env["project.timesheet.forecast.report.analysis"].search_read(
            [("employee_id", "=", employee.id), ("line_type", "=", "timesheet")],
            ["effective_revenues", "effective_costs", "effective_margin"],
        )
        self.assertEqual(row["effective_costs"], 380.0)
        self.assertEqual(
            row["effective_margin"], row["effective_revenues"] - row["effective_costs"]
        )
