from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests.common import freeze_time
from odoo.tools import mute_logger, view_validation

from odoo.addons.base.tests.test_views import ViewCase


class TestViews(ViewCase):
    def test_get_views_model_fields(self):
        model = self.env.ref("base.model_ir_ui_view")
        self.env["ir.model.fields"].create(
            [
                {"model_id": model.id, "name": "x_date_start", "ttype": "datetime"},
                {"model_id": model.id, "name": "x_date_stop", "ttype": "datetime"},
            ]
        )

        view = self.assertValid(
            """
                <cohort string="foo" date_start="x_date_start" date_stop="x_date_stop" interval="week" mode="churn" sample="1">
                    <field name="priority"/>
                </cohort>
            """
        )

        views = self.View.get_views([(view.id, "cohort")])
        self.assertTrue("x_date_start" in views["models"]["ir.ui.view"]["fields"])

    def test_cohort_data(self):
        # create a model with 2 dates field
        self.env["ir.model"].create(
            {
                "name": "Stuff",
                "model": "x_stuff",
                "field_id": [
                    Command.create(
                        {"name": "x_name", "ttype": "char", "field_description": "Name"}
                    ),
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
                ],
            }
        )
        # create 2 stuffs: one from 6 months ago without an end date,
        # and one from 4 months ago with an end date 1 month ago
        self.env["x_stuff"].create(
            [
                {
                    "x_name": "Stuff 1",
                    "x_date_start": fields.Date.today() - relativedelta(months=6),
                },
                {
                    "x_name": "Stuff 2",
                    "x_date_start": fields.Date.today() - relativedelta(months=4),
                    "x_date_stop": fields.Date.today() - relativedelta(months=1),
                },
            ]
        )

        # check that the cohort method returns the correct data
        cohort = self.env["x_stuff"].get_cohort_data(
            "x_date_start",
            "x_date_stop",
            "__count",
            "month",
            [],
            "retention",
            "forward",
        )

        # first row should be 6 mmonths ago, with 1 stuff counted until *now*
        first_row = cohort["rows"][0]
        value_per_month = [col["value"] for col in first_row["columns"]]
        # we should have 7 periods with value 1 (6 prev periods + current period),
        # then the rest with no value (9 periods) (16 periods in total)
        self.assertEqual(value_per_month, [1] * 7 + ["-"] * 9)
        expected_period_domain = [
            "&",
            "&",
            ("x_date_start", "!=", False),
            (
                "x_date_start",
                ">=",
                (fields.Date.today() - relativedelta(months=6)).replace(day=1),
            ),
            (
                "x_date_start",
                "<",
                (fields.Date.today() - relativedelta(months=5)).replace(day=1),
            ),
        ]
        self.assertEqual(list(first_row["domain"]), expected_period_domain)
        # check for the second row
        second_row = cohort["rows"][1]
        value_per_month = [col["value"] for col in second_row["columns"]]
        # we should have 3 periods with value 1, then 2 with value 0 (closing period + current period),
        # then the rest with no value (11 periods) (16 periods in total)
        self.assertEqual(value_per_month, [1.0] * 3 + [0] * 2 + ["-"] * 11)
        expected_period_domain = [
            "&",
            "&",
            ("x_date_start", "!=", False),
            (
                "x_date_start",
                ">=",
                (fields.Date.today() - relativedelta(months=4)).replace(day=1),
            ),
            (
                "x_date_start",
                "<",
                (fields.Date.today() - relativedelta(months=3)).replace(day=1),
            ),
        ]
        self.assertEqual(list(second_row["domain"]), expected_period_domain)

    @freeze_time("2024-12-20")
    def test_cohort_quarter(self):
        self.env["ir.model"].create(
            {
                "name": "Stuff",
                "model": "x_stuff",
                "field_id": [
                    Command.create(
                        {"name": "x_name", "ttype": "char", "field_description": "Name"}
                    ),
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
                ],
            }
        )

        self.env["x_stuff"].create(
            [
                {
                    "x_name": "Stuff 1",
                    "x_date_start": fields.Date.today() - relativedelta(months=6),
                },
                {
                    "x_name": "Stuff 2",
                    "x_date_start": fields.Date.today() - relativedelta(months=4),
                    "x_date_stop": fields.Date.today() - relativedelta(months=1),
                },
                {
                    "x_name": "Stuff 3",
                    "x_date_start": fields.Date.today() - relativedelta(months=2),
                },
            ]
        )

        cohort = self.env["x_stuff"].get_cohort_data(
            "x_date_start",
            "x_date_stop",
            "__count",
            "quarter",
            [],
            "retention",
            "forward",
        )

        self.assertEqual(
            [d["date"] for d in cohort["rows"]], ["Q2 2024", "Q3 2024", "Q4 2024"]
        )

        expected_values = [
            [1.0] * 3 + ["-"] * 13,
            [1.0] + [0] + ["-"] * 14,
            [1.0] + ["-"] * 15,
        ]
        for row, value in zip(cohort["rows"], expected_values, strict=True):
            value_per_quarter = [col["value"] for col in row["columns"]]
            self.assertEqual(value_per_quarter, value)


class TestCohortSchemaDeclaration(ViewCase):
    """The cohort view type declares its RelaxNG schema to `view_validation`.

    `web_cohort/validation.py` used to hand-roll the load/cache/log block that
    `relaxng()` could not be asked for, because it resolved `base/rng/` and
    nothing else. The block is gone; what replaces it is one `register_schema`
    call, and a declaration can go missing in a way a copied function could not.
    So these pin the declaration itself, not only its effect.
    """

    def test_the_cohort_schema_is_declared(self):
        self.assertEqual(
            view_validation.registered_schemas().get("cohort"),
            "web_cohort/rng/cohort_view.rng",
        )

    def test_the_declared_cohort_schema_loads(self):
        # A declared schema that will not load is refused rather than skipped,
        # so a wrong path fails every cohort view instead of silently switching
        # validation off. Asserting it compiles is what keeps that loud failure
        # from being how anyone finds out.
        self.assertIsNotNone(view_validation.relaxng("cohort"))

    def test_the_schema_is_the_only_thing_refusing_an_unknown_attribute(self):
        # A positive control first: the same arch without the attribute stores.
        # Without it this test would pass with the schema check disconnected,
        # since some other predicate might be doing the refusing.
        self.env["ir.model.fields"].create(
            [
                {
                    "model_id": self.env.ref("base.model_ir_ui_view").id,
                    "name": f"x_{name}",
                    "ttype": "datetime",
                }
                for name in ("cohort_start", "cohort_stop")
            ]
        )
        valid = (
            '<cohort string="foo" date_start="x_cohort_start" date_stop="x_cohort_stop"'
        )
        self.assertValid(f"{valid}/>")
        # Not assertInvalid: it asserts on `exception.context["name"]`, which
        # only `_prepare_view_error` sets. A schema refusal comes out of
        # `_check_xml` as a plain ValidationError, so that helper errors rather
        # than failing and would hide whichever of the two actually happened.
        rejected = f'{valid} not_a_cohort_attribute="1"/>'
        with (
            mute_logger(
                "odoo.addons.base.models.ir_ui_view",
                "odoo.tools.view_validation",
            ),
            self.assertRaises(ValidationError),
        ):
            self.View.create(
                {
                    "name": "unknown cohort attribute",
                    "model": "ir.ui.view",
                    "arch": rejected,
                }
            )

        # And the schema is what refused it. Without this the test would only
        # show that SOMETHING dislikes the attribute -- `_check_attributes` runs
        # over every arch and could have been the one -- which is a weaker
        # statement than the name of this test makes.
        declared = view_validation.registered_schemas()["cohort"]
        self.addCleanup(view_validation.register_schema, "cohort", declared)
        view_validation.register_schema("cohort", None)
        self.assertValid(rejected)
