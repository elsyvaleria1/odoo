from datetime import datetime

from odoo.tests import tagged

from odoo.addons.project_timesheet_holidays.tests.test_timesheet_holidays import (
    TestTimesheetHolidays,
)
from odoo.addons.sale_timesheet_enterprise.tests.test_ranking import (
    TestSaleTimesheetEnterpriseRanking,
)


@tagged("-at_install", "post_install")
class TestSaleTimesheetEnterpriseHolidaysRanking(
    TestTimesheetHolidays, TestSaleTimesheetEnterpriseRanking
):
    def test_ranking_exclude_timeoff(self):
        self.env.user.group_ids |= self.env.ref("hr_holidays.group_hr_holidays_user")
        self.employee_user.leave_manager_id = self.env.user
        holiday = self.Requests.create(
            {
                "name": "Time Off 1",
                "employee_id": self.employee_user.id,
                "holiday_status_id": self.hr_leave_type_with_ts.id,
                "request_date_from": datetime(2023, 4, 10, 7, 0, 0, 0),
                "request_date_to": datetime(2023, 4, 10, 18, 0, 0, 0),
            }
        )
        holiday.action_approve()
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
            self.period_start, self.period_end, self.today, fetch_tip=False
        )
        timesheets = self.env["account.analytic.line"].search(
            [("employee_id", "=", self.employee_user.id)]
        )

        self.assertEqual(
            timesheets.mapped("unit_amount"),
            [8.0, 8.0],
            "The employee should have two timesheets with unit time of 8.0 each",
        )
        self.assertEqual(
            ranking_data["leaderboard"][0]["total_time"],
            8.0,
            "The employee's total time should be 8.0",
        )
