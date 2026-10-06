from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, freeze_time, tagged

# NOTE: the many2one measure branch is deliberately left uncovered. get_cohort_data
# aggregates the baseline with ':sum' regardless of the field type, so a many2one
# measure is summed as database ids. Pinning that would freeze a defect as a
# contract; task t24339 tracks the fix. Add the coverage once it lands.

FROZEN_TODAY = "2026-06-15"


@tagged("post_install", "-at_install")
class TestCohortData(TransactionCase):
    """Cover the cohort aggregation modes, timelines and intervals."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.model"].create(
            {
                "name": "Cohort Stuff",
                "model": "x_cohort_stuff",
                "field_id": [
                    Command.create(
                        {
                            "name": "x_date_start",
                            "ttype": "date",
                            "field_description": "Start Date",
                        }
                    ),
                    Command.create(
                        {
                            "name": "x_date_stop",
                            "ttype": "date",
                            "field_description": "End Date",
                        }
                    ),
                    Command.create(
                        {
                            "name": "x_amount",
                            "ttype": "float",
                            "field_description": "Amount",
                        }
                    ),
                    Command.create(
                        {
                            "name": "x_flag",
                            "ttype": "boolean",
                            "field_description": "Flag",
                        }
                    ),
                ],
            }
        )
        # Three records entering the cohort in March 2026; one of them leaves in May.
        cls.env["x_cohort_stuff"].create(
            [
                {"x_date_start": "2026-03-10", "x_amount": 10.0},
                {
                    "x_date_start": "2026-03-10",
                    "x_date_stop": "2026-05-10",
                    "x_amount": 20.0,
                },
                {"x_date_start": "2026-03-10", "x_amount": 30.0},
            ]
        )

    def _cohort(self, **overrides):
        params = {
            "date_start": "x_date_start",
            "date_stop": "x_date_stop",
            "measure": "__count",
            "interval": "month",
            "domain": [],
            "mode": "retention",
            "timeline": "forward",
        }
        params.update(overrides)
        return self.env["x_cohort_stuff"].get_cohort_data(**params)

    @freeze_time(FROZEN_TODAY)
    def test_retention_counts_the_records_still_in(self):
        """Retention drops only when a record reaches its stop date."""
        row = self._cohort()["rows"][0]

        self.assertEqual(row["date"], "March 2026")
        self.assertEqual(row["value"], 3)
        self.assertEqual(
            [column["value"] for column in row["columns"]],
            [3.0, 3.0, 2.0, 2.0] + ["-"] * 12,
        )
        self.assertEqual(
            [column["percentage"] for column in row["columns"]],
            [100.0, 100.0, 66.7, 66.7] + [""] * 12,
        )

    @freeze_time(FROZEN_TODAY)
    def test_churn_is_the_complement_of_retention(self):
        """Churn reports the share that left, so it mirrors retention."""
        row = self._cohort(mode="churn")["rows"][0]

        self.assertEqual(
            [column["percentage"] for column in row["columns"]],
            [0.0, 0.0, 33.3, 33.3] + [""] * 12,
        )

    @freeze_time(FROZEN_TODAY)
    def test_churn_value_accumulates_the_departures(self):
        """The churn counter is cumulative across the periods."""
        row = self._cohort()["rows"][0]

        self.assertEqual(
            [column["churn_value"] for column in row["columns"]],
            [0.0, 0.0, 1.0, 1.0] + ["-"] * 12,
        )

    @freeze_time(FROZEN_TODAY)
    def test_future_columns_are_placeholders(self):
        """Periods after today hold no data, so they are not counted."""
        row = self._cohort()["rows"][0]

        future_columns = row["columns"][4:]
        self.assertEqual([column["value"] for column in future_columns], ["-"] * 12)
        self.assertEqual([column["percentage"] for column in future_columns], [""] * 12)
        for column in future_columns:
            self.assertNotIn("period", column)

    @freeze_time(FROZEN_TODAY)
    def test_backward_timeline_looks_back_from_the_cohort(self):
        """A backward cohort rebases on the records alive at window start."""
        # A record gone BEFORE the window starts: the row must count it while
        # the rebased initial value (and every percentage) must exclude it.
        self.env["x_cohort_stuff"].create(
            {"x_date_start": "2026-03-10", "x_date_stop": "2024-06-01"}
        )
        row = self._cohort(timeline="backward")["rows"][0]

        self.assertEqual(len(row["columns"]), 16)
        self.assertEqual(row["columns"][0]["period"], "December 2024")
        self.assertEqual(row["columns"][-1]["period"], "March 2026")
        self.assertEqual(row["value"], 4)
        self.assertEqual(
            [column["value"] for column in row["columns"]],
            [3.0] * 16,
        )
        self.assertEqual(
            [column["percentage"] for column in row["columns"]],
            [75.0] * 16,
        )

    @freeze_time(FROZEN_TODAY)
    def test_numeric_measure_aggregates_the_field(self):
        """A numeric measure sums the field instead of counting records."""
        result = self._cohort(measure="x_amount")
        row = result["rows"][0]

        self.assertEqual(row["value"], 60.0)
        self.assertEqual(
            [column["value"] for column in row["columns"]],
            [60.0, 60.0, 40.0, 40.0] + ["-"] * 12,
        )
        self.assertEqual(result["avg"]["avg_value"], 60.0)

    @freeze_time(FROZEN_TODAY)
    def test_week_interval_labels_columns_with_a_range(self):
        """Weekly columns carry a readable range instead of a single date."""
        row = self._cohort(interval="week")["rows"][0]

        self.assertRegex(row["columns"][0]["period"], r"^\d{2} \w{3} - \d{2} \w{3}$")

    @freeze_time(FROZEN_TODAY)
    def test_day_interval_labels_columns_with_the_day(self):
        """Daily columns carry a full day label."""
        row = self._cohort(interval="day")["rows"][0]

        self.assertRegex(row["columns"][0]["period"], r"^\d{2} \w{3} \d{4}$")

    @freeze_time(FROZEN_TODAY)
    def test_quarter_interval_labels_columns_with_the_quarter(self):
        """Quarterly columns carry the quarter number and the year."""
        row = self._cohort(interval="quarter")["rows"][0]

        self.assertEqual(row["columns"][0]["period"], "Q1 2026")

    @freeze_time(FROZEN_TODAY)
    def test_retention_domain_targets_the_remaining_records(self):
        """Each cell carries the domain that reproduces its own value."""
        row = self._cohort()["rows"][0]

        self.assertEqual(
            row["columns"][0]["domain"],
            ["|", ("x_date_stop", ">=", "2026-04-01"), ("x_date_stop", "=", False)],
        )

    @freeze_time(FROZEN_TODAY)
    def test_churn_domain_targets_the_departed_records(self):
        """In churn mode the cell domain selects what already left."""
        row = self._cohort(mode="churn")["rows"][0]

        self.assertEqual(
            row["columns"][0]["domain"], [("x_date_stop", "<", "2026-04-01")]
        )

    @freeze_time(FROZEN_TODAY)
    def test_a_domain_matching_nothing_yields_no_rows(self):
        """An empty cohort averages zero instead of dividing by zero."""
        result = self._cohort(domain=[("x_amount", "=", -1)])

        self.assertEqual(result["rows"], [])
        self.assertEqual(result["avg"]["avg_value"], 0)

    def test_nonexistent_measure_field_raises(self):
        """A measure naming a field absent from the model is rejected up front."""
        with self.assertRaises(UserError):
            self._cohort(measure="does_not_exist")

    def test_non_aggregatable_measure_raises(self):
        """A measure whose aggregator is not 'sum' is rejected up front."""
        with self.assertRaises(UserError):
            self._cohort(measure="x_flag")
