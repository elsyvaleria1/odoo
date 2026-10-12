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
            ]
        )

        cohort = self.env["x_stuff"].get_cohort_data(
            "x_date_start",
            "x_date_stop",
            "__count",
            "month",
            [],
            "retention",
            "forward",
        )

        first_row = cohort["rows"][0]
        value_per_month = [col["value"] for col in first_row["columns"]]
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
        second_row = cohort["rows"][1]
        value_per_month = [col["value"] for col in second_row["columns"]]
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
    def test_the_cohort_schema_is_declared(self):
        self.assertEqual(
            view_validation.registered_schemas().get("cohort"),
            "web_cohort/rng/cohort_view.rng",
        )

    def test_the_declared_cohort_schema_loads(self):
        self.assertIsNotNone(view_validation.relaxng("cohort"))

    def test_the_schema_is_the_only_thing_refusing_an_unknown_attribute(self):
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

        declared = view_validation.registered_schemas()["cohort"]
        self.addCleanup(view_validation.register_schema, "cohort", declared)
        view_validation.register_schema("cohort", None)
        self.assertValid(rejected)
