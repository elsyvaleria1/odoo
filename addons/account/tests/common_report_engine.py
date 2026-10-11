import copy
import io
import unittest
from collections import Counter
from datetime import date, datetime

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo.tools.misc import file_open, formatLang

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class TestAccountReportsCommon(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_currency = cls.setup_other_currency("CAD")
        cls.company_data_2 = cls.setup_other_company()
        cls.company_data_2["company"].currency_id = cls.other_currency
        cls.company_data_2["currency"] = cls.other_currency

    @classmethod
    def _generate_options(cls, report, date_from, date_to, default_options=None):
        if isinstance(date_from, datetime):
            date_from_str = fields.Date.to_string(date_from)
        else:
            date_from_str = date_from

        if isinstance(date_to, datetime):
            date_to_str = fields.Date.to_string(date_to)
        else:
            date_to_str = date_to

        if not default_options:
            default_options = {}

        return report.get_options(
            {
                "selected_variant_id": report.id,
                "date": {
                    "date_from": date_from_str,
                    "date_to": date_to_str,
                    "mode": "range",
                    "filter": "custom",
                },
                "show_account": True,
                "show_currency": True,
                **default_options,
            }
        )

    def _update_comparison_filter(
        self,
        options,
        report,
        comparison_type,
        number_period,
        date_from=None,
        date_to=None,
        period_order=None,
    ):
        previous_options = {
            **options,
            "comparison": {
                **options["comparison"],
                "date_from": date_from
                and date_from.strftime(DEFAULT_SERVER_DATE_FORMAT),
                "date_to": date_to and date_to.strftime(DEFAULT_SERVER_DATE_FORMAT),
                "filter": comparison_type,
                "number_period": number_period,
                "period_order": period_order or options["comparison"]["period_order"],
            },
        }
        return report.get_options(previous_options)

    def _update_multi_selector_filter(self, options, option_key, selected_ids):
        new_options = copy.deepcopy(options)
        for c in new_options[option_key]:
            c["selected"] = c["id"] in selected_ids
        return new_options

    def assertColumnPercentComparisonValues(self, lines, expected_values):
        filtered_lines = self._filter_folded_lines(lines)

        self.assertEqual(len(filtered_lines), len(expected_values))

        for value, expected_value in zip(filtered_lines, expected_values, strict=False):
            key = "column_percent_comparison_data"
            self.assertEqual(len(value[key]) + 1, len(expected_value))
            self.assertEqual(
                (value["name"], value[key]["name"], value[key]["mode"]), expected_value
            )

    def assertHorizontalGroupTotal(self, lines, expected_values):
        filtered_lines = self._filter_folded_lines(lines)

        self.assertEqual(len(filtered_lines), len(expected_values))
        for line_dict_list, (_title, *expected_columns) in zip(
            filtered_lines, expected_values, strict=False
        ):
            column_values = [
                column["no_format"] for column in line_dict_list["columns"]
            ]
            if line_dict_list.get("horizontal_group_total_data"):
                *expected_columns, total = expected_columns
                self.assertEqual(
                    line_dict_list["horizontal_group_total_data"]["no_format"], total
                )

            self.assertEqual(column_values, expected_columns)

    def assertHeadersValues(self, headers, expected_headers):
        self.assertEqual(len(headers), len(expected_headers))

        for header, expected_header in zip(headers, expected_headers, strict=False):
            self.assertEqual(len(header), len(expected_header))

            for i, column in enumerate(header):
                self.assertEqual(
                    column["name"],
                    self._convert_str_to_date(column["name"], expected_header[i]),
                )

    def assertIdenticalLines(self, reports):

        def expression_to_comparable_values(expr):
            return (
                expr.label,
                expr.engine,
                expr.formula,
                expr.subformula,
                expr.date_scope,
            )

        if not reports:
            raise UserError(self.env._("There are no reports to compare."))
        visited_line_codes = set()
        lines_by_code = reports.line_ids.grouped("code")
        for line in reports.line_ids:
            if not line.code or line.code in visited_line_codes:
                continue
            identical_lines = lines_by_code[line.code] - line
            if not identical_lines:
                continue
            with self.subTest(line_code=line.code):
                for tested_line in identical_lines:
                    self.assertCountEqual(
                        line.expression_ids.mapped(expression_to_comparable_values),
                        tested_line.expression_ids.mapped(
                            expression_to_comparable_values
                        ),
                        (
                            f'The line with code {line.code} from reports "{line.report_id.name}" and '
                            f'"{tested_line.report_id.name}" has different expression values in both reports.'
                        ),
                    )
            visited_line_codes.add(line.code)

    def assertLinesValues(
        self,
        lines,
        columns,
        expected_values,
        options,
        currency_map=None,
        ignore_folded=True,
    ):
        if currency_map is None:
            currency_map = {}

        filtered_lines = self._filter_folded_lines(lines) if ignore_folded else lines

        self.assertEqual(len(filtered_lines), len(expected_values))

        to_compare_list = []
        for i, line in enumerate(filtered_lines):
            compared_values = [[], []]
            for j, index in enumerate(columns):
                if index == 0:
                    current_value = line["name"]
                else:
                    if j > len(expected_values[i]) - 1:
                        break
                    current_value = line["columns"][index - 1].get("name", "")
                    current_figure_type = line["columns"][index - 1].get(
                        "figure_type", ""
                    )

                expected_value = expected_values[i][j]
                currency_data = currency_map.get(index, {})
                used_currency = None
                if "currency" in currency_data:
                    used_currency = currency_data["currency"]
                elif "currency_code_index" in currency_data:
                    currency_code = line["columns"][
                        currency_data["currency_code_index"] - 1
                    ].get("name", "")
                    if currency_code:
                        used_currency = self.env["res.currency"].search(
                            [("name", "=", currency_code)], limit=1
                        )
                        assert used_currency, (
                            "Currency having name=%s not found." % currency_code
                        )
                if not used_currency:
                    used_currency = self.env.company.currency_id

                if type(expected_value) in (int, float) and type(current_value) is str:
                    if current_figure_type and current_figure_type != "monetary":
                        expected_value = str(expected_value)
                    elif options.get("multi_currency"):
                        expected_value = formatLang(
                            self.env, expected_value, currency_obj=used_currency
                        )
                    else:
                        expected_value = formatLang(
                            self.env,
                            expected_value,
                            digits=used_currency.decimal_places,
                        )

                compared_values[0].append(current_value)
                compared_values[1].append(expected_value)

            to_compare_list.append(compared_values)

        errors = []
        for i, to_compare in enumerate(to_compare_list):
            if to_compare[0] != to_compare[1]:
                errors += [
                    "\n==== Differences at index %s ====" % str(i),
                    "Current Values:  %s" % str(to_compare[0]),
                    "Expected Values: %s" % str(to_compare[1]),
                ]

        id_counts = Counter(line["id"] for line in lines)
        duplicate_ids = {k: v for k, v in id_counts.items() if v > 1}
        if duplicate_ids:
            index_to_id = [
                f"index={index:<6} name={line.get('name', 'no line name?!')} \tline_id={line.get('id', 'no line id?!')}"
                for index, line in enumerate(lines)
                if line.get("id", "no line id?!") in duplicate_ids
            ]
            errors += [
                "\n==== There are lines sharing the same id ====",
                "\n".join(index_to_id),
            ]

        if errors:
            self.fail("\n".join(errors))

    def _filter_folded_lines(self, lines):
        filtered_lines = []
        folded_lines = set()
        for line in lines:
            if line.get("parent_id") in folded_lines:
                folded_lines.add(line["id"])
            else:
                if line.get("unfoldable") and not line.get("unfolded"):
                    folded_lines.add(line["id"])
                filtered_lines.append(line)
        return filtered_lines

    def _convert_str_to_date(self, ref, val):
        if isinstance(ref, date) and isinstance(val, str):
            return datetime.strptime(val, "%Y-%m-%d").date()
        return val

    @classmethod
    def _create_tax_report_line(
        cls,
        name,
        report,
        tag_name=None,
        parent_line=None,
        sequence=None,
        code=None,
        formula=None,
    ):
        create_vals = {
            "name": name,
            "code": code,
            "report_id": report.id,
            "sequence": sequence,
            "expression_ids": [],
        }
        if tag_name and formula:
            raise UserError(
                cls.env._(
                    "Can't use this helper to create a line with both tags and formula"
                )
            )
        if tag_name:
            create_vals["expression_ids"].append(
                Command.create(
                    {
                        "label": "balance",
                        "engine": "tax_tags",
                        "formula": tag_name,
                    }
                )
            )
        if parent_line:
            create_vals["parent_id"] = parent_line.id
        if formula:
            create_vals["expression_ids"].append(
                Command.create(
                    {
                        "label": "balance",
                        "engine": "aggregation",
                        "formula": formula,
                    }
                )
            )

        return cls.env["report.formula.line"].create(create_vals)

    @classmethod
    def _get_tag_ids(cls, expressions, company=False):
        return [
            (
                6,
                0,
                cls.env["account.account.tag"]
                .search(
                    [
                        ("applicability", "=", "taxes"),
                        (
                            "country_id.code",
                            "=",
                            (
                                company or cls.env.company
                            ).tax_config_id.account_fiscal_country_id.code,
                        ),
                        (
                            "name",
                            "in",
                            [
                                formula.lstrip("-")
                                for formula in expressions.mapped("formula")
                            ],
                        ),
                    ]
                )
                .ids,
            )
        ]

    @classmethod
    def _get_basic_line_dict_id_from_report_line(cls, report_line):
        report = report_line.report_id
        if report_line.parent_id:
            parent_line_id = cls._get_basic_line_dict_id_from_report_line(
                report_line.parent_id
            )
            return report._get_generic_line_id(
                report_line._name, report_line.id, parent_line_id=parent_line_id
            )

        return report._get_generic_line_id(report_line._name, report_line.id)

    @classmethod
    def _get_basic_line_dict_id_from_report_line_ref(cls, report_line_xmlid):
        return cls._get_basic_line_dict_id_from_report_line(
            cls.env.ref(report_line_xmlid)
        )

    @classmethod
    def _get_audit_params_from_report_line(
        cls, options, report_line, report_line_dict, **kwargs
    ):
        return {
            "report_line_id": report_line.id,
            "calling_line_dict_id": report_line_dict["id"],
            "expression_label": "balance",
            "column_group_key": next(iter(options["column_groups"])),
            **kwargs,
        }

    def _report_compare_with_test_file(self, report, xml_file=None, test_xml=None):
        report_xml = self.get_xml_tree_from_string(report["file_content"])
        if xml_file and not test_xml:
            with file_open(
                f"{self.test_module}/tests/expected_xmls/{xml_file}", "rb"
            ) as fp:
                test_xml = fp.read()
        test_xml_tree = self.get_xml_tree_from_string(test_xml)
        self.assertXmlTreeEqual(report_xml, test_xml_tree)

    @classmethod
    def _fill_tax_report_line_external_value(cls, target, amount, date):
        cls.env["report.formula.external.value"].create(
            {
                "company_id": cls.company_data["company"].id,
                "target_report_expression_id": cls.env.ref(target).id,
                "name": "Manual value",
                "date": fields.Date.from_string(date),
                "value": amount,
            }
        )

    def _test_xlsx_file(self, file_content, expected_values):
        if load_workbook is None:
            raise unittest.SkipTest("openpyxl not available")

        report_file = io.BytesIO(file_content)
        xlsx = load_workbook(filename=report_file, data_only=True)
        sheet = xlsx.worksheets[0]
        sheet_values = list(sheet.values)

        for row, values in expected_values.items():
            row_values = [v if v is not None else "" for v in sheet_values[row]]
            for row_value, expected_value in zip(row_values, values, strict=False):
                self.assertEqual(row_value, expected_value)
