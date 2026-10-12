import importlib.util
from datetime import date, datetime, time, timedelta
from pathlib import Path

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestUpgradeSharedClosures(TransactionCase):
    def _migrate(self):
        path = (
            Path(__file__).parents[1] / "migrations" / "1.17" / "end-shared-closures.py"
        )
        spec = importlib.util.spec_from_file_location("hr_holidays_1_17", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.env.cr, "1.16")
        self.env.invalidate_all()

    def test_a_released_closure_gives_the_day_back_to_every_company(self):
        mine, theirs = self.env["res.company"].create(
            [{"name": "Entered the closure"}, {"name": "Shares the calendar"}]
        )
        shared = self.env["resource.calendar"].create(
            {"name": "Shared across companies", "company_id": False, "tz": "UTC"}
        )
        employees = self.env["hr.employee"].create(
            [
                {
                    "name": name,
                    "company_id": company.id,
                    "resource_calendar_id": shared.id,
                }
                for name, company in [
                    ("Mine", mine),
                    ("Theirs", theirs),
                    ("Refused", theirs),
                ]
            ]
        )
        leave_type = self.env["hr.leave.type"].create(
            {
                "name": "Paid Time Off",
                "requires_allocation": False,
                "leave_validation_type": "hr",
            }
        )
        monday = date.today() + timedelta(days=21 - date.today().weekday())
        leaves = self.env["hr.leave"].create(
            [
                {
                    "name": "Week off",
                    "employee_id": employee.id,
                    "holiday_status_id": leave_type.id,
                    "request_date_from": monday,
                    "request_date_to": monday + timedelta(days=4),
                }
                for employee in employees
            ]
        )
        leaves[:2].action_approve()
        leaves[2].action_refuse()
        self.env.cr.execute(
            """
            INSERT INTO resource_schedule_exception
                   (name, calendar_id, date_from, date_to, time_type_id)
            VALUES ('Released closure', %s, %s, %s, %s)
            """,
            (
                shared.id,
                datetime.combine(monday + timedelta(days=2), time.min),
                datetime.combine(monday + timedelta(days=2), time(23, 59)),
                self.env["resource.time.type"]._get_leave_type().id,
            ),
        )
        self.env.invalidate_all()
        self.assertEqual(leaves.mapped("number_of_days"), [5, 5, 5])

        self._migrate()
        self.assertEqual(leaves.mapped("number_of_days"), [4, 4, 5])
        self.assertEqual(leaves.mapped("state"), ["validate", "validate", "refuse"])

        self._migrate()
        self.assertEqual(leaves.mapped("number_of_days"), [4, 4, 5])
