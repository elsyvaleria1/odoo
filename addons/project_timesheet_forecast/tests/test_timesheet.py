from datetime import date, datetime, timedelta

from odoo.tests import freeze_time

from odoo.addons.project_forecast.tests.common import TestCommonForecast


class TestPlanningTimesheet(TestCommonForecast):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.setUpEmployees()
        cls.setUpProjects()

    def test_gantt_progress_bar_group_by_project(self):
        """
        This test ensures that the _gantt_progress_bar_project_id return values is correct.
        - Every project_id present in the res_ids should be present in the dict.
        - The 'value' should be 0 if the project contains no planning slot available in the date range given, else it should be equal to the total of every available slot for the given date range.
        - The 'max value' should be equal to the 'allocated_hours' field for each project.
        """
        projects = (
            project_without_slot,
            project_slot_not_in_date_range,
            project_slot_in_date_range,
        ) = (
            self.env["project.project"]
            .with_context(tracking_disable=True)
            .create(
                [
                    {
                        "name": "Project no slot",
                        "allocated_hours": 40,
                    },
                    {
                        "name": "Project slot not in date range",
                        "allocated_hours": 50,
                    },
                    {
                        "name": "Project slot in date range",
                        "allocated_hours": 60,
                    },
                ]
            )
        )
        start_date = datetime(2021, 10, 22, 8, 0, 0)
        end_date = datetime(2021, 10, 29, 8, 0, 0)
        planning_vals = {
            "resource_id": self.resource_joseph.id,
            "state": "2_published",
            "allow_timesheets": True,
        }
        self.env["planning.slot"].create(
            [
                {
                    **planning_vals,
                    "project_id": project_slot_in_date_range.id,
                    "start_datetime": datetime(2021, 10, 25, 8, 0, 0),
                    "end_datetime": datetime(2021, 10, 26, 12, 0, 0),
                },
                {
                    **planning_vals,
                    "project_id": project_slot_in_date_range.id,
                    "start_datetime": datetime(2021, 10, 26, 13, 0, 0),
                    "end_datetime": datetime(2021, 10, 26, 17, 0, 0),
                },
                {
                    **planning_vals,
                    "project_id": project_slot_not_in_date_range.id,
                    "start_datetime": datetime(2021, 10, 20, 8, 0, 0),
                    "end_datetime": datetime(2021, 10, 21, 12, 0, 0),
                },
            ]
        )
        res_ids = projects.ids
        expected_values = {
            project_without_slot.id: {"value": 0.0, "max_value": 40.0},
            project_slot_not_in_date_range.id: {"value": 0.0, "max_value": 50.0},
            project_slot_in_date_range.id: {
                "value": 16.0,
                "max_value": 60.0,
            },  # 12 hours in the 1st slot + 4 hours in the 2nd slot
        }
        values = self.env["planning.slot"]._gantt_progress_bar_project_id(
            res_ids, start_date, end_date
        )
        self.assertDictEqual(values, expected_values)

    @freeze_time("2019-06-06 01:00:00")
    def test_timesheets_forecast_analysis_with_weekend_included(self):
        self.project_opera.write({"allow_timesheets": True})
        self.env["planning.slot"].create(
            {
                "project_id": self.project_opera.id,
                "employee_id": self.employee_bert.id,
                "resource_id": self.resource_bert.id,
                "allocated_hours": 40,
                "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                # 6/8/2019 and 6/9/2019 are weekend days
                "end_datetime": datetime(2019, 6, 12, 17, 0, 0),
                "allocated_percentage": 100,
                "state": "1_draft",
            }
        )
        self.env["planning.slot"].flush_model()
        result = self.env[
            "project.timesheet.forecast.report.analysis"
        ].formatted_read_group(
            domain=[["project_id", "=", self.project_opera.id]],
            groupby=["entry_date:month"],
            aggregates=["planned_hours:sum"],
        )
        self.assertEqual((result[0]["planned_hours:sum"]), 40)

    def test_compute_slot_effective_hours(self):
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.employee_bert.resource_id.id,
                "project_id": self.project_opera.id,
                "start_datetime": datetime(2024, 1, 1, 8, 0, 0),
                "end_datetime": datetime(2024, 1, 31, 17, 0, 0),
            }
        )
        self.assertEqual(slot.effective_hours, 0)
        self.env["account.analytic.line"].create(
            {
                "name": "Test Timesheet",
                "unit_amount": 2,
                "project_id": self.project_opera.id,
                "task_id": self.task_opera_place_new_chairs.id,
                "employee_id": self.employee_bert.id,
                "date": date(2024, 1, 15),
            }
        )
        self.assertEqual(slot.effective_hours, 2)

    def test_planning_analysis_report_fields(self):
        """This test ensure that the fields of the planning analysis report are correctly computed"""
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.employee_bert.resource_id.id,
                "project_id": self.project_opera.id,
                "start_datetime": datetime(2025, 1, 22, 0, 0, 0),
                "end_datetime": datetime(2025, 1, 23, 0, 0, 0),
                "state": "2_published",
                "allow_timesheets": True,
            }
        )
        self.env["account.analytic.line"].create(
            {
                "name": "Test Timesheet",
                "unit_amount": 2,
                "project_id": self.project_opera.id,
                "task_id": self.task_opera_place_new_chairs.id,
                "employee_id": self.employee_bert.id,
                "date": date(2025, 1, 22),
            }
        )
        slot.invalidate_recordset()

        effective_hours, remaining_hours, percentage_hours = self.env[
            "planning.analysis.report"
        ]._read_group(
            [("slot_id", "=", slot.id)],
            aggregates=[
                "effective_hours:sum",
                "remaining_hours:sum",
                "percentage_hours:avg",
            ],
        )[0]

        self.assertEqual(
            effective_hours, 2.0, "Effective hours should match the timesheet entry"
        )
        self.assertEqual(
            remaining_hours,
            6.0,
            "Remaining hours should be Allocated Hours - Effective hours",
        )
        self.assertEqual(
            percentage_hours, 25.0, "Percentage hours should be calculated properly"
        )


class TestForecastAnalysisEffectiveCost(TestCommonForecast):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpEmployees()
        cls.setUpProjects()
        cls.project_opera.allow_timesheets = True
        cls.employee_joseph.hourly_cost = 10.0

    def _effective(self, employee):
        self.env.flush_all()
        self.env.invalidate_all()
        return self.env["project.timesheet.forecast.report.analysis"].search_read(
            [("employee_id", "=", employee.id), ("line_type", "=", "timesheet")],
            ["effective_hours", "effective_costs"],
        )

    def test_the_effective_cost_is_what_the_timesheet_recorded(self):
        timesheet = self.env["account.analytic.line"].create(
            {
                "name": "Recorded",
                "project_id": self.project_opera.id,
                "employee_id": self.employee_joseph.id,
                "unit_amount": 4.0,
                "date": date(2021, 10, 25),
            }
        )
        self.assertEqual(timesheet.amount, -40.0)
        timesheet.amount = -380.0

        [row] = self._effective(self.employee_joseph)
        self.assertEqual(row["effective_hours"], 4.0)
        self.assertEqual(row["effective_costs"], 380.0)

    def test_a_later_raise_does_not_re_cost_past_timesheets(self):
        self.env["account.analytic.line"].create(
            {
                "name": "Before the raise",
                "project_id": self.project_opera.id,
                "employee_id": self.employee_joseph.id,
                "unit_amount": 4.0,
                "date": date(2021, 10, 25),
            }
        )
        [before] = self._effective(self.employee_joseph)
        self.employee_joseph.hourly_cost = 30.0
        [after] = self._effective(self.employee_joseph)

        self.assertEqual(before["effective_costs"], 40.0)
        self.assertEqual(after["effective_costs"], 40.0)


class TestPlanningSlotEffectiveCost(TestCommonForecast):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpEmployees()
        cls.setUpProjects()
        cls.project_opera.allow_timesheets = True
        cls.employee_joseph.hourly_cost = 10.0
        cls.slot = cls.env["planning.slot"].create(
            {
                "resource_id": cls.employee_joseph.resource_id.id,
                "project_id": cls.project_opera.id,
                "start_datetime": datetime(2021, 10, 25, 8, 0),
                "end_datetime": datetime(2021, 10, 29, 17, 0),
                "allocated_hours": 8.0,
            }
        )

    def _timesheet(self, **overrides):
        values = {
            "name": "Slot cost",
            "project_id": self.project_opera.id,
            "employee_id": self.employee_joseph.id,
            "unit_amount": 4.0,
            "date": date(2021, 10, 26),
        }
        values.update(overrides)
        return self.env["account.analytic.line"].create(values)

    def _read(self, field):
        self.env.flush_all()
        self.env.invalidate_all()
        return self.slot[field]

    def test_the_slot_costs_its_timesheets_at_what_they_recorded(self):
        timesheet = self._timesheet()
        self.assertEqual(timesheet.amount, -40.0)
        # Read the slot before rewriting the amount, so the first recompute has
        # to land: without it both writes fold into one pending compute and the
        # test passes whether or not `amount` is a dependency of it.
        self.assertEqual(self._read("effective_hours_cost"), 40.0)

        timesheet.amount = -380.0
        self.assertEqual(self._read("effective_hours"), 4.0)
        self.assertEqual(self._read("effective_hours_cost"), 380.0)

    def test_a_later_raise_does_not_re_cost_a_slot(self):
        self._timesheet()
        before = self._read("effective_hours_cost")
        self.employee_joseph.hourly_cost = 30.0
        self.assertEqual(before, 40.0)
        self.assertEqual(self._read("effective_hours_cost"), 40.0)

    def test_a_timesheet_moved_out_of_the_window_stops_counting(self):
        timesheet = self._timesheet()
        self.assertEqual(self._read("effective_hours"), 4.0)
        self.assertEqual(self._read("effective_hours_cost"), 40.0)

        timesheet.date = date(2021, 12, 1)
        self.assertEqual(self._read("effective_hours"), 0.0)
        self.assertEqual(self._read("effective_hours_cost"), 0.0)

    def test_a_timesheet_reassigned_to_someone_else_stops_counting(self):
        timesheet = self._timesheet()
        self.assertEqual(self._read("effective_hours"), 4.0)

        timesheet.employee_id = self.employee_bert
        self.assertEqual(self._read("effective_hours"), 0.0)
        self.assertEqual(self._read("effective_hours_cost"), 0.0)

    def test_the_analysis_report_reads_the_recorded_cost(self):
        timesheet = self._timesheet()
        timesheet.amount = -380.0
        self.env.flush_all()
        self.env.invalidate_all()
        [row] = self.env["planning.analysis.report"].search_read(
            [("employee_id", "=", self.employee_joseph.id)],
            ["effective_hours_cost", "allocated_hours_cost"],
        )
        self.assertEqual(row["effective_hours_cost"], 380.0)
        self.assertEqual(row["allocated_hours_cost"], 80.0)

    def _slots(self, count):
        base = datetime(2021, 10, 25, 8, 0)
        return self.env["planning.slot"].create(
            [
                {
                    "resource_id": self.employee_joseph.resource_id.id,
                    "project_id": self.project_opera.id,
                    "start_datetime": base + timedelta(days=index),
                    "end_datetime": base + timedelta(days=index, hours=8),
                    "allocated_hours": 8.0,
                }
                for index in range(count)
            ]
        )

    def _cost_of_a_timesheet_with(self, extra_slots):
        # The recompute has to be provoked, not merely read: `effective_hours_cost`
        # is stored, so reading it after `invalidate_all` is a column read and
        # costs the same whatever the compute does. Writing a timesheet is what
        # marks every slot of the project dirty.
        self._slots(extra_slots)
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        self._timesheet()
        self.env.flush_all()
        return self.env.cr.sql_statement_count - before

    def test_recomputing_many_shifts_does_not_cost_a_query_per_shift(self):
        few = self._cost_of_a_timesheet_with(4)
        many = self._cost_of_a_timesheet_with(40)
        self.assertLessEqual(
            many,
            few + 5,
            f"a timesheet on a project of 44 shifts cost {many} statements "
            f"against {few} on one of 4; the search is running once per shift",
        )
