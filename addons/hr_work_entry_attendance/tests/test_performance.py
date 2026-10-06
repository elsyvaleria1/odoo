from datetime import date

from dateutil.relativedelta import relativedelta
from dateutil.rrule import DAILY, rrule

from odoo import Command
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "work_entry_attendance_perf")
class TestHrWorkEntryAttendancePerformance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env.user.company_id = cls.env["res.company"].create(
            {"name": "Flower Corporation"}
        )

        cls.work_entry_type_overtime = cls.env.ref(
            "hr_work_entry.work_entry_type_overtime"
        )

        cls.ruleset = cls.env["hr.attendance.overtime.ruleset"].create(
            {
                "name": "Ruleset schedule quantity",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "Rule schedule quantity",
                            "base_off": "quantity",
                            "expected_hours_from_contract": True,
                            "quantity_period": "day",
                            "work_entry_type_id": cls.work_entry_type_overtime.id,
                        }
                    )
                ],
            }
        )

        employees = cls.env["hr.employee"].create(
            [
                {
                    "name": f"Employee {i}",
                    "sex": "male",
                    "birthday": "1982-08-01",
                    "nationality_country_id": cls.env.ref("base.us").id,
                    "wage": 5000.0,
                    "date_version": date.today() - relativedelta(months=2),
                    "contract_date_start": date.today() - relativedelta(months=2),
                    "work_entry_source": "attendance",
                    "contract_date_end": False,
                    "ruleset_id": cls.ruleset.id,
                }
                for i in range(100)
            ]
        )
        for employee in employees:
            employee.create_version(
                {
                    "date_version": date.today() - relativedelta(months=1, days=15),
                    "wage": 5500,
                }
            )
            employee.create_version(
                {"date_version": date.today() - relativedelta(months=1), "wage": 6000}
            )

        vals = []
        for employee in employees:
            for day in rrule(
                DAILY,
                dtstart=date.today() - relativedelta(months=2),
                until=date.today(),
            ):
                vals.append(  # noqa: PERF401  explicit loop reads clearer
                    {
                        "employee_id": employee.id,
                        "check_in": day.strftime("%Y-%m-%d 08:00:%S"),
                        "check_out": day.strftime("%Y-%m-%d 16:36:%S"),
                    }
                )
        cls.attendances = cls.env["hr.attendance"].create(vals)

    def test_regenerate_work_entries(self):
        # The budget is the measured cost, not headroom. It read 1081 against a
        # measurement of 129 -- a gap wide enough that the whole regeneration
        # could have stopped batching without the test noticing, and
        # `assertQueryCount` only LOGS when it comes in under, so nothing said
        # so in the lane output either.
        slots = [
            {"date": attendance.date, "employee_id": attendance.employee_id.id}
            for attendance in self.attendances
        ]
        with self.profile():
            with self.assertQueryCount(129):
                self.env["wizard.hr.work.entry.regenerate"].regenerate_work_entries(
                    slots=slots
                )

        # And that it did the work: a budget met by a call that regenerated
        # nothing is the cheapest possible pass.
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "in", self.attendances.employee_id.ids)]
        )
        self.assertEqual(len(work_entries.employee_id), 100)
        # An attendance on a day the schedule does not cover produces no work
        # entry, so this is not one per attendance: the fixture spans two
        # months of calendar days and read 4500 of 6300, which is the weekday
        # share. The bound is loose on purpose -- the fixture is relative to
        # `date.today()`, so the exact weekday count moves daily, and a figure
        # that moves daily is a flake, not a measurement.
        self.assertGreater(len(work_entries), 0.6 * len(self.attendances))
