from datetime import UTC, datetime

from odoo.fields import Date
from odoo.tests.common import TransactionCase


class TestWorkEntriesGanttProgressBar(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        calendar = cls.env.company.resource_calendar_id
        cls.displayed_employee, cls.other_employee = cls.env["hr.employee"].create(
            [
                {
                    "name": "Displayed in the gantt",
                    "resource_calendar_id": calendar.id,
                    "date_version": Date.to_date("2025-01-01"),
                    "contract_date_start": Date.to_date("2025-01-01"),
                },
                {
                    "name": "Not displayed in the gantt",
                    "resource_calendar_id": calendar.id,
                    "date_version": Date.to_date("2025-01-01"),
                    "contract_date_start": Date.to_date("2025-01-01"),
                },
            ]
        )

    def test_progress_bar_ignores_employees_outside_res_ids(self):
        values = self.env["hr.work.entry"]._gantt_progress_bar(
            "employee_id",
            self.displayed_employee.ids,
            datetime(2025, 3, 1, tzinfo=UTC),
            datetime(2025, 4, 1, tzinfo=UTC),
        )

        self.assertEqual(
            set(values),
            set(self.displayed_employee.ids),
            "work entries were generated for employees the gantt never asked about",
        )
        self.assertGreater(
            values[self.displayed_employee.id]["max_value"],
            0,
            "the expected duration of the displayed employee went missing",
        )
