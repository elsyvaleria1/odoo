from copy import deepcopy
from unittest.mock import patch

from odoo.addons.account.models.account_sales_report import AccountEcSalesReportHandler
from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


class EcSalesByPartnerTestCommon(TestAccountReportsCommon):
    allow_inherited_tests_method = True

    def test_partner_rows_and_column_group_totals(self):
        report = self.env.ref(self.report_xmlid)
        handler = self.env[report.custom_handler_model_id.model]
        options = {
            "column_groups": {
                "current": {"forced_options": {}},
                "previous": {"forced_options": {}},
            },
            "columns": [
                {
                    "column_group_key": group,
                    "expression_label": label,
                    "figure_type": "string"
                    if label in ("country_code", "vat_number")
                    else "monetary",
                }
                for group in ("current", "previous")
                for label in (
                    "country_code",
                    "vat_number",
                    "goods",
                    "services",
                    "triangular",
                    "balance",
                )
            ],
        }
        rows = [
            (
                self.partner_a,
                {
                    "current": {
                        "country_code": "FR",
                        "vat_number": "FR123",
                        "goods": 10,
                        "services": 20,
                        "triangular": -5,
                    },
                    "previous": {
                        "country_code": None,
                        "vat_number": None,
                        "goods": None,
                        "services": 3,
                    },
                },
            ),
            (
                self.partner_b,
                {"current": {"goods": -2, "services": 0, "triangular": 4}},
            ),
        ]
        before = [(partner, deepcopy(values)) for partner, values in rows]
        with patch.object(
            AccountEcSalesReportHandler, "_query_partners", return_value=rows
        ) as query:
            lines = handler._dynamic_lines_generator(report, options, {}, warnings={})
        query.assert_called_once_with(report, options)
        self.assertEqual(rows, before)
        self.assertEqual([priority for priority, line in lines], [0, 0, 0])
        self.assertEqual(
            [line["name"] for priority, line in lines[:-1]],
            [self.partner_a.name, self.partner_b.name],
        )
        self.assertEqual(
            [
                [column["no_format"] for column in line["columns"]]
                for priority, line in lines
            ],
            [
                ["FR", "FR123", 10, 20, -5, 25, "UNKNOWN", "", 0, 3, 0, 3],
                ["UNKNOWN", "", -2, 0, 4, 2, "UNKNOWN", "", 0, 0, 0, 0],
                ["", "", 8, 20, -1, 27, "", "", 0, 3, 0, 3],
            ],
        )
        self.assertEqual(lines[-1][1]["class"], "total")

    def test_empty_result_keeps_total_row(self):
        report = self.env.ref(self.report_xmlid)
        handler = self.env[report.custom_handler_model_id.model]
        options = {
            "column_groups": {"current": {"forced_options": {}}},
            "columns": [
                {
                    "column_group_key": "current",
                    "expression_label": "balance",
                    "figure_type": "monetary",
                }
            ],
        }
        with patch.object(
            AccountEcSalesReportHandler, "_query_partners", return_value=[]
        ):
            lines = handler._dynamic_lines_generator(report, options, {})
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0][1]["class"], "total")
        self.assertEqual(lines[0][1]["columns"][0]["no_format"], 0)

    def test_empty_report_through_report_engine(self):
        report = self.env.ref(self.report_xmlid)
        options = self._generate_options(report, "2026-01-01", "2026-01-31")
        lines = report._get_lines(options)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["class"], "total")
        for column in lines[0]["columns"]:
            if column["figure_type"] == "monetary":
                self.assertEqual(column["no_format"], 0)
