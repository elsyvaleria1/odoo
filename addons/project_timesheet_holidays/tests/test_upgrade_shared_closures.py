import importlib.util
from datetime import date, datetime, time, timedelta
from pathlib import Path

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestUpgradeSharedClosures(TransactionCase):
    def _migrate(self):
        path = (
            Path(__file__).parents[1] / "migrations" / "1.2" / "end-shared-closures.py"
        )
        spec = importlib.util.spec_from_file_location("pth_1_2", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.env.cr, "1.1")
        self.env.invalidate_all()

    def test_a_released_closure_books_time_off_for_every_company(self):
        mine, theirs = self.env["res.company"].create(
            [{"name": "Entered the closure"}, {"name": "Shares the calendar"}]
        )
        shared = self.env["resource.calendar"].create(
            {"name": "Shared across companies", "company_id": False, "tz": "UTC"}
        )
        booked, free, on_leave = self.env["hr.employee"].create(
            [
                {
                    "name": name,
                    "company_id": company.id,
                    "resource_calendar_id": shared.id,
                }
                for name, company in [
                    ("Booked", mine),
                    ("Free", theirs),
                    ("On leave", theirs),
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
        closed_day = date.today() + timedelta(days=23 - date.today().weekday())
        self.env["hr.leave"].create(
            {
                "name": "Day off",
                "employee_id": on_leave.id,
                "holiday_status_id": leave_type.id,
                "request_date_from": closed_day,
                "request_date_to": closed_day,
            }
        ).action_approve()
        self.env.cr.execute(
            """
            INSERT INTO resource_schedule_exception
                   (name, calendar_id, date_from, date_to, time_type_id)
            VALUES ('Released closure', %s, %s, %s, %s)
         RETURNING id
            """,
            (
                shared.id,
                datetime.combine(closed_day, time.min),
                datetime.combine(closed_day, time(23, 59)),
                self.env["resource.time.type"]._get_leave_type().id,
            ),
        )
        closure = self.env["resource.schedule.exception"].browse(
            self.env.cr.fetchone()[0]
        )
        self.env.invalidate_all()
        entered = closure.with_context(
            allowed_company_ids=mine.ids
        )._generate_public_time_off_timesheets(booked)
        self.assertEqual(entered.employee_id, booked)

        self._migrate()
        self.assertEqual(closure.timesheet_ids.employee_id, booked | free)
        self.assertIn(entered, closure.timesheet_ids)

        self._migrate()
        self.assertEqual(len(closure.timesheet_ids), 2)
