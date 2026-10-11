import datetime
import io
from itertools import chain

from odoo import models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.libs.documents import SheetBuilder
from odoo.tools import SQL

from odoo.addons.account.tools.display_types import NON_ACCOUNTABLE_DISPLAY_TYPES
from odoo.addons.report_formula.models.account_report_export import (
    PDF_PAPERFORMAT_ARGS,
)

_debug = DebugLog(__name__)

XLSX_GRAY_200 = "#EEEEEE"
XLSX_BORDER_COLOR = "#B4B4B4"
XLSX_FONT_SIZE_DEFAULT = 8
XLSX_FONT_SIZE_HEADING = 11


class AccountJournalReportHandler(models.AbstractModel):
    _name = "account.journal.report.handler"
    _inherit = ["report.formula.custom.handler"]
    _description = "Journal Report Custom Handler"

    def _customize_warnings(
        self, report, options, all_column_groups_expression_totals, warnings
    ):
        if "account.common_warning_draft_in_period" in warnings:
            warnings.pop("account.common_warning_draft_in_period")

    def _custom_options_initializer(self, report, options, previous_options):

        options["ignore_totals_below_sections"] = True
        options["show_payment_lines"] = previous_options.get("show_payment_lines", True)
        options["custom_display_config"] = {
            "css_custom_class": "journal_report",
            "pdf_css_custom_class": "journal_report_pdf",
            "components": {
                "AccountReportLine": "JournalReportLine",
                "AccountReportFilters": "JournalReportFilters",
            },
            "templates": {
                "AccountReportLineName": "account.JournalReportLineName",
            },
            "pdf_export": {
                "pdf_export_main": "account.journal_report_pdf_export_main",
            },
        }


    @_debug.perf.timed
    def _report_custom_engine_journal_report(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ) -> dict | list:

        def prepare_result_dict(current_groupby, query_line):
            if current_groupby == "account_id":
                code = query_line["account_code"][0]
            elif current_groupby == "journal_id":
                code = query_line["journal_code"][0]
            else:
                code = None

            result_line_dict = {
                "count": query_line["count"]
                if current_groupby == "journal_id"
                else None,
                "to_review": query_line["to_review"]
                if current_groupby == "journal_id"
                else None,
                "code": code,
                "credit": query_line["credit"],
                "debit": query_line["debit"],
                "balance": query_line["balance"]
                if current_groupby == "account_id"
                else None,
                "has_sublines": True,
            }
            return query_line["grouping_key"], result_line_dict

        report = self.env["report.formula"].browse(options["report_id"])
        report._check_groupby_fields(
            (next_groupby.split(",") if next_groupby else [])
            + ([current_groupby] if current_groupby else [])
        )

        _debug.logic(
            "journal_engine_mode",
            report=report,
            groupby=current_groupby,
            next_groupby=next_groupby,
            header_only=not current_groupby,
            show_payment_lines=options.get("show_payment_lines"),
        )
        if not current_groupby:
            return {
                "count": None,
                "to_review": None,
                "code": None,
                "debit": None,
                "credit": None,
                "balance": None,
            }

        query = report._get_report_query(options, "strict_range")
        account_alias = query.join(
            lhs_alias="account_move_line",
            lhs_column="account_id",
            rhs_table="account_account",
            rhs_column="id",
            link="account_id_for_code",
        )
        account_code = self.env["account.account"]._field_to_sql(
            account_alias, "code", query
        )

        groupby_clause = self.env["account.move.line"]._field_to_sql(
            "account_move_line", current_groupby, query
        )
        select_from_groupby = SQL("%s AS grouping_key", groupby_clause)

        query = SQL(
            """
                SELECT
                    %(select_from_groupby)s,
                    COUNT(DISTINCT move_id) AS count,
                    COUNT(DISTINCT move_id) FILTER (WHERE am.state = 'draft' OR NOT am.checked) AS to_review,
                    ARRAY_AGG(DISTINCT %(account_code)s) AS account_code,
                    ARRAY_AGG(DISTINCT j.code) AS journal_code,
                    SUM(%(debit)s) AS debit,
                    SUM(%(credit)s) AS credit,
                    SUM(%(balance)s) AS balance
                FROM %(table)s
                %(currency_table_join)s
                JOIN account_move am ON am.id = account_move_line.move_id
                JOIN account_journal j ON j.id = am.journal_id
                JOIN res_company cp ON cp.id = am.company_id
                WHERE %(case_statement)s AND %(search_conditions)s
                GROUP BY %(groupby_clause)s
                ORDER BY %(groupby_clause)s
                %(query_tail)s
            """,
            select_from_groupby=select_from_groupby,
            account_code=account_code,
            debit=report._currency_table_apply_rate(SQL('"account_move_line".debit')),
            credit=report._currency_table_apply_rate(SQL('"account_move_line".credit')),
            balance=report._currency_table_apply_rate(
                SQL('"account_move_line".balance')
            ),
            currency_table_join=report._currency_table_aml_join(options),
            table=query.from_clause,
            search_conditions=query.where_clause,
            case_statement=self._get_payment_lines_filter_case_statement(options),
            groupby_clause=groupby_clause,
            query_tail=report._get_engine_query_tail(offset, limit),
        )
        _debug.pipeline(
            "journal_engine_query",
            report=report,
            groupby=current_groupby,
            offset=offset,
            limit=limit,
        )
        self.env.cr.execute(query)
        return [
            prepare_result_dict(current_groupby, query_line)
            for query_line in self.env.cr.dictfetchall()
        ]

    @_debug.perf.timed
    def _custom_line_postprocessor(self, report, options, lines):
        new_lines = []

        _debug.logic(
            "journal_postprocess_skipped",
            report=report,
            skipped=not lines,
        )
        if not lines:
            return new_lines

        colname_to_idx = {
            col["expression_label"]: idx
            for idx, col in enumerate(options.get("columns", []))
        }
        to_review_index = colname_to_idx.get("to_review")
        section_end_journal_ids = {}
        for i, line in enumerate(lines):
            line_id = line["id"]

            line_model, res_id = report._get_model_info_from_id(line_id)
            if to_review_index is not None:
                line["to_review"] = line["columns"][to_review_index].get("no_format")
            if line_model == "account.journal":
                line["journal_id"] = res_id
            elif line_model == "account.account":
                res_ids_map = report._get_res_ids_from_line_id(
                    line_id, ["account.journal", "account.account"]
                )
                line["journal_id"] = res_ids_map["account.journal"]
                line["account_id"] = res_ids_map["account.account"]
                line["date"] = options["date"]

                if (
                    i + 1 == len(lines)
                    or report._get_model_info_from_id(lines[i + 1]["id"])[0]
                    != "account.account"
                ):
                    section_end_journal_ids[i] = line["journal_id"]

        render_global_summary = (
            report._get_model_info_from_id(lines[0]["id"])[0] == "report.formula.line"
        )
        journal_ids_with_tax = (
            self._get_journal_ids_with_tax(options)
            if section_end_journal_ids or render_global_summary
            else set()
        )
        tax_summary_journals = self.env["account.journal"].browse(
            sorted(set(section_end_journal_ids.values()) & journal_ids_with_tax)
        )
        tax_summaries = self._get_tax_summary_sections(
            options,
            tax_summary_journals,
            with_global=render_global_summary and bool(journal_ids_with_tax),
        )

        for i, line in enumerate(lines):
            new_lines.append(line)
            journal_id = section_end_journal_ids.get(i)
            if journal_id is not None and journal_id in tax_summaries:
                new_lines.append(
                    {
                        "id": report._get_generic_line_id(
                            False,
                            False,
                            parent_line_id=line["parent_id"],
                            markup="tax_report_section",
                        ),
                        "name": "",
                        "parent_id": line["parent_id"],
                        "journal_id": journal_id,
                        "is_tax_section_line": True,
                        "columns": [],
                        "colspan": len(options["columns"]) + 1,
                        "level": 4,
                        **tax_summaries[journal_id],
                    }
                )

        if None in tax_summaries:
            new_lines.append(
                {
                    "id": report._get_generic_line_id(
                        False, False, markup="tax_report_section_heading"
                    ),
                    "name": self.env._("Global Tax Summary"),
                    "level": 0,
                    "columns": [],
                    "unfoldable": False,
                    "colspan": len(options["columns"]) + 1,
                }
            )
            new_lines.append(
                {
                    "id": report._get_generic_line_id(
                        False, False, markup="tax_report_section"
                    ),
                    "name": "",
                    "is_tax_section_line": True,
                    "columns": [],
                    "colspan": len(options["columns"]) + 1,
                    "level": 4,
                    "class": "o_account_reports_ja_subtable",
                    **tax_summaries[None],
                }
            )

        if _debug.pipeline.enabled:
            _debug.pipeline(
                "journal_lines_postprocessed",
                report=report,
                lines=len(lines),
                new_lines=len(new_lines),
                tax_section_lines=sum(
                    1 for line in new_lines if line.get("is_tax_section_line")
                ),
                first_level=report._get_model_info_from_id(lines[0]["id"])[0]
                == "report.formula.line",
            )
        return new_lines

    def format_column_values_from_client(self, options, lines):
        report = self.env["report.formula"].browse(options["report_id"])
        for line_dict in lines:
            if line_dict.get("is_tax_section_line"):
                self._format_tax_summary_line(report, options, line_dict)

        return report.format_column_values_from_client(options, lines)

    @_debug.perf.timed
    def _format_tax_summary_line(self, report, options, line_dict) -> None:
        tax_report_lines = line_dict.get("tax_report_lines")
        if tax_report_lines:
            monetary_fields = [
                "base_amount",
                "tax_amount",
                "tax_non_deductible",
                "tax_deductible",
                "tax_due",
            ]
            for tax_line in chain.from_iterable(tax_report_lines.values()):
                for field in monetary_fields:
                    no_format_field = f"{field}_no_format"
                    no_format_value = tax_line.get(no_format_field)
                    if no_format_value is not None:
                        tax_line[field] = report.format_value(
                            options, no_format_value, figure_type="monetary"
                        )

        tax_grid_lines = line_dict.get("tax_grid_summary_lines")
        _debug.pipeline(
            "tax_summary_line_formatted",
            report=report,
            tax_countries=len(tax_report_lines or ()),
            grid_countries=len(tax_grid_lines or ()),
        )
        if tax_grid_lines:
            for country_grids in tax_grid_lines.values():
                for grid_line in country_grids.values():
                    debit = grid_line.get("+_no_format", 0)
                    credit = grid_line.get("-_no_format", 0)
                    balance = grid_line.get("balance_no_format", 0)
                    grid_line["+"] = report.format_value(
                        options, debit, figure_type="monetary"
                    )
                    grid_line["-"] = report.format_value(
                        options, credit, figure_type="monetary"
                    )
                    grid_line["balance"] = report.format_value(
                        options, balance, figure_type="monetary"
                    )
                    grid_line["impact"] = report.format_value(
                        options, balance, figure_type="monetary"
                    )

    def _get_print_options(self, options, report, export_type=None):
        print_options = report.get_options(
            previous_options={**options, "export_mode": "print"}
        )
        if export_type == "pdf":
            print_options["css_custom_class"] = options["custom_display_config"][
                "pdf_css_custom_class"
            ]
        return print_options


    def _get_pdf_export_html(
        self, options, lines=None, additional_context=None, template=None, report=None
    ):
        report = report or self.env["report.formula"].browse(options["report_id"])
        print_options = self._get_print_options(options, report, export_type="pdf")
        document_data = self._generate_document_data_for_export(
            report, print_options, "pdf"
        )
        render_values = {
            "report": report,
            "options": print_options,
            "document_data": document_data,
        }
        if additional_context:
            render_values.update(additional_context)
        template = (
            template
            or options["custom_display_config"]["pdf_export"]["pdf_export_main"]
        )
        return self.env["ir.qweb"]._render(template, render_values)

    @_debug.perf.timed
    def export_to_pdf(self, options) -> dict:
        report = self.env["report.formula"].browse(options["report_id"])
        base_url = report.get_base_url()
        rcontext = {
            "mode": "print",
            "base_url": base_url,
            "company": self.env.company,
        }
        footer = self.env["report.formula"]._get_layout_footer(rcontext)

        body = self._get_pdf_export_html(
            options, additional_context={"base_url": base_url}, report=report
        )
        print_options = self._get_print_options(options, report, export_type="pdf")
        action_report = self.env["ir.actions.report"]
        body_with_footer = (
            action_report._get_html_with_header_footer(body, footer=footer)
            if footer
            else body
        )
        pdf_file_stream = io.BytesIO(
            action_report._render_html_to_pdf(
                [body_with_footer],
                landscape=False,
                specific_paperformat_args=PDF_PAPERFORMAT_ARGS,
            )
        )

        pdf_result = pdf_file_stream.getvalue()
        pdf_file_stream.close()
        _debug.pipeline(
            "journal_pdf_rendered",
            report=report,
            footer=bool(footer),
            body_chars=len(body),
            pdf_bytes=len(pdf_result),
        )

        return {
            "file_name": report.get_default_report_filename(print_options, "pdf"),
            "file_content": pdf_result,
            "file_type": "pdf",
        }


    @_debug.perf.timed
    def _get_xlsx_sheets(self, options):
        report = self.env["report.formula"].browse(options["report_id"])
        print_options = self._get_print_options(options, report)
        document_data = self._generate_document_data_for_export(
            report, print_options, "xlsx"
        )
        _debug.pipeline(
            "xlsx_document_data_ready",
            report=report,
            journals=len(document_data["journals_vals"]),
            global_tax_summary=bool(document_data.get("global_tax_summary")),
        )

        sheets = []
        for journal_vals in document_data["journals_vals"]:
            cursor_y = 0

            sheet = SheetBuilder(journal_vals["name"])
            sheets.append(sheet)
            columns = journal_vals["columns"]
            _debug.pipeline(
                "xlsx_journal_sheet",
                report=report,
                journal=journal_vals.get("id"),
                columns=len(columns),
                lines=len(journal_vals["lines"]),
                tax_summary=bool(journal_vals.get("tax_summary")),
            )

            for cursor_x, column in enumerate(columns):
                align = "left"
                if "o_right_alignment" in column.get("class", ""):
                    align = "right"
                self._write_cell(
                    sheet,
                    cursor_x,
                    cursor_y,
                    column["name"],
                    1,
                    False,
                    XLSX_FONT_SIZE_HEADING,
                    True,
                    XLSX_GRAY_200,
                    align,
                    2,
                    2,
                )

            cursor_y += 1
            cursor_x = 0
            for line in journal_vals["lines"][:-1]:
                is_first_aml_line = False
                for column in columns:
                    border_top = 0 if not is_first_aml_line else 1
                    align = "left"

                    if line.get(column["label"], {}).get("data"):
                        data = line[column["label"]]["data"]
                        is_date = isinstance(data, datetime.date)
                        bold = False

                        if "o_right_alignment" in column.get("class", ""):
                            align = "right"

                        if (
                            line[column["label"]].get("class")
                            and "o_bold" in line[column["label"]]["class"]
                        ):
                            is_first_aml_line = True
                            border_top = 1
                            bold = True

                        self._write_cell(
                            sheet,
                            cursor_x,
                            cursor_y,
                            data,
                            1,
                            is_date,
                            XLSX_FONT_SIZE_DEFAULT,
                            bold,
                            "white",
                            align,
                            0,
                            border_top,
                            XLSX_BORDER_COLOR,
                        )

                    else:
                        self._write_cell(
                            sheet,
                            cursor_x,
                            cursor_y,
                            "",
                            1,
                            False,
                            XLSX_FONT_SIZE_DEFAULT,
                            False,
                            "white",
                            align,
                            0,
                            border_top,
                            XLSX_BORDER_COLOR,
                        )

                    cursor_x += 1
                cursor_x = 0
                cursor_y += 1

            total_line = journal_vals["lines"][-1]
            for column in columns:
                data = ""
                align = "left"

                if total_line.get(column["label"], {}).get("data"):
                    data = total_line[column["label"]]["data"]

                if "o_right_alignment" in column.get("class", ""):
                    align = "right"

                self._write_cell(
                    sheet,
                    cursor_x,
                    cursor_y,
                    data,
                    1,
                    False,
                    XLSX_FONT_SIZE_DEFAULT,
                    True,
                    XLSX_GRAY_200,
                    align,
                    2,
                    2,
                )
                cursor_x += 1

            cursor_x = 0

            sheet.default_row(20)
            sheet.row(0, 30)

            if journal_vals.get("tax_summary"):
                self._write_tax_summaries_to_sheet(
                    report,
                    sheet,
                    len(columns) + 1,
                    1,
                    journal_vals["tax_summary"],
                )

        if document_data.get("global_tax_summary"):
            sheet = SheetBuilder(self.env._("Global Tax Summary"))
            sheets.append(sheet)
            self._write_tax_summaries_to_sheet(
                report, sheet, 0, 0, document_data["global_tax_summary"]
            )
        return sheets

    def export_to_xlsx(self, options, response=None):
        report = self.env["report.formula"].browse(options["report_id"])
        print_options = self._get_print_options(options, report)
        sheets = [
            *self._get_xlsx_sheets(options),
            report._get_xlsx_options_sheet([print_options]),
        ]
        return {
            "file_name": report.get_default_report_filename(options, "xlsx"),
            "file_content": report._write_xlsx_sheets(sheets),
            "file_type": "xlsx",
        }

    @_debug.perf.timed
    def _write_cell(
        self,
        sheet,
        x,
        y,
        value,
        colspan,
        datetime,
        font_size,
        bold=False,
        bg_color="white",
        align="left",
        border_bottom=0,
        border_top=0,
        border_color="0x000000",
    ) -> None:
        style = {
            "font_name": "Arial",
            "font_size": font_size,
            "bold": bold,
            "bg_color": bg_color,
            "align": align,
            "bottom": border_bottom,
            "top": border_top,
            "border_color": border_color,
        }

        if colspan == 1:
            if datetime:
                sheet.cell(
                    y, x, value, {**style, "num_format": "yyyy-mm-dd"}, date=True
                )
            else:
                if isinstance(value, str):
                    value = value.replace("\n", " ")
                sheet.cell(y, x, value, style, measure=font_size)
        else:
            sheet.cell(y, x, value, style, colspan=colspan)

    @_debug.perf.timed
    def _write_tax_summaries_to_sheet(
        self, report, sheet, start_x, start_y, tax_summary
    ) -> None:
        cursor_x = start_x
        cursor_y = start_y

        columns = []
        taxes = tax_summary.get("tax_report_lines")
        _debug.logic(
            "xlsx_tax_summary_layout",
            report=report,
            tax_countries=len(taxes or ()),
            grid_countries=len(tax_summary.get("tax_grid_summary_lines") or ()),
            non_deductible_column=bool(tax_summary.get("tax_non_deductible_column")),
            deductible_column=bool(tax_summary.get("tax_deductible_column")),
            due_column=bool(tax_summary.get("tax_due_column")),
        )
        if taxes:
            start_align_right = start_x + 1

            if len(taxes) > 1:
                start_align_right += 1
                columns.append(self.env._("Country"))

            columns += [
                self.env._("Name"),
                self.env._("Base Amount"),
                self.env._("Tax Amount"),
            ]
            if tax_summary.get("tax_non_deductible_column"):
                columns.append(self.env._("Non-Deductible"))
            if tax_summary.get("tax_deductible_column"):
                columns.append(self.env._("Deductible"))
            if tax_summary.get("tax_due_column"):
                columns.append(self.env._("Due"))

            self._write_cell(
                sheet,
                cursor_x,
                cursor_y,
                self.env._("Taxes Applied"),
                len(columns),
                False,
                XLSX_FONT_SIZE_HEADING,
                True,
                "white",
                "left",
                2,
            )
            cursor_y += 1
            for column in columns:
                align = "left"
                if cursor_x >= start_align_right:
                    align = "right"
                self._write_cell(
                    sheet,
                    cursor_x,
                    cursor_y,
                    column,
                    1,
                    False,
                    XLSX_FONT_SIZE_DEFAULT,
                    True,
                    XLSX_GRAY_200,
                    align,
                    2,
                )
                cursor_x += 1

            cursor_x = start_x
            cursor_y += 1

            for country in taxes:
                is_country_first_line = True
                for tax in taxes[country]:
                    if len(taxes) > 1:
                        if is_country_first_line:
                            is_country_first_line = not is_country_first_line
                            self._write_cell(
                                sheet,
                                cursor_x,
                                cursor_y,
                                country,
                                1,
                                False,
                                XLSX_FONT_SIZE_DEFAULT,
                                True,
                                "white",
                                "left",
                                1,
                                0,
                                XLSX_BORDER_COLOR,
                            )

                        cursor_x += 1

                    self._write_cell(
                        sheet,
                        cursor_x,
                        cursor_y,
                        tax["name"],
                        1,
                        False,
                        XLSX_FONT_SIZE_DEFAULT,
                        True,
                        "white",
                        "left",
                        1,
                        0,
                        XLSX_BORDER_COLOR,
                    )
                    self._write_cell(
                        sheet,
                        cursor_x + 1,
                        cursor_y,
                        tax["base_amount"],
                        1,
                        False,
                        XLSX_FONT_SIZE_DEFAULT,
                        False,
                        "white",
                        "right",
                        1,
                        0,
                        XLSX_BORDER_COLOR,
                    )
                    self._write_cell(
                        sheet,
                        cursor_x + 2,
                        cursor_y,
                        tax["tax_amount"],
                        1,
                        False,
                        XLSX_FONT_SIZE_DEFAULT,
                        False,
                        "white",
                        "right",
                        1,
                        0,
                        XLSX_BORDER_COLOR,
                    )
                    cursor_x += 3

                    if tax_summary.get("tax_non_deductible_column"):
                        self._write_cell(
                            sheet,
                            cursor_x,
                            cursor_y,
                            tax["tax_non_deductible"],
                            1,
                            False,
                            XLSX_FONT_SIZE_DEFAULT,
                            False,
                            "white",
                            "right",
                            1,
                            0,
                            XLSX_BORDER_COLOR,
                        )
                        cursor_x += 1

                    if tax_summary.get("tax_deductible_column"):
                        self._write_cell(
                            sheet,
                            cursor_x,
                            cursor_y,
                            tax["tax_deductible"],
                            1,
                            False,
                            XLSX_FONT_SIZE_DEFAULT,
                            False,
                            "white",
                            "right",
                            1,
                            0,
                            XLSX_BORDER_COLOR,
                        )
                        cursor_x += 1

                    if tax_summary.get("tax_due_column"):
                        self._write_cell(
                            sheet,
                            cursor_x,
                            cursor_y,
                            tax["tax_due"],
                            1,
                            False,
                            XLSX_FONT_SIZE_DEFAULT,
                            False,
                            "white",
                            "right",
                            1,
                            0,
                            XLSX_BORDER_COLOR,
                        )

                    cursor_x = start_x
                    cursor_y += 1

        cursor_x = start_x
        cursor_y += 2

        columns = []
        grids = tax_summary.get("tax_grid_summary_lines")
        if grids:
            start_align_right = start_x + 1
            if len(grids) > 1:
                start_align_right += 1
                columns.append(self.env._("Country"))

            columns += [self.env._("Grid"), "+", "-", self.env._("Impact On Grid")]

            self._write_cell(
                sheet,
                cursor_x,
                cursor_y,
                self.env._("Impact On Grid"),
                len(columns),
                False,
                XLSX_FONT_SIZE_HEADING,
                True,
                "white",
                "left",
                2,
            )

            cursor_y += 1
            for column in columns:
                align = "left"
                if cursor_x >= start_align_right:
                    align = "right"
                self._write_cell(
                    sheet,
                    cursor_x,
                    cursor_y,
                    column,
                    1,
                    False,
                    XLSX_FONT_SIZE_DEFAULT,
                    True,
                    XLSX_GRAY_200,
                    align,
                    2,
                )
                cursor_x += 1

            cursor_x = start_x
            cursor_y += 1

            for country in grids:
                is_country_first_line = True
                for grid_name in grids[country]:
                    if len(grids) > 1:
                        if is_country_first_line:
                            is_country_first_line = not is_country_first_line
                            self._write_cell(
                                sheet,
                                cursor_x,
                                cursor_y,
                                country,
                                1,
                                False,
                                XLSX_FONT_SIZE_DEFAULT,
                                True,
                                "white",
                                "left",
                                1,
                                0,
                                XLSX_BORDER_COLOR,
                            )

                        cursor_x += 1

                    self._write_cell(
                        sheet,
                        cursor_x,
                        cursor_y,
                        grid_name,
                        1,
                        False,
                        XLSX_FONT_SIZE_DEFAULT,
                        True,
                        "white",
                        "left",
                        1,
                        0,
                        XLSX_BORDER_COLOR,
                    )
                    self._write_cell(
                        sheet,
                        cursor_x + 1,
                        cursor_y,
                        grids[country][grid_name].get("+", 0),
                        1,
                        False,
                        XLSX_FONT_SIZE_DEFAULT,
                        False,
                        "white",
                        "right",
                        1,
                        0,
                        XLSX_BORDER_COLOR,
                    )
                    self._write_cell(
                        sheet,
                        cursor_x + 2,
                        cursor_y,
                        grids[country][grid_name].get("-", 0),
                        1,
                        False,
                        XLSX_FONT_SIZE_DEFAULT,
                        False,
                        "white",
                        "right",
                        1,
                        0,
                        XLSX_BORDER_COLOR,
                    )
                    self._write_cell(
                        sheet,
                        cursor_x + 3,
                        cursor_y,
                        grids[country][grid_name]["impact"],
                        1,
                        False,
                        XLSX_FONT_SIZE_DEFAULT,
                        False,
                        "white",
                        "right",
                        1,
                        0,
                        XLSX_BORDER_COLOR,
                    )

                    cursor_x = start_x
                    cursor_y += 1


    @_debug.perf.timed
    def _generate_document_data_for_export(
        self, report, options, export_type="pdf"
    ) -> dict:
        self.env.flush_all()
        report._init_currency_table(options)
        query = report._get_report_query(options, "strict_range")
        account_alias = query.left_join(
            lhs_alias="account_move_line",
            lhs_column="account_id",
            rhs_table="account_account",
            rhs_column="id",
            link="account_id",
        )
        account_code = self.env["account.account"]._field_to_sql(
            account_alias, "code", query
        )
        account_name = self.env["account.account"]._field_to_sql(account_alias, "name")

        query = SQL(
            """
            SELECT
                account_move_line.id AS move_line_id,
                account_move_line.name,
                account_move_line.date,
                am.invoice_date,
                account_move_line.amount_currency,
                %(tax_base_amount)s AS tax_base_amount,
                account_move_line.currency_id AS move_line_currency,
                account_move_line.display_type AS display_type,
                am.id AS move_id,
                am.name AS move_name,
                am.journal_id,
                am.currency_id AS move_currency,
                am.amount_total_in_currency_signed AS amount_currency_total,
                am.currency_id != cp.currency_id AS is_multicurrency,
                p.name AS partner_name,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                %(account_alias)s.account_type AS account_type,
                COALESCE(%(debit)s, 0) AS debit,
                COALESCE(%(credit)s, 0) AS credit,
                COALESCE(%(balance)s, 0) AS balance,
                %(j_name)s AS journal_name,
                j.code AS journal_code,
                j.type AS journal_type,
                cp.currency_id AS company_currency,
                CASE WHEN j.type = 'sale' THEN am.payment_reference WHEN j.type = 'purchase' THEN am.ref END AS reference,
                array_remove(array_agg(DISTINCT %(tax_name)s), NULL) AS taxes,
                array_remove(array_agg(DISTINCT %(tag_name)s), NULL) AS tax_grids
            FROM %(table)s
            %(currency_table_join)s
            JOIN account_move am ON am.id = account_move_line.move_id
            LEFT JOIN res_partner p ON p.id = account_move_line.partner_id
            JOIN account_journal j ON j.id = am.journal_id
            JOIN res_company cp ON cp.id = am.company_id
            LEFT JOIN account_move_line_account_tax_rel aml_at_rel ON aml_at_rel.account_move_line_id = account_move_line.id
            LEFT JOIN account_tax parent_tax ON parent_tax.id = aml_at_rel.account_tax_id and parent_tax.amount_type = 'group'
            LEFT JOIN account_tax_filiation_rel tax_filiation_rel ON tax_filiation_rel.parent_tax = parent_tax.id
            LEFT JOIN account_tax tax ON (tax.id = aml_at_rel.account_tax_id and tax.amount_type != 'group') or tax.id = tax_filiation_rel.child_tax
            LEFT JOIN account_account_tag_account_move_line_rel tag_rel ON tag_rel.account_move_line_id = account_move_line.id
            LEFT JOIN account_account_tag tag ON tag_rel.account_account_tag_id = tag.id
            LEFT JOIN res_currency journal_curr ON journal_curr.id = j.currency_id
            WHERE %(case_statement)s AND %(search_conditions)s
            GROUP BY "account_move_line".id, am.id, p.id, %(account_alias)s.id, j.id, cp.id, journal_curr.id, account_code, account_name, account_currency_table.rate
            ORDER BY
                CASE j.type
                    WHEN 'sale' THEN 1
                    WHEN 'purchase' THEN 2
                    WHEN 'general' THEN 3
                    WHEN 'bank' THEN 4
                    ELSE 5
                END,
                j.sequence,
                CASE WHEN am.name = '/' THEN 1 ELSE 0 END, am.date, am.name, am.id,
                CASE %(account_alias)s.account_type
                    WHEN 'liability_payable' THEN 1
                    WHEN 'asset_receivable' THEN 1
                    WHEN 'liability_credit_card' THEN 5
                    WHEN 'asset_cash' THEN 5
                    ELSE 2
                END,
                (
                    SELECT tax_rep.tax_id
                      FROM account_tax_repartition_line tax_rep
                     WHERE tax_rep.id = account_move_line.tax_repartition_line_id
                ) NULLS FIRST
            """,
            table=query.from_clause,
            currency_table_join=report._currency_table_aml_join(options),
            debit=report._currency_table_apply_rate(SQL('"account_move_line".debit')),
            credit=report._currency_table_apply_rate(SQL('"account_move_line".credit')),
            balance=report._currency_table_apply_rate(
                SQL('"account_move_line".balance')
            ),
            tax_base_amount=report._currency_table_apply_rate(
                SQL('"account_move_line".tax_base_amount')
            ),
            case_statement=self._get_payment_lines_filter_case_statement(options),
            search_conditions=query.where_clause,
            account_code=account_code,
            account_name=account_name,
            account_alias=SQL.identifier(account_alias),
            j_name=self.env["account.journal"]._field_to_sql("j", "name"),
            tax_name=self.env["account.tax"]._field_to_sql("tax", "name"),
            tag_name=self.env["account.account.tag"]._field_to_sql("tag", "name"),
        )

        self.env.cr.execute(query)
        result = {}

        for entry in self.env.cr.dictfetchall():
            result.setdefault(entry["journal_id"], {})
            result[entry["journal_id"]].setdefault(entry["move_id"], [])
            result[entry["journal_id"]][entry["move_id"]].append(entry)
        _debug.perf.count("export_aml_rows_fetched", rows=self.env.cr.rowcount)
        _debug.pipeline(
            "export_amls_grouped",
            report=report,
            export_type=export_type,
            journals=len(result),
        )

        journals_vals = []
        account_move_vals_lists = [
            list(journal_entry_dict.values()) for journal_entry_dict in result.values()
        ]
        journal_headers = [
            {
                "id": account_move_vals_list[0][0]["journal_id"],
                "name": account_move_vals_list[0][0]["journal_name"],
                "code": account_move_vals_list[0][0]["journal_code"],
                "type": account_move_vals_list[0][0]["journal_type"],
            }
            for account_move_vals_list in account_move_vals_lists
        ]
        exported_journal_ids = {header["id"] for header in journal_headers}
        initial_balances = self._query_bank_journal_initial_balances(
            options,
            {
                header["id"]
                for header in journal_headers
                if self._is_bank_journal_export_required(header)
            },
        )
        journal_ids_with_tax = self._get_journal_ids_with_tax(options)
        tax_summaries = self._get_tax_summary_sections(
            options,
            self.env["account.journal"].browse(
                sorted(exported_journal_ids & journal_ids_with_tax)
            ),
            with_global=bool(exported_journal_ids & journal_ids_with_tax),
        )

        for journal_vals, account_move_vals_list in zip(
            journal_headers, account_move_vals_lists, strict=True
        ):
            journal_vals["initial_balance"] = initial_balances.get(
                journal_vals["id"], 0.0
            )
            if journal_vals["id"] in tax_summaries:
                journal_vals["tax_summary"] = tax_summaries[journal_vals["id"]]

            journal_vals["lines"] = self._get_export_lines_for_journal(
                report, options, export_type, journal_vals, account_move_vals_list
            )
            journal_vals["columns"] = self._get_columns_for_journal(
                journal_vals, export_type
            )
            journals_vals.append(journal_vals)
            _debug.pipeline(
                "export_journal_built",
                report=report,
                journal=journal_vals["id"],
                journal_type=journal_vals["type"],
                moves=len(account_move_vals_list),
                lines=len(journal_vals["lines"]),
                tax_summary="tax_summary" in journal_vals,
            )

        _debug.logic(
            "global_tax_summary_needed",
            report=report,
            journals=len(journals_vals),
            needed=None in tax_summaries,
        )
        return {
            "journals_vals": journals_vals,
            "global_tax_summary": tax_summaries.get(None, False),
        }

    @_debug.perf.timed
    def _get_columns_for_journal(self, journal, export_type="pdf"):
        columns = [
            {"name": self.env._("Document"), "label": "document"},
        ]

        if export_type == "pdf":
            columns.append({"name": self.env._("Account"), "label": "account_label"})
        else:
            columns.extend(
                [
                    {"name": self.env._("Account Code"), "label": "account_code"},
                    {"name": self.env._("Account Label"), "label": "account_label"},
                ]
            )

        columns.extend(
            [
                {"name": self.env._("Name"), "label": "name"},
                {
                    "name": self.env._("Debit"),
                    "label": "debit",
                    "class": "o_right_alignment ",
                },
                {
                    "name": self.env._("Credit"),
                    "label": "credit",
                    "class": "o_right_alignment ",
                },
            ]
        )

        if journal.get("tax_summary"):
            columns.append(
                {"name": self.env._("Taxes"), "label": "taxes"},
            )
            if journal["tax_summary"].get("tax_grid_summary_lines"):
                columns.append({"name": self.env._("Tax Grids"), "label": "tax_grids"})

        if self._is_bank_journal_export_required(journal):
            columns.append(
                {
                    "name": self.env._("Balance"),
                    "label": "balance",
                    "class": "o_right_alignment ",
                }
            )

            if journal.get("multicurrency_column"):
                columns.append(
                    {
                        "name": self.env._("Amount Currency"),
                        "label": "amount_currency",
                        "class": "o_right_alignment ",
                    }
                )

        _debug.logic(
            "journal_columns_chosen",
            journal=journal.get("id"),
            journal_type=journal.get("type"),
            export_type=export_type,
            tax_summary=bool(journal.get("tax_summary")),
            multicurrency_column=bool(journal.get("multicurrency_column")),
            columns=len(columns),
        )
        return columns

    def _is_bank_journal_export_required(self, journal_vals) -> bool:
        return journal_vals.get("type") == "bank"

    @_debug.perf.timed
    def _get_export_lines_for_journal(
        self, report, options, export_type, journal_vals, account_move_vals_list
    ):
        lines = []

        _debug.logic(
            "journal_export_lines_route",
            report=report,
            journal=journal_vals.get("id"),
            journal_type=journal_vals.get("type"),
            export_type=export_type,
            moves=len(account_move_vals_list),
        )
        if self._is_bank_journal_export_required(journal_vals):
            return self._get_export_lines_for_bank_journal(
                report, options, export_type, journal_vals, account_move_vals_list
            )

        total_credit = 0
        total_debit = 0

        for i, account_move_line_vals_list in enumerate(account_move_vals_list):
            for j, move_line_entry_vals in enumerate(account_move_line_vals_list):
                document = False
                if j == 0:
                    document = move_line_entry_vals["move_name"]
                elif j == 1:
                    document = move_line_entry_vals["date"]

                line = self._get_base_line(
                    report,
                    options,
                    export_type,
                    document,
                    move_line_entry_vals,
                    j,
                    i % 2 != 0,
                    journal_vals.get("tax_summary"),
                )

                total_credit += move_line_entry_vals["credit"]
                total_debit += move_line_entry_vals["debit"]

                lines.append(line)

            move_vals_entry = account_move_line_vals_list[0]
            if move_vals_entry["is_multicurrency"]:
                amount_currency_name = self.env._(
                    "Amount in currency: %s",
                    report._format_value(
                        options,
                        move_vals_entry["amount_currency_total"],
                        "monetary",
                        format_params={"currency_id": move_vals_entry["move_currency"]},
                    ),
                )
                if len(account_move_line_vals_list) <= 2:
                    lines.append(
                        {
                            "document": {"data": amount_currency_name},
                            "line_class": "o_even " if i % 2 == 0 else "o_odd ",
                            "amount": {
                                "data": move_vals_entry["amount_currency_total"]
                            },
                            "currency_id": {"data": move_vals_entry["move_currency"]},
                        }
                    )
                else:
                    lines[-1]["document"] = {"data": amount_currency_name}
                    lines[-1]["amount"] = {
                        "data": move_vals_entry["amount_currency_total"]
                    }
                    lines[-1]["currency_id"] = {
                        "data": move_vals_entry["move_currency"]
                    }

        lines.append({})

        total_line = {
            "name": {"data": self.env._("Total")},
            "debit": {"data": report._format_value(options, total_debit, "monetary")},
            "credit": {"data": report._format_value(options, total_credit, "monetary")},
        }

        lines.append(total_line)

        _debug.pipeline(
            "journal_export_lines_built",
            report=report,
            journal=journal_vals.get("id"),
            lines=len(lines),
        )
        return lines

    @_debug.perf.timed
    def _get_export_lines_for_bank_journal(
        self, report, options, export_type, journal_vals, account_moves_vals_list
    ):
        lines = []

        current_balance = journal_vals["initial_balance"]
        lines.append(
            {
                "name": {"data": self.env._("Starting Balance")},
                "balance": {
                    "data": report._format_value(options, current_balance, "monetary")
                },
            }
        )

        _debug.pipeline(
            "bank_initial_balance_read",
            report=report,
            journal=journal_vals["id"],
            initial_balance=current_balance,
            moves=len(account_moves_vals_list),
        )
        total_credit = 0
        total_debit = 0

        for i, account_move_line_vals_list in enumerate(account_moves_vals_list):
            is_unreconciled_payment = not any(
                line
                for line in account_move_line_vals_list
                if line["account_type"] in ("liability_credit_card", "asset_cash")
            )

            for j, move_line_entry_vals in enumerate(account_move_line_vals_list):
                if move_line_entry_vals["account_type"] not in (
                    "liability_credit_card",
                    "asset_cash",
                ):
                    document = ""
                    if j == 0:
                        document = f"{move_line_entry_vals['move_name']} ({move_line_entry_vals['date']})"
                    line = self._get_base_line(
                        report,
                        options,
                        export_type,
                        document,
                        move_line_entry_vals,
                        j,
                        i % 2 != 0,
                        journal_vals.get("tax_summary"),
                    )

                    total_credit += move_line_entry_vals["credit"]
                    total_debit += move_line_entry_vals["debit"]

                    if not is_unreconciled_payment:
                        line_balance = -move_line_entry_vals["balance"]
                        current_balance += line_balance
                        line.update(
                            {
                                "balance": {
                                    "data": report._format_value(
                                        options, current_balance, "monetary"
                                    ),
                                    "class": "o_muted "
                                    if self.env.company.currency_id.is_zero(
                                        line_balance
                                    )
                                    else "",
                                },
                            }
                        )

                    if (
                        self.env.user.has_group("base.group_multi_currency")
                        and move_line_entry_vals["move_line_currency"]
                        != move_line_entry_vals["company_currency"]
                    ):
                        journal_vals["multicurrency_column"] = True
                        amount_currency = (
                            -move_line_entry_vals["amount_currency"]
                            if not is_unreconciled_payment
                            else move_line_entry_vals["amount_currency"]
                        )
                        move_line_currency = self.env["res.currency"].browse(
                            move_line_entry_vals["move_line_currency"]
                        )
                        line.update(
                            {
                                "amount_currency": {
                                    "data": report._format_value(
                                        options,
                                        amount_currency,
                                        "monetary",
                                        format_params={
                                            "currency_id": move_line_currency.id
                                        },
                                    ),
                                    "class": "o_muted "
                                    if move_line_currency.is_zero(amount_currency)
                                    else "",
                                }
                            }
                        )
                    lines.append(line)

        lines.append({})

        total_line = {
            "name": {"data": self.env._("Total")},
            "balance": {
                "data": report._format_value(options, current_balance, "monetary")
            },
        }
        lines.append(total_line)

        _debug.pipeline(
            "bank_export_lines_built",
            report=report,
            journal=journal_vals["id"],
            lines=len(lines),
            multicurrency_column=bool(journal_vals.get("multicurrency_column")),
            closing_balance=current_balance,
        )
        return lines

    @_debug.perf.timed
    def _get_base_line(
        self,
        report,
        options,
        export_type,
        document,
        line_entry,
        line_index,
        even,
        has_taxes,
    ):
        company_currency = self.env.company.currency_id

        name = line_entry["name"] or line_entry["reference"]
        account_label = line_entry["partner_name"] or line_entry["account_name"]

        if line_entry["account_type"] not in ("asset_receivable", "liability_payable"):
            account_label = line_entry["account_name"]
        elif line_entry["partner_name"] and line_entry["account_type"] in (
            "asset_receivable",
            "liability_payable",
        ):
            name = f"{line_entry['partner_name']} {name or ''}"

        line = {
            "line_class": "o_even " if even else "o_odd ",
            "document": {
                "data": document,
                "class": "o_bold " if line_index == 0 else "",
            },
            "account_code": {"data": line_entry["account_code"]},
            "account_label": {
                "data": (
                    account_label
                    if export_type != "pdf"
                    else (
                        f"{line_entry['account_code']} "
                        + (
                            line_entry["account_name"][:35] + "..."
                            if len(line_entry["account_name"]) > 35
                            else line_entry["account_name"]
                        )
                    )
                )
            },
            "name": {"data": name},
            "debit": {
                "data": report._format_value(options, line_entry["debit"], "monetary"),
                "class": "o_muted "
                if company_currency.is_zero(line_entry["debit"])
                else "",
            },
            "credit": {
                "data": report._format_value(options, line_entry["credit"], "monetary"),
                "class": "o_muted "
                if company_currency.is_zero(line_entry["credit"])
                else "",
            },
        }

        if has_taxes:
            tax_val = ""
            if line_entry["taxes"]:
                tax_val = self.env._("T: %s", ", ".join(line_entry["taxes"]))
            elif line_entry["tax_base_amount"] is not None:
                tax_val = self.env._(
                    "B: %s",
                    report._format_value(
                        options, line_entry["tax_base_amount"], "monetary"
                    ),
                )

            line.update(
                {
                    "taxes": {"data": tax_val},
                    "tax_grids": {"data": ", ".join(line_entry["tax_grids"])},
                }
            )

        return line


    def _get_payment_lines_filter_case_statement(self, options):
        if not options.get("show_payment_lines"):
            return SQL(
                """
                    (j.type != 'bank' OR EXISTS(
                        SELECT
                            1
                        FROM account_move_line
                        JOIN account_account acc ON acc.id = account_move_line.account_id
                        WHERE account_move_line.move_id = am.id
                        AND acc.account_type IN ('liability_credit_card', 'asset_cash')
                    ))
                """
            )
        else:
            return SQL("TRUE")

    @_debug.perf.timed
    def _query_bank_journal_initial_balances(self, options, journal_ids) -> dict:
        if not journal_ids:
            return {}
        report = self.env["report.formula"].browse(options["report_id"])
        query = report._get_report_query(
            options,
            "to_beginning_of_period",
            domain=[("journal_id", "in", list(journal_ids))],
        )
        self.env.cr.execute(
            SQL(
                """
                SELECT journal.id AS journal_id,
                       COALESCE(SUM(%(balance)s), 0) AS balance
                FROM %(table)s
                %(currency_table_join)s
                JOIN account_journal journal ON journal.id = "account_move_line".journal_id AND account_move_line.account_id = journal.default_account_id
                WHERE %(search_conditions)s
                GROUP BY journal.id
            """,
                table=query.from_clause,
                balance=report._currency_table_apply_rate(
                    SQL('"account_move_line".balance')
                ),
                currency_table_join=report._currency_table_aml_join(options),
                search_conditions=query.where_clause,
            )
        )
        initial_balances = dict(self.env.cr.fetchall())
        _debug.perf.count(
            "bank_journal_initial_balances_fetched",
            journals=len(journal_ids),
            rows=len(initial_balances),
        )
        return initial_balances


    def _get_journal_ids_with_tax(self, options) -> set:
        report = self.env["report.formula"].browse(options.get("report_id"))
        domain = Domain("tax_ids", "!=", False) & report._get_domain_options(
            options, "strict_range"
        )
        return {
            journal.id
            for [journal] in self.env["account.move.line"]._read_group(
                domain, ["journal_id"]
            )
        }

    def _get_used_tax_ids_by_journal(self, options, journal_ids) -> dict:
        report = self.env["report.formula"].browse(options.get("report_id"))
        domain = (
            Domain("journal_id", "in", list(journal_ids))
            & Domain("tax_ids", "!=", False)
            & report._get_domain_options(options, "strict_range")
        )
        used_tax_ids_by_journal = {journal_id: set() for journal_id in journal_ids}
        for journal, tax in self.env["account.move.line"]._read_group(
            domain, ["journal_id", "tax_ids"]
        ):
            used_tax_ids_by_journal[journal.id].update((tax | tax.children_tax_ids).ids)
        return used_tax_ids_by_journal

    @_debug.perf.timed
    def _get_tax_summary_sections(self, options, journals, with_global=True) -> dict:
        section_keys = [*([None] if with_global else []), *journals.ids]
        _debug.logic(
            "tax_summary_sections_requested",
            report=options.get("report_id"),
            journals=journals,
            with_global=with_global,
        )
        if not section_keys:
            return {}

        tax_report_options = self._get_generic_tax_report_options(options)
        tax_report_lines_by_key = self._get_generic_tax_summary_for_sections(
            options, tax_report_options, section_keys
        )
        tax_grid_summary_lines_by_key = self._get_tax_grids_summary(
            options, tax_report_options, section_keys
        )
        return {
            key: self._build_tax_summary_section(
                tax_report_lines_by_key[key], tax_grid_summary_lines_by_key[key]
            )
            for key in section_keys
        }

    def _build_tax_summary_section(
        self, tax_report_lines, tax_grid_summary_lines
    ) -> dict:
        tax_non_deductible_column = any(
            line.get("tax_non_deductible_no_format")
            for country_vals_list in tax_report_lines.values()
            for line in country_vals_list
        )
        tax_deductible_column = any(
            line.get("tax_deductible_no_format")
            for country_vals_list in tax_report_lines.values()
            for line in country_vals_list
        )
        tax_due_column = any(
            line.get("tax_due_no_format")
            for country_vals_list in tax_report_lines.values()
            for line in country_vals_list
        )
        return {
            "tax_report_lines": tax_report_lines,
            "tax_non_deductible_column": tax_non_deductible_column,
            "tax_deductible_column": tax_deductible_column,
            "tax_due_column": tax_due_column,
            "extra_columns": int(tax_non_deductible_column)
            + int(tax_deductible_column)
            + int(tax_due_column),
            "tax_grid_summary_lines": tax_grid_summary_lines,
        }

    @_debug.perf.timed
    def _get_generic_tax_report_options(self, options):
        generic_tax_report = self.env.ref("account.generic_tax_report")
        previous_option = options.copy()
        previous_option.update(
            {
                "selected_variant_id": generic_tax_report.id,
                "date_from": options.get("date", {}).get("date_from"),
                "date_to": options.get("date", {}).get("date_to"),
            }
        )
        tax_report_options = generic_tax_report.get_options(previous_option)
        journal_report = self.env["report.formula"].browse(options["report_id"])
        tax_report_options["forced_domain"] = list(
            Domain(tax_report_options.get("forced_domain", []))
            & journal_report._get_domain_options(options, "strict_range")
        )
        return tax_report_options

    def _get_tax_summary_section_options(self, tax_report_options, section_keys):
        base_key, base_group = next(iter(tax_report_options["column_groups"].items()))
        base_columns = [
            column
            for column in tax_report_options["columns"]
            if column["column_group_key"] == base_key
        ]
        column_groups = {}
        columns = []
        group_key_by_section = {}
        for section_key in section_keys:
            group_key = base_key if section_key is None else f"journal_{section_key}"
            group_key_by_section[section_key] = group_key
            column_groups[group_key] = (
                base_group
                if section_key is None
                else {
                    **base_group,
                    "forced_domain": [
                        *base_group.get("forced_domain", []),
                        ("journal_id", "=", section_key),
                    ],
                }
            )
            columns += [
                {**column, "column_group_key": group_key} for column in base_columns
            ]
        return (
            {**tax_report_options, "column_groups": column_groups, "columns": columns},
            group_key_by_section,
        )

    @_debug.perf.timed
    def _get_tax_grids_summary(self, options, tax_report_options, section_keys):
        report = self.env.ref("account.journal_report")
        query = report._get_report_query(tax_report_options, "strict_range")
        country_code = self.env["res.country"]._field_to_sql("country", "code")
        tag_name = self.env["account.account.tag"]._field_to_sql("tag", "name")
        query = SQL(
            """
                SELECT
                    "account_move_line".journal_id,
                    %(country_code)s AS country_code,
                    tag.id,
                    %(tag_name)s AS name,
                    SUM(COALESCE(%(debit)s, 0)) AS debit,
                    SUM(COALESCE(%(credit)s, 0)) AS credit
                FROM %(table_references)s
                %(currency_table_join)s
                JOIN account_account_tag_account_move_line_rel rel ON "account_move_line".id = rel.account_move_line_id
                JOIN account_account_tag tag ON tag.id = rel.account_account_tag_id
                JOIN res_country country ON country.id = tag.country_id
                WHERE %(search_condition)s
                  AND applicability = 'taxes'
             GROUP BY "account_move_line".journal_id, country_code, tag.id
             ORDER BY country_code, %(tag_name)s
        """,
            country_code=country_code,
            tag_name=tag_name,
            debit=report._currency_table_apply_rate(SQL('"account_move_line".debit')),
            credit=report._currency_table_apply_rate(SQL('"account_move_line".credit')),
            currency_table_join=report._currency_table_aml_join(tax_report_options),
            table_references=query.from_clause,
            search_condition=query.where_clause,
        )
        self.env.cr.execute(query)
        query_res = self.env.cr.fetchall()
        _debug.perf.count("tax_grid_rows_fetched", rows=len(query_res))

        id2tag = (
            self.env["account.account.tag"]
            .browse([tag_id for _journal_id, _country_name, tag_id, *__ in query_res])
            .grouped("id")
        )
        amounts_by_key = {section_key: {} for section_key in section_keys}
        for journal_id, country_code, tag_id, name, debit, credit in query_res:
            if id2tag[tag_id].balance_negate:
                debit, credit = credit, debit
            for section_key in (None, journal_id):
                if section_key not in amounts_by_key:
                    continue
                grid = (
                    amounts_by_key[section_key]
                    .setdefault(country_code, {})
                    .setdefault(name, {"tag_ids": [], "+": 0.0, "-": 0.0})
                )
                if tag_id not in grid["tag_ids"]:
                    grid["tag_ids"].append(tag_id)
                grid["+"] += debit
                grid["-"] += credit

        res = {}
        for section_key, amounts_by_country in amounts_by_key.items():
            res[section_key] = {}
            for country_code, grids in amounts_by_country.items():
                for name, grid in grids.items():
                    balance = grid["+"] - grid["-"]
                    res[section_key].setdefault(country_code, {})[name] = {
                        "tag_ids": grid["tag_ids"],
                        "balance": report._format_value(options, balance, "monetary"),
                        "balance_no_format": balance,
                        "+": report._format_value(options, grid["+"], "monetary"),
                        "+_no_format": grid["+"],
                        "-": report._format_value(options, grid["-"], "monetary"),
                        "-_no_format": grid["-"],
                        "impact": report._format_value(options, balance, "monetary"),
                    }

        _debug.pipeline(
            "tax_grids_summarized",
            report=report,
            sections=len(section_keys),
            rows=len(query_res),
        )
        return res

    @_debug.perf.timed
    def _get_generic_tax_summary_for_sections(
        self, options, tax_report_options, section_keys
    ):
        report = self.env["report.formula"].browse(options["report_id"])
        section_options, group_key_by_section = self._get_tax_summary_section_options(
            tax_report_options, section_keys
        )
        section_options["account_journal_report_tax_deductibility_columns"] = True
        tax_report = self.env.ref("account.generic_tax_report")
        tax_report_lines = tax_report._get_lines(section_options)

        wanted_columns = {
            "base_amount": "net",
            "tax_amount": "tax",
            "tax_non_deductible": "tax_non_deductible",
            "tax_deductible": "tax_deductible",
            "tax_due": "tax_due",
        }
        tax_values_by_key = {section_key: {} for section_key in section_keys}
        zero_journal_taxes = []
        for tax_report_line in tax_report_lines:
            model, line_id = report._parse_line_id(tax_report_line.get("id"))[-1][1:]
            if model != "account.tax":
                continue
            by_group_and_label = {
                (column["column_group_key"], column["expression_label"]): column[
                    "no_format"
                ]
                for column in tax_report_line["columns"]
            }
            for section_key, group_key in group_key_by_section.items():
                missing = {
                    label
                    for label in wanted_columns.values()
                    if (group_key, label) not in by_group_and_label
                }
                if missing:
                    raise UserError(
                        self.env._(
                            "The tax report did not provide the columns the journal report's tax summary needs: %(labels)s",
                            labels=", ".join(sorted(missing)),
                        )
                    )
                values = {
                    key: by_group_and_label[group_key, label] or 0.0
                    for key, label in wanted_columns.items()
                }
                tax_values_by_key[section_key][line_id] = values
                if section_key is not None and not any(values.values()):
                    zero_journal_taxes.append((section_key, line_id))

        if zero_journal_taxes:
            used_tax_ids_by_journal = self._get_used_tax_ids_by_journal(
                options, {journal_id for journal_id, _tax_id in zero_journal_taxes}
            )
            for journal_id, tax_id in zero_journal_taxes:
                if tax_id not in used_tax_ids_by_journal[journal_id]:
                    del tax_values_by_key[journal_id][tax_id]

        _debug.pipeline(
            "tax_summary_values_read",
            report=report,
            sections=len(section_keys),
            tax_report_lines=len(tax_report_lines),
        )
        res_by_key = {}
        for section_key, tax_values in tax_values_by_key.items():
            res = {}
            for tax in self.env["account.tax"].browse(tax_values.keys()):
                values = tax_values[tax.id]
                res.setdefault(tax.country_id.code, []).append(
                    {
                        **{
                            key: report._format_value(options, value, "monetary")
                            for key, value in values.items()
                        },
                        **{f"{key}_no_format": value for key, value in values.items()},
                        "name": tax.name,
                        "line_id": report._get_generic_line_id("account.tax", tax.id),
                    }
                )
            res_by_key[section_key] = dict(sorted(res.items()))
        return res_by_key


    def journal_report_tax_tag_template_open_aml(self, options, params=None) -> dict:
        tag_ids = params.get("tag_ids")
        domain = (
            self.env["report.formula"]
            .browse(options["report_id"])
            ._get_domain_options(options, "strict_range")
            + [("tax_tag_ids", "in", tag_ids)]
            + self.env["account.move.line"]._get_domain_tax_exigible()
        )

        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Journal Items for Tax Audit"),
            "res_model": "account.move.line",
            "views": [
                [self.env.ref("account.view_move_line_tax_audit_tree").id, "list"]
            ],
            "domain": domain,
            "context": self.env.context,
        }

    def journal_report_action_dropdown_audit_default_tax_report(self, options, params):
        return self.env["account.generic.tax.report.handler"].caret_option_audit_tax(
            options, params
        )

    @_debug.perf.timed
    def journal_report_action_view_tax_journal_items(self, options, params) -> dict:
        ctx = {
            "search_default_posted": 0 if options.get("all_entries") else 1,
            "search_default_date_between": 1,
            "date_from": (params and params.get("date_from"))
            or options.get("date", {}).get("date_from"),
            "date_to": (params and params.get("date_to"))
            or options.get("date", {}).get("date_to"),
            "search_default_journal_id": params.get("journal_id"),
            "expand": 1,
        }
        if params and params.get("tax_type") == "tag":
            ctx.update(
                {
                    "search_default_group_by_tax_tags": 1,
                    "search_default_group_by_account": 2,
                }
            )
        elif params and params.get("tax_type") == "tax":
            ctx.update(
                {
                    "search_default_group_by_taxes": 1,
                    "search_default_group_by_account": 2,
                }
            )

        if params and "journal_id" in params:
            ctx.update(
                {
                    "search_default_journal_id": [params["journal_id"]],
                }
            )

        if (
            options
            and options.get("journals")
            and not ctx.get("search_default_journal_id")
        ):
            selected_journals = [
                journal["id"]
                for journal in options["journals"]
                if journal.get("selected") and journal["model"] == "account.journal"
            ]
            if len(selected_journals) == 1:
                ctx["search_default_journal_id"] = selected_journals

        _debug.logic(
            "tax_journal_items_grouping",
            report=options.get("report_id") if options else None,
            tax_type=params.get("tax_type") if params else None,
            journal_filter=bool(ctx.get("search_default_journal_id")),
        )

        return {
            "name": params.get("name"),
            "view_mode": "list,pivot,graph,kanban",
            "res_model": "account.move.line",
            "views": [(self.env.ref("account.view_account_move_line_list").id, "list")],
            "type": "ir.actions.act_window",
            "domain": [("display_type", "not in", NON_ACCOUNTABLE_DISPLAY_TYPES)],
            "context": ctx,
        }

    def journal_report_action_view_account_move_lines_by_account(
        self, options, params
    ) -> dict:
        report = self.env["report.formula"].browse(options["report_id"])
        journal = self.env["account.journal"].browse(params["journal_id"])
        account = self.env["account.account"].browse(params["account_id"])

        domain = [
            ("journal_id.id", "=", journal.id),
            ("account_id.id", "=", account.id),
        ]
        domain += report._get_domain_options(options, "strict_range")

        return {
            "type": "ir.actions.act_window",
            "name": self.env._(
                "%(journal)s - %(account)s", journal=journal.name, account=account.name
            ),
            "res_model": "account.move.line",
            "views": [[False, "list"]],
            "domain": domain,
        }

    def journal_report_open_aml_by_move(self, options, params):
        report = self.env["report.formula"].browse(options["report_id"])
        journal = self.env["account.journal"].browse(params["journal_id"])
        review = params.get("review")

        context_update = {
            "search_default_group_by_account": 0,
            "show_more_partner_info": 1,
        }

        if review:
            context_update["search_default_to_check"] = 1
            if options["all_entries"]:
                context_update["search_default_to_check_draft"] = 1

        if journal.type in ("bank", "credit"):
            params["view_ref"] = "account.view_journal_report_audit_bank_move_line_tree"
            context_update["search_default_exclude_bank_lines"] = 1
        else:
            params["view_ref"] = "account.view_journal_report_audit_move_line_tree"
            context_update.update(
                {
                    "search_default_group_by_move": 1,
                }
            )
        _debug.logic(
            "audit_view_chosen",
            report=report,
            journal=journal,
            review=review,
            view_ref=params.get("view_ref"),
        )

        action = report.open_journal_items(options=options, params=params)
        action.get("context", {}).update(context_update)
        return action
