from datetime import datetime

from odoo.tests import tagged

from odoo.addons.sale_timesheet.tests.common import TestCommonSaleTimesheet


@tagged("-at_install", "post_install")
class TestSaleTimesheetEnterpriseRanking(TestCommonSaleTimesheet):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.period_start = datetime(2023, 4, 1, 7, 0, 0)
        cls.period_end = datetime(2023, 4, 30, 18, 0, 0)
        cls.today = datetime(2023, 4, 25, 7, 0, 0)
        cls.so = cls.env["sale.order"].create(
            {
                "company_id": cls.employee_user.company_id.id,
                "partner_id": cls.partner_a.id,
                "partner_invoice_id": cls.partner_a.id,
                "partner_shipping_id": cls.partner_a.id,
            }
        )
        cls.sol = cls.env["sale.order.line"].create(
            {
                "product_id": cls.product_order_timesheet3.id,
                "product_qty": 10,
                "order_id": cls.so.id,
            }
        )
        cls.project_billable = cls.env["project.project"].create(
            {
                "name": "Billable project",
                "sale_line_id": cls.sol.id,
                "allow_billable": True,
            }
        )
        cls.task_billable = cls.env["project.task"].create(
            {
                "name": "Billable Task",
                "sale_line_id": cls.sol.id,
                "project_id": cls.project_billable.id,
            }
        )
        cls.employee_user.billable_time_target = 160
        cls.env["res.config.settings"].create(
            {"timesheet_show_rates": True, "timesheet_show_leaderboard": True}
        ).execute()

    def test_get_timesheet_ranking_data_with_timesheet_show_rates_disabled(self):
        self.env["res.config.settings"].create(
            {"timesheet_show_rates": False, "timesheet_show_leaderboard": False}
        ).execute()
        self.assertFalse(
            self.env["res.company"].get_timesheet_ranking_data(
                self.period_start, self.period_end, self.today, True
            ),
            "An empty dict should be returned since the feature is disabled on the company.",
        )

    def test_get_timesheet_ranking_data_with_timesheet_show_leaderboard_disabled(self):
        self.env["res.config.settings"].create(
            {"timesheet_show_leaderboard": False}
        ).execute()
        self.employee_user.user_id = self.env.user
        self.env["account.analytic.line"].create(
            {
                "employee_id": self.employee_user.id,
                "unit_amount": 8,
                "date": datetime(2023, 4, 15, 7, 0, 0, 0),
                "project_id": self.project_billable.id,
                "task_id": self.task_billable.id,
            }
        )
        data = self.env["res.company"].get_timesheet_ranking_data(
            self.period_start, self.period_end, self.today, True
        )
        self.assertTrue(data)
        self.assertTrue(data["leaderboard"])
        self.assertEqual(len(data["leaderboard"]), 1)
        self.assertDictEqual(
            data["leaderboard"][0],
            {
                "id": self.employee_user.id,
                "name": self.employee_user.name,
                "billable_time_target": self.employee_user.billable_time_target,
                "billable_time": 0.0,
                "total_time": 8.0,
                "total_valid_time": 8.0,
                "billing_rate": 0.0,
            },
        )
        self.assertEqual(
            data["billable_time_target"], self.employee_user.billable_time_target
        )

    def test_fetch_tip(self):
        data = self.company_data["company"].get_timesheet_ranking_data(
            self.period_start, self.period_end, self.today, True
        )
        self.assertTrue(
            data.get("tip"),
            "A tip should be set in the company's timesheet ranking data.",
        )

    def test_total_time_target(self):
        data = [
            self.company_data["company"].get_timesheet_ranking_data(
                self.period_start, self.period_end, date, False
            )
            for date in [
                datetime(2023, 4, 15, 0, 0, 0),
                datetime(2023, 5, 1, 0, 0, 0),
                datetime(2023, 3, 31, 0, 0, 0),
            ]
        ]

        self.assertIsNotNone(
            data[0].get("total_time_target"),
            "Today's date is set between the time window, so total_time_target should be set.",
        )
        self.assertIsNotNone(
            data[1].get("total_time_target"),
            "Today's date is set after the time window, so total_time_target should be set.",
        )
        self.assertFalse(
            data[2].get("total_time_target"),
            "Today's date is set after the time window, so total_time_target should be set to false.",
        )

    def test_total_time(self):
        self.env["account.analytic.line"].create(
            {
                "employee_id": self.employee_user.id,
                "unit_amount": 8,
                "date": datetime(2023, 4, 15, 7, 0, 0, 0),
                "project_id": self.project_billable.id,
                "task_id": self.task_billable.id,
            }
        )
        ranking_data = self.employee_user.company_id.get_timesheet_ranking_data(
            self.period_start, self.period_end, self.today, False
        )
        self.assertEqual(
            ranking_data["leaderboard"][0]["total_valid_time"],
            8.0,
            "The employee's total valid time should be 8 since today's date is past the timesheet's date.",
        )
        self.assertEqual(
            ranking_data["leaderboard"][0]["total_time"],
            8.0,
            "The employee's total time should be 8.",
        )

        self.env["account.analytic.line"].create(
            {
                "employee_id": self.employee_user.id,
                "unit_amount": 8,
                "date": datetime(2023, 4, 26, 7, 0, 0, 0),
                "project_id": self.project_billable.id,
                "task_id": self.task_billable.id,
            }
        )
        ranking_data = self.employee_user.company_id.get_timesheet_ranking_data(
            self.period_start, self.period_end, self.today, False
        )
        self.assertEqual(
            ranking_data["leaderboard"][0]["total_valid_time"],
            8.0,
            "The employee's total valid time should still be 8 since the timesheet's date is past today's date (and so invalid).",
        )
        self.assertEqual(
            ranking_data["leaderboard"][0]["total_time"],
            16.0,
            "The employee's total time should be 16.",
        )
