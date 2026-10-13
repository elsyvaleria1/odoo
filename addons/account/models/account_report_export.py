import base64
import datetime
import io
import re
from ast import literal_eval
from collections import defaultdict

import markupsafe

from odoo import api, models
from odoo.exceptions import RedirectWarning, UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import html2plaintext
from odoo.tools.misc import format_date

from odoo.addons.account.tools.report_engines import (
    ACCOUNT_CODES_ENGINE_TAG_ID_PREFIX_REGEX,
    parse_account_codes_formula,
)
from odoo.addons.report_formula.models.account_report_custom_handler import (
    AccountReportFileDownloadException,
)

_debug = DebugLog(__name__)


class AccountReportExport(models.Model):
    _inherit = "report.formula"

    @api.model
    @_debug.perf.timed
    def _cron_account_report_send(self, job_count=10) -> None:
        _debug.lifecycle("_cron_account_report_send", records=self)
        to_process = self.env["report.formula"].search(
            [("send_and_print_values", "!=", False)],
        )
        if not to_process:
            _debug.logic("send_skipped", reason="nothing_queued", job_count=job_count)
            return

        _debug.pipeline("send_queue_loaded", reports=to_process, job_count=job_count)
        processed_count = 0
        need_retrigger = False

        for report in to_process:
            if need_retrigger:
                break
            send_and_print_vals = report.send_and_print_values
            report_partner_ids = send_and_print_vals.get("report_options", {}).get(
                "partner_ids", []
            )
            need_retrigger = processed_count + len(report_partner_ids) > job_count
            partner_ids = report_partner_ids[: job_count - processed_count]
            company = self.env["res.company"].browse(
                send_and_print_vals["report_options"]["companies"][0]["id"]
            )
            existing_partner_ids = set(
                self.env["res.partner"].browse(partner_ids).exists().ids
            )
            for partner_id in partner_ids:
                if partner_id in existing_partner_ids:
                    options = {
                        **send_and_print_vals["report_options"],
                        "partner_ids": [partner_id],
                    }
                    self.env["wizard.report.formula.send"]._process_send_and_print(
                        report=report.with_company(company), options=options
                    )
                    processed_count += 1
                report_partner_ids.remove(partner_id)
            _debug.pipeline(
                "report_send_batch",
                report=report,
                partners=len(partner_ids),
                existing_partners=len(existing_partner_ids),
                remaining_partners=len(report_partner_ids),
                processed=processed_count,
                need_retrigger=need_retrigger,
            )
            if report_partner_ids:
                send_and_print_vals["report_options"]["partner_ids"] = (
                    report_partner_ids
                )
                report.send_and_print_values = send_and_print_vals
            else:
                report.send_and_print_values = False

        _debug.logic(
            "send_retrigger_decided",
            need_retrigger=need_retrigger,
            processed=processed_count,
            job_count=job_count,
        )
        if need_retrigger:
            self.env["ir.cron"]._trigger_ref("account.ir_cron_account_report_send")

    @api.model
    def _get_sender_company_for_export(self, options):
        if options.get("tax_unit", "company_only") != "company_only":
            tax_unit = self.env["account.tax.unit"].browse(options["tax_unit"])
            _debug.logic("sender_company_tax_unit", tax_unit=tax_unit)
            return tax_unit.main_company_id

        report_companies = self.env["res.company"].browse(
            self.get_report_company_ids(options)
        )
        options_main_company = report_companies[0]

        if (
            options.get("tax_unit") is not None
            and options_main_company._get_branches_with_same_vat() == report_companies
        ):
            _debug.logic("sender_company_vat_root", companies=report_companies)
            return report_companies.sorted(lambda x: len(x.parent_ids))[0]
        elif options_main_company._is_every_branch_selected():
            _debug.logic("sender_company_branch_root", company=options_main_company)
            return options_main_company.root_id

        _debug.logic("sender_company_main", company=options_main_company)
        return options_main_company

    @_debug.perf.timed
    def _get_report_send_recipients(self, options):
        custom_handler_model = self._get_custom_handler_model()
        if custom_handler_model and hasattr(
            self.env[custom_handler_model], "_get_report_send_recipients"
        ):
            return self.env[custom_handler_model]._get_report_send_recipients(options)
        return self.env["res.partner"]

    def _get_pdf_export_render_values(self, options, lines, report_info):
        render_values = super()._get_pdf_export_render_values(
            options, lines, report_info
        )
        render_values["show_last_annotations"] = options.get("show_last_annotations")
        render_values["status_selection"] = dict(
            self.env["account.audit.account.status"]
            ._fields["status"]
            ._description_selection(self.env)
        )
        if options.get("show_last_annotations"):
            last_annotations = self._get_last_comments_by_line(options, lines)
            for line in lines:
                line["last_comment"] = last_annotations.get(line["id"])
        else:
            render_values["annotations"] = (
                self._prepare_annotations_list_for_pdf_export(
                    options["date"], lines, report_info["annotations"]
                )
            )
        return render_values

    def _get_pdf_extra_option_labels(self, options):
        labels = []
        if (
            self.filter_show_draft
            and options["all_entries"]
            and self.env.user.has_group("account.group_account_readonly")
        ):
            labels.append(self.env._("With Draft Entries"))
        if self.filter_unreconciled and options["unreconciled"]:
            labels.append(self.env._("Unreconciled Entries"))
        if options.get("include_analytic_without_aml"):
            labels.append(self.env._("Including Analytic Simulations"))
        return labels + super()._get_pdf_extra_option_labels(options)

    @_debug.perf.timed
    def _prepare_annotations_list_for_pdf_export(
        self, date_options, lines, annotations_per_line_id
    ):
        annotations_to_render = []
        record_to_number_map = {}
        for line in lines:
            line["annotations"] = []
            for annotation in annotations_per_line_id.get(line["id"], []):
                report_period_date_from = datetime.datetime.strptime(
                    date_options["date_from"], "%Y-%m-%d"
                ).date()
                report_period_date_to = datetime.datetime.strptime(
                    date_options["date_to"], "%Y-%m-%d"
                ).date()
                if (
                    not annotation["date"]
                    or report_period_date_from
                    <= annotation["date"]
                    <= report_period_date_to
                ):
                    if number := record_to_number_map.get(
                        (annotation["model"], annotation["id"])
                    ):
                        line["annotations"].append(str(number))
                        continue
                    number = len(record_to_number_map) + 1
                    record_to_number_map[annotation["model"], annotation["id"]] = number
                    line["annotations"].append(str(number))
                    annotations_to_render.append(
                        {
                            "number": str(number),
                            "body": markupsafe.Markup("<br/>").join(
                                html2plaintext(annotation["body"]).split("\n")
                            ),
                            "date": format_date(self.env, annotation["date"])
                            if annotation["date"]
                            else None,
                        }
                    )
        _debug.pipeline(
            "pdf_annotations_prepared",
            lines=len(lines),
            annotated_lines=len(annotations_per_line_id),
            annotations=len(annotations_to_render),
        )
        return annotations_to_render

    @_debug.perf.timed
    def get_vat_for_export(self, options, raise_warning=True):
        self.check_singleton()

        if (
            self.filter_multi_company == "tax_units"
            and options["tax_unit"] != "company_only"
        ):
            tax_unit = self.env["account.tax.unit"].browse(options["tax_unit"])
            _debug.logic(
                "vat_source", report=self, source="tax_unit", tax_unit=tax_unit
            )
            return tax_unit.vat

        company = self._get_sender_company_for_export(options)

        if company.tax_config_id.account_fiscal_country_id != self.country_id:
            foreign_vat_fpos = self.env["account.fiscal.position"].search(
                [
                    *self.env["account.fiscal.position"]._get_domain_company_compatible(
                        company
                    ),
                    ("foreign_vat", "!=", False),
                    ("country_id", "=", self.country_id.id),
                ],
                limit=1,
            )
            if foreign_vat_fpos:
                _debug.logic(
                    "vat_source",
                    report=self,
                    source="foreign_vat_fpos",
                    fiscal_position=foreign_vat_fpos,
                )
                return foreign_vat_fpos.foreign_vat

        if not company.vat and raise_warning:
            action = self.env.ref("base.action_res_company_form")
            raise RedirectWarning(
                self.env._(
                    "No VAT number associated with your company. Please define one."
                ),
                action.id,
                self.env._("Company Settings"),
            )
        _debug.logic(
            "vat_source",
            report=self,
            source="company",
            company=company,
            missing=not company.vat,
        )
        return company.vat

    @_debug.perf.timed
    def action_download_xlsx_accounts_coverage_report(self) -> dict:
        _debug.lifecycle("action_download_xlsx_accounts_coverage_report", records=self)
        self.check_singleton()
        if not self.is_account_coverage_report_available:
            raise UserError(
                self.env._(
                    "The Accounts Coverage Report is not available for this report."
                )
            )

        output = io.BytesIO()
        import xlsxwriter

        with xlsxwriter.Workbook(output, {"in_memory": True}) as workbook:
            worksheet = workbook.add_worksheet(self.env._("Accounts coverage"))
            worksheet.set_column(0, 0, 20)
            worksheet.set_column(1, 1, 75)
            worksheet.set_column(2, 2, 80)
            worksheet.freeze_panes(1, 0)

            headers = [
                self.env._("Account Code / Tag"),
                self.env._("Error message"),
                self.env._("Report lines mentioning the account code"),
                "#FFFFFF",
            ]
            lines = [headers] + self._generate_accounts_coverage_report_xlsx_lines()
            for i, line in enumerate(lines):
                worksheet.write_row(
                    i, 0, line[:-1], workbook.add_format({"bg_color": line[-1]})
                )

        attachment_id = self.env["ir.attachment"].create(
            {
                "name": f"{self.display_name} - {self.env._('Accounts Coverage Report')}",
                "datas": base64.encodebytes(output.getvalue()),
            }
        )
        _debug.pipeline(
            "coverage_xlsx_written",
            report=self,
            rows=len(lines),
            attachment=attachment_id,
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment_id.id}",
            "target": "download",
        }

    @_debug.perf.timed
    def _generate_accounts_coverage_report_xlsx_lines(self):

        def get_domain_account(prefix):
            if tag_matching := ACCOUNT_CODES_ENGINE_TAG_ID_PREFIX_REGEX.match(prefix):
                if tag_matching["ref"]:
                    account_tag_id = self.env["ir.model.data"]._xmlid_to_res_id(
                        tag_matching["ref"]
                    )
                else:
                    account_tag_id = int(tag_matching["id"])
                return "tag_ids", "in", (account_tag_id,)
            else:
                return "code", "=like", f"{prefix}%"

        self.check_singleton()

        AccountAccount = self.env["account.account"].with_context(active_test=False)
        all_reported_accounts = AccountAccount
        accounts_by_expressions = {}
        reported_account_codes = []
        non_existing_codes = defaultdict(lambda: self.env["report.formula.line"])
        lines_per_non_linked_tag = defaultdict(lambda: self.env["report.formula.line"])
        lines_using_bad_operator_per_tag = defaultdict(
            lambda: self.env["report.formula.line"]
        )
        candidate_duplicate_codes = defaultdict(lambda: self.env["report.formula.line"])
        duplicate_codes = defaultdict(lambda: self.env["report.formula.line"])
        duplicate_codes_same_line = defaultdict(lambda: self.env["report.formula.line"])
        common_account_domain = [
            *AccountAccount._get_domain_company_compatible(self.env.company),
        ]

        tag_ids_linked_to_account = set(
            AccountAccount.search([("tag_ids", "!=", False)]).tag_ids.ids
        )

        expressions = self.line_ids.expression_ids._expand_aggregations()
        _debug.pipeline(
            "coverage_expressions_expanded",
            report=self,
            expressions=expressions,
            linked_tags=len(tag_ids_linked_to_account),
        )

        def get_condition_rewriter(expr):
            def rewrite_condition(condition):
                field_expr = condition.field_expr
                if not field_expr.startswith("account_id."):
                    return Domain.TRUE
                operand = [
                    field_expr.replace("account_id.", "", 1),
                    condition.operator,
                    condition.value,
                ]
                if operand[0] == "code" and not AccountAccount.search_count(
                    [operand], limit=1
                ):
                    _debug.logic(
                        "coverage_code_missing", expression=expr, code=operand[2]
                    )
                    non_existing_codes[operand[2]] |= expr.report_line_id
                elif operand[0] == "tag_ids":
                    tag_ids = operand[2]
                    if not isinstance(tag_ids, (list, tuple, set)):
                        tag_ids = [tag_ids]

                    if operand[1] in ("=", "in"):
                        tag_ids_to_browse = [
                            tag_id
                            for tag_id in tag_ids
                            if tag_id not in tag_ids_linked_to_account
                        ]
                        for tag in self.env["account.account.tag"].browse(
                            tag_ids_to_browse
                        ):
                            lines_per_non_linked_tag[f"{tag.name} ({tag.id})"] |= (
                                expr.report_line_id
                            )
                    else:
                        _debug.logic(
                            "coverage_tag_bad_operator",
                            expression=expr,
                            operator=operand[1],
                            tags=len(tag_ids),
                        )
                        for tag in self.env["account.account.tag"].browse(tag_ids):
                            lines_using_bad_operator_per_tag[
                                f"{tag.name} ({tag.id}) - Operator: {operand[1]}"
                            ] |= expr.report_line_id

                return Domain(*operand)

            return rewrite_condition

        for i, expr in enumerate(expressions):
            reported_accounts = AccountAccount
            if expr.engine == "domain":
                domain = literal_eval(expr.formula.strip())

                reported_accounts += AccountAccount.search(  # noqa: E8507 -- a coverage audit: one query per expression, each with its own domain
                    Domain(domain).map_conditions(get_condition_rewriter(expr))
                )
            elif expr.engine == "account_codes":
                account_codes = [
                    {
                        "prefix": term.prefix,
                        "balance": term.balance_character,
                        "require": [term.required_tag.token]
                        if term.required_tag
                        else [],
                        "exclude": [
                            *term.excluded_prefixes,
                            *(tag.token for tag in term.excluded_tags),
                        ],
                        "line": expr.report_line_id,
                    }
                    for term in parse_account_codes_formula(expr.formula)
                ]

                for account_code in account_codes:
                    reported_account_codes.append(account_code)
                    exclude_domain_accounts = [
                        get_domain_account(exclude_code)
                        for exclude_code in account_code["exclude"]
                    ]
                    reported_accounts += AccountAccount.search(  # noqa: E8507 -- a coverage audit: one query per account code, each with its own prefix and exclusions
                        [
                            *common_account_domain,
                            get_domain_account(account_code["prefix"]),
                            *map(get_domain_account, account_code["require"]),
                            *[
                                excl_domain
                                for excl_tuple in exclude_domain_accounts
                                for excl_domain in ("!", excl_tuple)
                            ],
                        ]
                    )

                    prefixes_to_check = [
                        account_code["prefix"],
                        *account_code["require"],
                        *account_code["exclude"],
                    ]
                    for prefix_to_check in prefixes_to_check:
                        account_domain = get_domain_account(prefix_to_check)
                        if not AccountAccount.search_count(  # noqa: E8507 -- a coverage audit: one existence probe per prefix
                            [
                                *common_account_domain,
                                account_domain,
                            ],
                            limit=1,
                        ):
                            if account_domain[0] == "code":
                                non_existing_codes[prefix_to_check] |= account_code[
                                    "line"
                                ]
                            elif account_domain[0] == "tag_ids":
                                lines_per_non_linked_tag[prefix_to_check] |= (
                                    account_code["line"]
                                )

            all_reported_accounts |= reported_accounts
            accounts_by_expressions[expr.id] = reported_accounts

            if len(reported_accounts) != len(set(reported_accounts)):
                seen = set()
                for reported_account in reported_accounts:
                    if reported_account not in seen:
                        seen.add(reported_account)
                    else:
                        duplicate_codes_same_line[reported_account.code] |= (
                            expr.report_line_id
                        )

            for expr2 in expressions[: i + 1]:
                reported_accounts2 = accounts_by_expressions[expr2.id]
                for duplicate_account in reported_accounts & reported_accounts2:
                    if (
                        len(expr.report_line_id | expr2.report_line_id) > 1
                        and expr.date_scope == expr2.date_scope
                        and expr.subformula == expr2.subformula
                    ):
                        candidate_duplicate_codes[duplicate_account.code] |= (
                            expr.report_line_id | expr2.report_line_id
                        )

        _debug.pipeline(
            "coverage_expressions_scanned",
            report=self,
            reported_accounts=len(all_reported_accounts),
            account_code_terms=len(reported_account_codes),
            candidate_duplicates=len(candidate_duplicate_codes),
            same_line_duplicates=len(duplicate_codes_same_line),
            non_existing_codes=len(non_existing_codes),
            non_linked_tags=len(lines_per_non_linked_tag),
            bad_operator_tags=len(lines_using_bad_operator_per_tag),
        )
        for (
            candidate_duplicate_code,
            candidate_duplicate_lines,
        ) in candidate_duplicate_codes.items():
            if len(set(candidate_duplicate_lines.mapped("name"))) <= 1:
                continue
            seen_balance_chars = []
            seen_balance_chars.extend(
                reported_account_code["balance"]
                for reported_account_code in reported_account_codes
                if candidate_duplicate_code.startswith(reported_account_code["prefix"])
                and reported_account_code["balance"]
            )
            if (
                not seen_balance_chars
                or seen_balance_chars.count("C") > 1
                or seen_balance_chars.count("D") > 1
            ):
                duplicate_codes[candidate_duplicate_code] |= candidate_duplicate_lines

        _debug.logic(
            "coverage_duplicates_verified",
            report=self,
            candidates=len(candidate_duplicate_codes),
            verified=len(duplicate_codes),
        )
        if self.root_report_id == self.env.ref("account.profit_and_loss"):
            accounts_in_coa = AccountAccount.search(
                [
                    *common_account_domain,
                    (
                        "account_type",
                        "in",
                        (
                            "income",
                            "income_other",
                            "expense",
                            "expense_depreciation",
                            "expense_direct_cost",
                        ),
                    ),
                    ("account_type", "!=", "off_balance"),
                ]
            )
            _debug.logic(
                "coverage_coa_scope",
                report=self,
                scope="profit_and_loss",
                coa_accounts=len(accounts_in_coa),
            )
        else:
            accounts_in_coa = AccountAccount.search(
                [
                    *common_account_domain,
                    (
                        "account_type",
                        "not in",
                        (
                            "off_balance",
                            "income",
                            "income_other",
                            "expense",
                            "expense_depreciation",
                            "expense_direct_cost",
                        ),
                    ),
                ]
            )
            _debug.logic(
                "coverage_coa_scope",
                report=self,
                scope="balance_sheet",
                coa_accounts=len(accounts_in_coa),
            )

        non_reported_codes = {
            code
            for code in (accounts_in_coa - all_reported_accounts).mapped("code")
            if code
        }

        all_reported_codes = sorted(
            {code for code in all_reported_accounts.mapped("code") if code}
            | non_reported_codes
            | non_existing_codes.keys()
        )
        _debug.pipeline(
            "coverage_codes_collected",
            report=self,
            codes=len(all_reported_codes),
            non_reported=len(non_reported_codes),
        )
        errors_trie = self._get_accounts_coverage_report_errors_trie(
            all_reported_codes,
            non_reported_codes,
            duplicate_codes,
            duplicate_codes_same_line,
            non_existing_codes,
        )
        errors_trie["children"].update(
            **self._get_account_tag_coverage_report_errors_trie(
                lines_per_non_linked_tag, lines_using_bad_operator_per_tag
            )
        )

        errors_trie = self._regroup_accounts_coverage_report_errors_trie(errors_trie)
        return self._get_accounts_coverage_report_coverage_lines("", errors_trie)

    @api.depends("country_id", "chart_template", "root_report_id")
    @_debug.perf.timed
    def _compute_is_account_coverage_report_available(self) -> None:
        for report in self:
            report.is_account_coverage_report_available = (
                (
                    report.availability_condition == "country"
                    and self.env.company.tax_config_id.account_fiscal_country_id
                    == report.country_id
                )
                or (
                    report.availability_condition == "coa"
                    and self.env.company.account_config_id.chart_template
                    == report.chart_template
                )
                or report.availability_condition == "always"
            ) and report.root_report_id in (
                self.env.ref("account.profit_and_loss", raise_if_not_found=False),
                self.env.ref("account.balance_sheet", raise_if_not_found=False),
            )

    @_debug.perf.timed
    def _get_accounts_coverage_report_errors_trie(
        self,
        all_reported_codes,
        non_reported_codes,
        duplicate_codes,
        duplicate_codes_same_line,
        non_existing_codes,
    ):
        errors_trie = {"children": {}, "lines": {}, "errors": {None}}
        for reported_code in all_reported_codes:
            current_trie = errors_trie
            lines = self.env["report.formula.line"]
            errors = set()
            if reported_code in non_reported_codes:
                errors.add("NON_REPORTED")
            elif reported_code in duplicate_codes_same_line:
                lines |= duplicate_codes_same_line[reported_code]
                errors.add("DUPLICATE_SAME_LINE")
            elif reported_code in duplicate_codes:
                lines |= duplicate_codes[reported_code]
                errors.add("DUPLICATE")
            elif reported_code in non_existing_codes:
                lines |= non_existing_codes[reported_code]
                errors.add("NON_EXISTING")
            else:
                errors.add("NONE")

            for j in range(1, len(reported_code) + 1):
                current_trie = current_trie["children"].setdefault(
                    reported_code[:j],
                    {"children": {}, "lines": lines, "errors": errors},
                )
        _debug.pipeline(
            "coverage_errors_trie_built",
            report=self,
            codes=len(all_reported_codes),
            roots=len(errors_trie["children"]),
        )
        return errors_trie

    @api.model
    def _get_account_tag_coverage_report_errors_trie(
        self, lines_per_non_linked_tag, lines_per_bad_operator_tag
    ):
        errors = {
            non_linked_tag: {
                "children": {},
                "lines": line,
                "errors": {"NON_LINKED"},
            }
            for non_linked_tag, line in lines_per_non_linked_tag.items()
        }
        errors.update(
            {
                bad_operator_tag: {
                    "children": {},
                    "lines": line,
                    "errors": {"BAD_OPERATOR"},
                }
                for bad_operator_tag, line in lines_per_bad_operator_tag.items()
            }
        )
        return errors

    def _regroup_accounts_coverage_report_errors_trie(self, trie):
        if trie.get("children"):
            children_errors = set()
            children_lines = self.env["report.formula.line"]
            if trie.get("errors"):
                children_errors |= set(trie.get("errors"))
            for child in trie["children"].values():
                regroup = self._regroup_accounts_coverage_report_errors_trie(child)
                children_lines |= regroup["lines"]
                children_errors |= set(regroup["errors"])
            if (
                len(children_errors) == 1
                and children_lines
                and children_lines == trie["lines"]
            ):
                trie["children"] = {}
                trie["lines"] = children_lines
                trie["errors"] = children_errors
        return trie

    @_debug.perf.timed
    def _get_accounts_coverage_report_coverage_lines(
        self, subcode, trie, coverage_lines=None
    ):
        ERRORS = {
            "NON_REPORTED": {
                "msg": self.env._(
                    "This account exists in the Chart of Accounts but is not mentioned in any line of the report"
                ),
                "color": "#FF0000",
            },
            "DUPLICATE": {
                "msg": self.env._(
                    "This account is reported in multiple lines of the report"
                ),
                "color": "#FF8916",
            },
            "DUPLICATE_SAME_LINE": {
                "msg": self.env._(
                    "This account is reported multiple times on the same line of the report"
                ),
                "color": "#E6A91D",
            },
            "NON_EXISTING": {
                "msg": self.env._(
                    "This account is reported in a line of the report but does not exist in the Chart of Accounts"
                ),
                "color": "#FFBF00",
            },
            "NON_LINKED": {
                "msg": self.env._(
                    "This tag is reported in a line of the report but is not linked to any account of the Chart of Accounts"
                ),
                "color": "#FFBF00",
            },
            "BAD_OPERATOR": {
                "msg": self.env._(
                    "The used operator is not supported for this expression."
                ),
                "color": "#FFBF00",
            },
        }
        if coverage_lines is None:
            coverage_lines = []
        if trie.get("children"):
            for child in trie.get("children"):
                self._get_accounts_coverage_report_coverage_lines(
                    child, trie["children"][child], coverage_lines
                )
        else:
            error = next(iter(trie["errors"])) if trie["errors"] else False
            if error and error != "NONE":
                coverage_lines.append(
                    [
                        subcode,
                        ERRORS[error]["msg"],
                        " + ".join(trie["lines"].sorted().mapped("name")),
                        ERRORS[error]["color"],
                    ]
                )
        if _debug.pipeline.enabled and not subcode:
            _debug.pipeline(
                "coverage_lines_built", report=self, lines=len(coverage_lines)
            )
        return coverage_lines

    @_debug.perf.timed
    def _generate_file_data_with_error_check(
        self, options, content_generator, generator_params, errors: dict | None = None
    ):
        if errors is None:
            errors = {}
        self.check_singleton()
        if any(error_value.get("level") == "danger" for error_value in errors.values()):
            _debug.logic("file_generation_blocked", report=self, errors=len(errors))
            raise AccountReportFileDownloadException(errors)

        content = content_generator(**generator_params)

        file_data = {
            "file_name": self.get_default_report_filename(
                options, generator_params["file_type"]
            ),
            "file_content": re.sub(r"\n\s*\n", "\n", content).encode(),
            "file_type": generator_params["file_type"],
        }

        _debug.pipeline(
            "file_data_generated",
            report=self,
            file_type=generator_params["file_type"],
            size=len(file_data["file_content"]),
            non_blocking_errors=len(errors),
        )
        if errors:
            raise AccountReportFileDownloadException(errors, file_data)

        return file_data

    def _split_line_name_for_xlsx(self, line):
        if self._get_model_info_from_id(line["id"])[0] == "account.account":
            return self.env["account.account"]._split_code_name(line["name"])
        return super()._split_line_name_for_xlsx(line)

    def _get_xlsx_printable_filters(self, options, options_to_print=None):
        filters = super()._get_xlsx_printable_filters(options, options_to_print)
        filters.append(
            (
                20,
                "journals",
                self.env._("Journals"),
                [
                    journal.get("title")
                    for journal in options.get("journals") or []
                    if journal.get("selected")
                ],
            )
        )
        filters.append(
            (
                70,
                "aml_ir_filters",
                self.env._("Filters"),
                [
                    ir_filter["name"]
                    for ir_filter in options.get("aml_ir_filters") or []
                    if ir_filter["selected"]
                ],
            )
        )
        extra_options = [
            (self.env._("With Draft Entries"), "all_entries", self.filter_show_draft),
            (
                self.env._("Unreconciled Entries"),
                "unreconciled",
                self.filter_unreconciled,
            ),
            (
                self.env._("Including Analytic Simulations"),
                "include_analytic_without_aml",
                True,
            ),
        ]
        filters.append(
            (
                80,
                None,
                self.env._("Options"),
                [
                    name
                    for name, option_key, condition in extra_options
                    if (not options_to_print or option_key in options_to_print)
                    and condition
                    and options.get(option_key)
                ],
            )
        )
        return filters

    def _get_pdf_footer_template(self) -> str:
        return "account.internal_layout"
