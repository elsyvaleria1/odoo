from datetime import datetime

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPlanningAttendanceAnalysisReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Analysed", "hourly_cost": 10.0}
        )
        cls.env["planning.slot"].create(
            {
                "resource_id": cls.employee.resource_id.id,
                "start_datetime": datetime(2026, 9, 7, 8, 0),
                "end_datetime": datetime(2026, 9, 11, 17, 0),
                "allocated_hours": 8.0,
            }
        )
        cls.env["hr.attendance"].create(
            {
                "employee_id": cls.employee.id,
                "check_in": datetime(2026, 9, 8, 8, 0),
                "check_out": datetime(2026, 9, 8, 16, 0),
            }
        )
        cls.env.flush_all()
        cls.report = cls.env["planning.attendance.analysis.report"]

    def _rows(self):
        self.env.invalidate_all()
        return self.report.search_read(
            [("employee_id", "=", self.employee.id)],
            ["entry_date", "effective_hours", "effective_costs", "currency_id"],
        )

    def test_a_shift_spanning_days_gives_one_row_per_day_not_one_row_five_times(self):
        rows = self._rows()
        self.assertEqual(len(rows), 5)
        self.assertEqual(len({row["id"] for row in rows}), 5)
        self.assertEqual(
            len({row["entry_date"] for row in rows}),
            5,
            "each row must carry its own date",
        )

    def test_the_day_that_was_attended_reports_its_attendance(self):
        [attended] = [
            row
            for row in self._rows()
            if row["entry_date"] == datetime(2026, 9, 8).date()
        ]
        self.assertEqual(attended["effective_hours"], 7.0)
        self.assertEqual(attended["effective_costs"], 70.0)

    def test_reading_rows_agrees_with_grouping_them(self):
        rows = {row["entry_date"]: row["effective_hours"] for row in self._rows()}
        grouped = {
            group["entry_date:day"][0]: group["effective_hours:sum"]
            for group in self.report.formatted_read_group(
                [("employee_id", "=", self.employee.id)],
                ["entry_date:day"],
                ["effective_hours:sum"],
            )
        }
        self.assertEqual(
            {date.isoformat(): hours for date, hours in rows.items()}, grouped
        )

    def test_the_cost_columns_carry_the_company_currency(self):
        row = self._rows()[0]
        self.assertEqual(row["currency_id"][0], self.env.company.currency_id.id)
        self.assertEqual(
            self.report._fields["effective_costs"].get_description(self.env)["type"],
            "monetary",
        )
