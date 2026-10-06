from datetime import date, datetime

from odoo import Command
from odoo.tests.common import TransactionCase


class TestGanttUnavailability(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Monday 8h",
                "tz": "UTC",
                "hours_per_day": 8.0,
                "attendance_ids": [
                    Command.create(
                        {
                            "name": "Mon Morning",
                            "dayofweek": "0",
                            "hour_from": 9,
                            "hour_to": 12,
                            "day_period": "morning",
                        }
                    ),
                    Command.create(
                        {
                            "name": "Mon Afternoon",
                            "dayofweek": "0",
                            "hour_from": 12,
                            "hour_to": 17,
                            "day_period": "afternoon",
                        }
                    ),
                ],
            }
        )
        cls.contracted = cls.env["hr.employee"].create(
            {
                "name": "Contracted Employee",
                "resource_calendar_id": cls.calendar.id,
                "date_version": date(2024, 1, 1),
                "contract_date_start": date(2024, 1, 1),
                "wage": 10,
            }
        )
        cls.uncontracted = cls.env["hr.employee"].create(
            {"name": "Free Employee", "resource_calendar_id": cls.calendar.id}
        )

    def test_unavailability_for_contracted_employee(self):
        """Check that a contracted Monday-only employee gets notable
        unavailability intervals covering the rest of the week."""
        result = self.env["hr.leave"]._gantt_unavailability(
            "employee_id",
            [self.contracted.id],
            datetime(2024, 1, 8),
            datetime(2024, 1, 14),
            "week",
        )
        intervals = result[self.contracted.id]
        self.assertTrue(intervals, "a Monday-only calendar must yield unavailability")
        for interval in intervals:
            self.assertLess(interval["start"], interval["stop"])
            self.assertGreaterEqual(
                (interval["stop"] - interval["start"]).total_seconds(),
                3600,
                "sub-cell intervals must be filtered out on week scale",
            )

    def test_unavailability_for_employee_without_contract(self):
        """Check that employees without contract data fall back to the
        resource-calendar path and still report intervals."""
        result = self.env["hr.leave"]._gantt_unavailability(
            "employee_id",
            [self.uncontracted.id],
            datetime(2024, 1, 8),
            datetime(2024, 1, 14),
            "week",
        )
        self.assertIn(self.uncontracted.id, result)
        self.assertIsInstance(result[self.uncontracted.id], list)
        self.assertTrue(result[self.uncontracted.id])

    def test_unavailability_skips_stale_contract_version(self):
        """F9 regression: a stale `hr.version` sibling sharing the same
        contract dates (e.g. an earlier salary-raise amendment under one
        continuous contract) must be skipped rather than computed and then
        silently discarded via an inverted interval."""
        stale_start = date(2020, 1, 1)
        current_start = date(2024, 1, 1)
        employee = self.env["hr.employee"].create(
            {
                "name": "Amended Contract Employee",
                "resource_calendar_id": self.calendar.id,
                "date_version": stale_start,
                "contract_date_start": stale_start,
                "wage": 10,
            }
        )
        # A later amendment (e.g. a raise) under the SAME continuous
        # contract: shares `contract_date_start` with the first version
        # (per `hr.version._compute_dates`), so both match
        # `_gantt_unavailability`'s search, but only this one's own sliced
        # window covers the query below.
        self.env["hr.version"].create(
            {
                "employee_id": employee.id,
                "resource_calendar_id": self.calendar.id,
                "date_version": current_start,
                "contract_date_start": stale_start,
                "wage": 20,
            }
        )

        call_count = 0
        original = type(self.env["resource.calendar"])._unavailable_intervals_batch

        def counting_wrapper(self_calendar, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original(self_calendar, *args, **kwargs)

        self.patch(
            type(self.env["resource.calendar"]),
            "_unavailable_intervals_batch",
            counting_wrapper,
        )

        result = self.env["hr.leave"]._gantt_unavailability(
            "employee_id",
            [employee.id],
            datetime(2024, 6, 3),
            datetime(2024, 6, 10),
            "week",
        )

        self.assertEqual(
            call_count,
            1,
            "the stale 2020 version must be skipped; only the current "
            "version covering the query window should be processed",
        )
        intervals = result[employee.id]
        self.assertTrue(
            intervals, "the current version must still yield unavailability"
        )
        for interval in intervals:
            self.assertLess(interval["start"], interval["stop"])

    def test_unavailability_other_field_delegates(self):
        """Check that non-employee groupings delegate to the generic gantt
        implementation."""
        result = self.env["hr.leave"]._gantt_unavailability(
            "department_id",
            [],
            datetime(2024, 1, 8),
            datetime(2024, 1, 14),
            "week",
        )
        self.assertEqual(result, {})
