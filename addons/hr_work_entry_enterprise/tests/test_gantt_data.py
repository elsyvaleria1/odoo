from datetime import UTC, datetime

from odoo.fields import Date
from odoo.tests.common import TransactionCase


class TestWorkEntriesGanttData(TransactionCase):
    def test_employee_with_contract_and_no_work_entries_gets_a_row(self):
        calendar = self.env.company.resource_calendar_id
        ghost_employee = self.env["hr.employee"].create(
            {
                "name": "Ghost, no work entries yet",
                "resource_calendar_id": calendar.id,
                "date_version": Date.to_date("2025-01-01"),
                "contract_date_start": Date.to_date("2025-01-01"),
            }
        )

        result = self.env["hr.work.entry"].get_gantt_data(
            domain=[],
            groupby=["employee_id"],
            read_specification={"employee_id": {}},
            start_date="2025-01-01 00:00:00",
            stop_date="2025-02-01 00:00:00",
        )

        group_employee_ids = {
            group["employee_id"][0]
            for group in result["groups"]
            if group.get("employee_id")
        }
        self.assertIn(
            ghost_employee.id,
            group_employee_ids,
            "an employee with an active contract and no work entries yet "
            "must still get a gantt row",
        )

    def test_archived_employee_gets_no_phantom_row(self):
        calendar = self.env.company.resource_calendar_id
        archived_employee = self.env["hr.employee"].create(
            {
                "name": "Archived, gone",
                "resource_calendar_id": calendar.id,
                "date_version": Date.to_date("2025-01-01"),
                "contract_date_start": Date.to_date("2025-01-01"),
            }
        )
        archived_employee.active = False

        result = self.env["hr.work.entry"].get_gantt_data(
            domain=[],
            groupby=["employee_id"],
            read_specification={"employee_id": {}},
            start_date="2025-01-01 00:00:00",
            stop_date="2025-02-01 00:00:00",
        )

        group_employee_ids = {
            group["employee_id"][0]
            for group in result["groups"]
            if group.get("employee_id")
        }
        self.assertNotIn(
            archived_employee.id,
            group_employee_ids,
            "an archived employee must not appear as a phantom gantt row",
        )

    def test_unavailability_covers_window_before_calendar_change(self):
        calendar_a = self.env.company.resource_calendar_id
        calendar_b = calendar_a.copy({"name": "Calendar B"})
        changed = self.env["hr.employee"].create(
            {
                "name": "Changed calendar",
                "tz": "UTC",
                "resource_calendar_id": calendar_a.id,
                "date_version": Date.to_date("2025-01-01"),
                "contract_date_start": Date.to_date("2025-01-01"),
            }
        )
        changed.version_id.copy(
            {
                "date_version": Date.to_date("2025-09-15"),
                "resource_calendar_id": calendar_b.id,
            }
        )
        control = self.env["hr.employee"].create(
            {
                "name": "Single calendar",
                "tz": "UTC",
                "resource_calendar_id": calendar_a.id,
                "date_version": Date.to_date("2025-01-01"),
                "contract_date_start": Date.to_date("2025-01-01"),
            }
        )
        start = datetime(2025, 9, 1, tzinfo=UTC)
        stop = datetime(2025, 10, 1, tzinfo=UTC)
        change = datetime(2025, 9, 15, tzinfo=UTC)
        result = self.env["hr.work.entry"]._gantt_unavailability(
            "employee_id", [control.id, changed.id], start, stop, "month"
        )
        for employee in (control, changed):
            before_change = [
                interval
                for interval in result[employee.id]
                if interval["start"] < change
            ]
            self.assertTrue(
                before_change,
                f"{employee.name}: weekends before the calendar change must "
                "be unavailable",
            )
