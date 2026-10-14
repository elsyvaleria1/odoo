import bisect
import datetime
import functools
import itertools
from collections import defaultdict
from typing import Any, Self

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, date_utils, groupby
from odoo.tools.misc import format_date

from odoo.addons.account.tools.display_types import NON_ACCOUNTABLE_DISPLAY_TYPES
from odoo.addons.account.tools.report_engines import (
    LEDGER_ENGINES,
    UNDISTR_LINE_NAME,
    AccountCodesFormulaError,
    parse_account_codes_formula,
)
from odoo.addons.report_formula.models.account_report import (
    report_option_filter_field,
)

_debug = DebugLog(__name__)


def _has_code_prefix(prefix, account) -> bool:
    return account["code"].startswith(prefix)


class AccountReport(models.Model):
    _inherit = "report.formula"

    chart_template = fields.Selection(
        selection=lambda self: self.env[
            "account.chart.template"
        ]._select_chart_template(),
        string="Chart of Accounts",
    )
    only_tax_exigible = report_option_filter_field(
        fields.Boolean, "only_tax_exigible", "Only Tax Exigible Lines"
    )
    allow_foreign_vat = report_option_filter_field(
        fields.Boolean, "allow_foreign_vat", "Allow Foreign VAT"
    )
    currency_translation = report_option_filter_field(
        fields.Selection,
        "currency_translation",
        default="cta",
        selection=[
            ("current", "Use the most recent rate at the date of the report"),
            ("cta", "Use CTA"),
        ],
    )
    filter_multi_company = report_option_filter_field(
        fields.Selection,
        "filter_multi_company",
        "Multi-Company",
        default="selector",
        selection=[
            ("selector", "Use Company Selector"),
            ("tax_units", "Use Tax Units"),
        ],
    )
    filter_show_draft = report_option_filter_field(
        fields.Boolean,
        "filter_show_draft",
        "Draft Entries",
        default=True,
    )
    filter_unreconciled = report_option_filter_field(
        fields.Boolean,
        "filter_unreconciled",
        "Unreconciled Entries",
        default=False,
    )
    filter_journals = report_option_filter_field(
        fields.Boolean, "filter_journals", "Journals"
    )
    filter_analytic = report_option_filter_field(
        fields.Boolean, "filter_analytic", "Analytic Filter"
    )
    filter_hierarchy = report_option_filter_field(
        fields.Selection,
        "filter_hierarchy",
        "Account Groups",
        default="optional",
        selection=[
            ("by_default", "Enabled by Default"),
            ("optional", "Optional"),
            ("never", "Never"),
        ],
    )
    filter_account_type = report_option_filter_field(
        fields.Selection,
        "filter_account_type",
        "Account Types",
        default="disabled",
        selection=[
            ("both", "Payable and receivable"),
            ("payable", "Payable"),
            ("receivable", "Receivable"),
            ("disabled", "Disabled"),
        ],
    )
    filter_partner = report_option_filter_field(
        fields.Boolean, "filter_partner", "Partners"
    )
    filter_aml_ir_filters = report_option_filter_field(
        fields.Boolean,
        "filter_aml_ir_filters",
        "Favorite Filters",
        help="If activated, user-defined filters on journal items can be selected on this report",
    )
    filter_budgets = report_option_filter_field(
        fields.Boolean, "filter_budgets", "Budgets"
    )
    default_opening_date_filter = fields.Selection(
        selection_add=[
            ("this_return_period", "This Return Period"),
            ("previous_return_period", "Last Return Period"),
        ],
        ondelete={
            "this_return_period": "set null",
            "previous_return_period": "set null",
        },
    )
    availability_condition = fields.Selection(
        selection_add=[
            ("country",),
            ("coa", "Chart of Accounts Matches"),
            ("always",),
        ],
        ondelete={"coa": "set always"},
    )

    @api.depends("root_report_id")
    def _compute_allow_account_audit_status_on_lines(self) -> None:
        self._compute_report_option_filter("allow_account_audit_status_on_lines")

    @api.constrains("availability_condition", "chart_template")
    def _check_availability_condition_chart_template(self) -> None:
        for record in self:
            if record.availability_condition == "coa" and not record.chart_template:
                raise ValidationError(
                    self.env._(
                        "The Availability is set to 'Chart of Accounts Matches' but the field Chart of Accounts is not set."
                    )
                )

    @_debug.perf.timed
    def _move_tax_tags_to_country(self, country_id) -> None:
        moving_reports = self.filtered(lambda x: x.country_id.id != country_id)
        tax_tags_expressions = moving_reports.line_ids.expression_ids.filtered(
            lambda x: x.engine == "tax_tags"
        )
        if not tax_tags_expressions:
            _debug.logic(
                "tag_move_skipped", report=self, reason="no_tax_tags_expressions"
            )
            return

        tag_model = self.env["account.account.tag"].with_context(
            active_test=False, lang="en_US"
        )
        source_tags = tax_tags_expressions._get_matching_tags()
        if not source_tags:
            _debug.logic("tag_move_skipped", report=self, reason="no_matching_tags")
            return

        reports_by_tag = defaultdict(self.env["report.formula"].browse)
        for expression in source_tags._get_related_tax_report_expressions():
            reports_by_tag[expression._tax_tag_key()] |= (
                expression.report_line_id.report_id
            )

        destination_names = set(
            tag_model.search(
                [
                    ("applicability", "=", "taxes"),
                    ("country_id", "=", country_id),
                    ("name", "in", source_tags.mapped("name")),
                ]
            ).mapped("name")
        )

        tags_to_move = tag_model.browse()
        for tag in source_tags:
            users = reports_by_tag[(tag.name, tag.country_id.id)]
            if tag.name not in destination_names and users <= moving_reports:
                tags_to_move += tag
        _debug.logic(
            "tags_partitioned",
            report=self,
            country_id=country_id,
            source_tags=source_tags,
            destination_names=len(destination_names),
            tags_to_move=tags_to_move,
        )
        tags_to_move.write({"country_id": country_id})

        missing_names = (
            set(source_tags.mapped("name"))
            - destination_names
            - set(tags_to_move.mapped("name"))
        )
        expression_model = self.env["report.formula.expression"]
        _debug.pipeline(
            "missing_tags_creating",
            report=self,
            country_id=country_id,
            missing_names=len(missing_names),
        )
        tag_model.create(
            [
                tag_vals
                for name in sorted(missing_names)
                for tag_vals in expression_model._prepare_tag_vals(name, country_id)
            ]
        )

    horizontal_group_ids = fields.Many2many(
        comodel_name="account.report.horizontal.group",
        string="Horizontal Groups",
    )
    return_type_ids = fields.One2many(
        comodel_name="account.return.type",
        inverse_name="report_id",
        string="Return Types",
    )

    is_account_coverage_report_available = fields.Boolean(
        compute="_compute_is_account_coverage_report_available"
    )

    send_and_print_values = fields.Json(copy=False)

    allow_account_audit_status_on_lines = fields.Boolean(
        compute="_compute_allow_account_audit_status_on_lines",
        precompute=True,
        store=True,
        readonly=False,
    )

    @_debug.perf.timed
    def unlink(self):
        _debug.lifecycle("unlink", unlink=self)
        for report in self:
            action, menuitem = report._get_existing_menuitem()
            menuitem.unlink()
            action.unlink()
        return super().unlink()

    @_debug.perf.timed
    def write(self, vals):
        _debug.lifecycle("write", records=self, fields=sorted(vals))
        if "active" in vals:
            reports = {r.id: r.name for r in self}
            actions = (
                self.env["ir.actions.client"]
                .sudo()
                .search(
                    [
                        ("name", "in", list(reports.values())),
                        ("tag", "=", "account_report"),
                    ]
                )
                .filtered(
                    lambda act: (
                        (
                            self.env["ir.actions.actions"]
                            ._eval_action_context(act.context)
                            .get("report_id"),
                            act.name,
                        )
                        in reports.items()
                    )
                )
            )
            self.env["ir.ui.menu"].sudo().search(
                [
                    ("active", "=", not vals["active"]),
                    (
                        "action",
                        "in",
                        [f"ir.actions.client,{action.id}" for action in actions],
                    ),
                ]
            ).active = vals["active"]
            _debug.logic(
                "menus_active_synced",
                records=self,
                actions=actions,
                active=vals.get("active"),
            )
        if "country_id" in vals:
            self._move_tax_tags_to_country(vals["country_id"])
        return super().write(vals)

    @api.model_create_multi
    @_debug.perf.timed
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                model=self._name,
                count=len(vals_list),
                fields=sorted({key for vals in vals_list for key in vals}),
            )
        reports = super().create(vals_list)

        reports_by_impacted_field = {}
        for report, impacted_fields in zip(reports, vals_list, strict=False):
            for field_name in impacted_fields:
                reports_by_impacted_field.setdefault(
                    field_name, self.env["report.formula"]
                )
                reports_by_impacted_field[field_name] += report

        if root_annual_statements := self.env.ref(
            "account.annual_statements", raise_if_not_found=False
        ):
            asr_section_reports = reports.filtered_domain(
                self._get_domain_asr_sections(root_annual_statements)
            )
            _debug.logic(
                "asr_sections_detected",
                reports=reports,
                asr_section_reports=asr_section_reports,
            )

            if asr_section_reports:
                for name, field in asr_section_reports._fields.items():
                    if (
                        field._depends
                        and "section_main_report_ids" in field._depends
                        and field.store
                    ):
                        reports_to_recompute = reports - reports_by_impacted_field.get(
                            name, self.env["report.formula"]
                        )
                        if reports_to_recompute:
                            _debug.logic(
                                "asr_filter_recomputed",
                                field=name,
                                reports=reports_to_recompute,
                            )
                            self.env.add_to_compute(field, reports_to_recompute)
                            reports_to_recompute._recompute_field(field)

            asr_section_reports._link_annual_statements(root_annual_statements)
        return reports

    def _get_domain_asr_sections(self, root_annual_statements) -> list:
        return [
            ("root_report_id", "in", root_annual_statements.section_report_ids.ids),
            (
                "availability_condition",
                "!=",
                "always",
            ),
        ]

    @_debug.perf.timed
    def _link_annual_statements(self, root_annual_statements) -> None:
        Report = self.env["report.formula"].with_context(active_test=False)
        existing_statements = Report.search(
            [
                ("root_report_id", "=", root_annual_statements.id),
                ("country_id", "in", [*self.country_id.ids, False]),
                ("chart_template", "in", list(set(self.mapped("chart_template")))),
            ]
        ).grouped(lambda report: (report.country_id, report.chart_template))
        for asr_section_report in self:
            annual_statements = existing_statements.get(
                (asr_section_report.country_id, asr_section_report.chart_template),
                self.env["report.formula"],
            )
            if not annual_statements:
                annual_statements = Report.create(
                    {
                        "name": self.env._("Annual Statements"),
                        "root_report_id": root_annual_statements.id,
                        "country_id": asr_section_report.country_id.id,
                        "use_sections": True,
                        "chart_template": asr_section_report.chart_template,
                        "availability_condition": asr_section_report.availability_condition,
                        "section_report_ids": [
                            Command.set(root_annual_statements.section_report_ids.ids)
                        ],
                    }
                )
                _debug.logic(
                    "annual_statements_created",
                    report=asr_section_report,
                    annual_statements=annual_statements,
                )

            annual_statements.section_report_ids -= asr_section_report.root_report_id

            if asr_section_report.use_sections:
                annual_statements.section_report_ids += (
                    asr_section_report.section_report_ids
                )
            else:
                annual_statements.section_report_ids += asr_section_report
                asr_section_report.sequence = asr_section_report.root_report_id.sequence
            _debug.logic(
                "annual_statements_linked",
                report=asr_section_report,
                annual_statements=annual_statements,
                use_sections=asr_section_report.use_sections,
            )

    ACCOUNT_TYPE_FILTER_DOMAINS = {
        "trade_receivable": (False, "asset_receivable"),
        "trade_payable": (False, "liability_payable"),
        "non_trade_receivable": (True, "asset_receivable"),
        "non_trade_payable": (True, "liability_payable"),
    }

    @_debug.perf.timed
    def _init_options_journals(
        self, options, previous_options, additional_journals_domain=None
    ) -> None:
        def option_value(value, selected=False, group_journals=None):
            result = {
                "id": value.id,
                "model": value._name,
                "name": value.display_name,
                "selected": selected,
            }

            if value._name == "account.journal.group":
                result.update(
                    {
                        "title": value.display_name,
                        "journals": group_journals.ids,
                        "journal_types": sorted(set(group_journals.mapped("type"))),
                    }
                )
            elif value._name == "account.journal":
                result.update(
                    {
                        "title": f"{value.name} - {value.code}",
                        "type": value.type,
                        "visible": True,
                    }
                )

            return result

        if not self.filter_journals:
            _debug.logic("journals_skipped", report=self, reason="filter_disabled")
            return

        previous_journals = previous_options.get("journals", [])
        previous_journal_group_action = previous_options.get(
            "__journal_group_action", {}
        )

        all_journals = self._get_filter_journals(
            options, additional_domain=additional_journals_domain
        )
        all_journal_groups = self._get_filter_journal_groups(options)

        options["journals"] = []
        options["selected_journal_groups"] = {}

        groups_journals_selected = set()
        options_journal_groups = []

        is_opening_report = previous_options.get("is_opening_report")

        for group in all_journal_groups:
            group_journals = all_journals - group.excluded_journal_ids
            if group.company_id:
                company_domain = self.env[
                    "account.journal"
                ]._get_domain_company_compatible(group.company_id)
                group_journals = group_journals.filtered_domain(company_domain)

            selected = (
                group.id == previous_journal_group_action.get("id")
                and previous_journal_group_action.get("action") == "add"
            )

            group_option = option_value(
                group, selected=selected, group_journals=group_journals
            )
            options_journal_groups.append(group_option)

            if selected:
                options["selected_journal_groups"] = group_option
                groups_journals_selected |= set(group_journals.ids)

        previous_selected_journals_ids = {
            journal["id"]
            for journal in previous_journals
            if journal.get("model") == "account.journal" and journal.get("selected")
        }

        company_journals_map = defaultdict(list)
        journals_selected = set()

        for journal in all_journals:
            selected = False

            if journal.id in groups_journals_selected:
                selected = True

            elif (
                not options["selected_journal_groups"]
                and previous_journal_group_action.get("action") != "remove"
            ):
                if journal.id in previous_selected_journals_ids:
                    selected = True

            if selected:
                journals_selected.add(journal.id)

            company_journals_map[journal.company_id].append(
                option_value(journal, selected=journal.id in journals_selected)
            )

        if journals_selected and not options["selected_journal_groups"]:
            for group in options_journal_groups:
                if journals_selected == set(group["journals"]):
                    group["selected"] = True
                    options["selected_journal_groups"] = group
                    break

        if (
            journals_selected == set(all_journals.ids)
            and not options["selected_journal_groups"]
        ):
            for journals in company_journals_map.values():
                for journal in journals:
                    journal["selected"] = False

        if all_journal_groups:
            options["journals"] = [
                {
                    "id": "divider",
                    "name": self.env._("Multi-ledger"),
                    "model": "account.journal.group",
                }
            ] + options_journal_groups

        _debug.pipeline(
            "journals_selected",
            report=self,
            journals=len(all_journals),
            groups=len(all_journal_groups),
            selected=len(journals_selected),
            group_selected=bool(options["selected_journal_groups"]),
            is_opening_report=is_opening_report,
            companies=len(company_journals_map),
        )
        if not company_journals_map:
            options["name_journal_group"] = self.env._("No Journal")
            return

        _debug.logic(
            "journals_layout_chosen",
            report=self,
            per_company=len(company_journals_map) > 1 or bool(all_journal_groups),
        )
        if len(company_journals_map) > 1 or all_journal_groups:
            for company, journals in company_journals_map.items():
                company_name = company.sudo().display_name

                unfolded = (
                    False
                    if is_opening_report
                    else next(
                        (
                            entry.get("unfolded")
                            for entry in previous_journals
                            if entry["model"] == "res.company"
                            and entry["name"] == company_name
                        ),
                        False,
                    )
                )

                for journal in journals:
                    journal["visible"] = unfolded

                options["journals"].append(
                    {
                        "id": "divider",
                        "model": "res.company",
                        "name": company_name,
                        "unfolded": unfolded,
                    }
                )

                options["journals"] += journals

        else:
            options["journals"].extend(next(iter(company_journals_map.values()), []))

    def _init_options_audit(self, options, previous_options) -> None:
        if not self.allow_account_audit_status_on_lines:
            return

        main_company = self._get_sender_company_for_export(options)

        date_from = options["date"]["date_from"]
        audit_return = self.env["account.return"].search_read(
            [
                ("return_type_category", "=", "audit"),
                ("company_id", "=", main_company.id),
                ("date_to", "=", options["date"]["date_to"]),
                ("date_from", "=", date_from)
                if date_from
                else ("date_from", "!=", False),
            ],
            limit=1,
            fields=["id"],
        )

        options.setdefault("audit", {})
        options["audit"]["id"] = (
            audit_return[0]["id"] if len(audit_return) > 0 else False
        )

    @_debug.perf.timed
    def _init_options_journals_names(
        self, options, previous_options, additional_journals_domain=None
    ) -> None:
        all_journals = [
            journal
            for journal in options.get("journals", [])
            if journal["model"] == "account.journal"
        ]
        journals_selected = [j for j in all_journals if j.get("selected")]
        if options.get("selected_journal_groups"):
            names_to_display = [options["selected_journal_groups"]["name"]]
        elif len(all_journals) == len(journals_selected) or not journals_selected:
            names_to_display = [self.env._("All Journals")]
        else:
            names_to_display = []
            for journal in options["journals"]:
                if journal.get("model") == "account.journal" and journal["selected"]:
                    names_to_display += [journal["name"]]

        max_nb_journals_displayed = 5
        nb_remaining = len(names_to_display) - max_nb_journals_displayed
        _debug.logic(
            "journal_names_chosen",
            report=self,
            from_group=bool(options.get("selected_journal_groups")),
            journals=len(all_journals),
            selected=len(journals_selected),
            remaining=nb_remaining,
        )
        displayed_names = ", ".join(names_to_display[:max_nb_journals_displayed])
        if nb_remaining == 1:
            options["name_journal_group"] = self.env._(
                "%(names)s and one other", names=displayed_names
            )
        elif nb_remaining > 1:
            options["name_journal_group"] = self.env._(
                "%(names)s and %(remaining)s others",
                names=displayed_names,
                remaining=nb_remaining,
            )
        else:
            options["name_journal_group"] = displayed_names

    @api.model
    def _get_options_journals(self, options):
        selected_journals = [
            journal
            for journal in options.get("journals", [])
            if journal["model"] == "account.journal" and journal["selected"]
        ]
        if not selected_journals:
            selected_journals = [
                journal
                for journal in options.get("journals", [])
                if journal["model"] == "account.journal"
            ]
        return selected_journals

    @api.model
    def _get_domain_options_journals(self, options):
        selected_journals = self._get_options_journals(options)
        domain = (
            Domain("journal_id", "in", [j["id"] for j in selected_journals])
            if selected_journals
            else Domain.TRUE
        )
        if options.get("include_analytic_without_aml"):
            domain |= Domain("journal_id", "=", False)
        return domain

    def _init_options_aml_ir_filters(self, options, previous_options) -> None:
        options["aml_ir_filters"] = []
        if not self.filter_aml_ir_filters:
            _debug.logic(
                "aml_ir_filters_skipped", report=self, reason="filter_disabled"
            )
            return

        ir_filters = self.env["ir.filters"].search(
            [("model_id", "=", "account.move.line")]
        )
        if not ir_filters:
            _debug.logic("aml_ir_filters_empty", report=self)
            return

        aml_ir_filters = [
            {"id": x.id, "name": x.name, "selected": False} for x in ir_filters
        ]
        previous_options_aml_ir_filters = previous_options.get("aml_ir_filters", [])
        previous_options_filters_map = {
            filter_item["id"]: filter_item
            for filter_item in previous_options_aml_ir_filters
        }

        for filter_item in aml_ir_filters:
            if filter_item["id"] in previous_options_filters_map:
                filter_item["selected"] = previous_options_filters_map[
                    filter_item["id"]
                ]["selected"]

        options["aml_ir_filters"] = aml_ir_filters
        _debug.pipeline(
            "aml_ir_filters_built",
            report=self,
            filters=len(aml_ir_filters),
            previous=len(previous_options_filters_map),
        )

    @api.model
    def _get_options_aml_ir_filters(self, options):
        selected_filters_ids = [
            filter_item["id"]
            for filter_item in options.get("aml_ir_filters", [])
            if filter_item["selected"]
        ]

        if not selected_filters_ids:
            return Domain.TRUE

        selected_ir_filters = self.env["ir.filters"].browse(selected_filters_ids)
        return Domain.OR(
            filter_record._get_domain_evaluated()
            for filter_record in selected_ir_filters
        )

    @_debug.perf.timed
    def _init_options_return_periodicity(self, options, previous_options) -> None:
        if not self._reads_ledger():
            return
        if (
            previous_options.get("return_periodicity")
            and previous_options["return_periodicity"].get("return_type_id")
            and previous_options["return_periodicity"].get("report_id")
            in (False, self.id, options["sections_source_id"])
        ):
            options["return_periodicity"] = {
                **previous_options["return_periodicity"],
                "report_id": self.id,
            }
            if "selected_return_country_id" in previous_options:
                options["return_periodicity"]["country_id"] = previous_options[
                    "selected_return_country_id"
                ]
            _debug.logic(
                "return_periodicity_kept",
                report=self,
                return_type_id=options["return_periodicity"].get("return_type_id"),
            )
        elif (
            len(
                return_type := self.env["report.formula"]
                .browse(options["sections_source_id"])
                .return_type_ids
            )
            == 1
            or "selected_return_type_id" in previous_options
        ):
            if len(return_type) > 1:
                return_type = self.env["account.return.type"].browse(
                    previous_options["selected_return_type_id"]
                )

            main_company = self.env.company
            start_day, start_month = return_type._get_start_date_elements(main_company)
            options["return_periodicity"] = {
                "periodicity": return_type._get_periodicity(main_company),
                "months_per_period": return_type._get_periodicity_months_delay(
                    main_company
                ),
                "start_day": start_day,
                "start_month": start_month,
                "return_type_id": return_type.id,
                "report_id": self.id,
            }
            if return_country_id := previous_options.get("selected_return_country_id"):
                options["return_periodicity"]["country_id"] = return_country_id
            _debug.logic(
                "return_periodicity_from_type",
                report=self,
                return_type=return_type,
                months_per_period=options["return_periodicity"]["months_per_period"],
            )

    def _init_options_analytic(self, options, previous_options) -> None:
        if not self.filter_analytic:
            return

        if self.env.user.has_group("analytic.group_analytic_accounting"):
            previous_analytic_accounts = previous_options.get("analytic_accounts", [])
            analytic_account_ids = [int(x) for x in previous_analytic_accounts]
            selected_analytic_accounts = (
                self.env["account.analytic.account"]
                .with_context(active_test=False)
                .search([("id", "in", analytic_account_ids)])
            )

            options["display_analytic"] = True
            options["analytic_accounts"] = selected_analytic_accounts.ids
            options["selected_analytic_account_names"] = (
                selected_analytic_accounts.mapped("name")
            )
            _debug.pipeline(
                "analytic_accounts_selected",
                report=self,
                requested=len(analytic_account_ids),
                accounts=selected_analytic_accounts,
            )

    def _init_options_partner(self, options, previous_options) -> None:
        if not self.filter_partner:
            return

        options["partner"] = True
        previous_partner_ids = previous_options.get("partner_ids") or []
        options["partner_categories"] = previous_options.get("partner_categories") or []

        selected_partner_ids = [int(partner) for partner in previous_partner_ids]
        selected_partners = (
            selected_partner_ids
            and self.env["res.partner"]
            .with_context(active_test=False)
            .search([("id", "in", selected_partner_ids)])
        ) or self.env["res.partner"]
        options["selected_partner_ids"] = selected_partners.mapped("display_name")
        options["partner_ids"] = selected_partners.ids

        selected_partner_tag_ids = [
            int(category) for category in options["partner_categories"]
        ]
        selected_partner_categories = (
            selected_partner_tag_ids
            and self.env["res.partner.tag"].browse(selected_partner_tag_ids)
        ) or self.env["res.partner.tag"]
        options["selected_partner_categories"] = selected_partner_categories.mapped(
            "name"
        )

    @api.model
    def _get_domain_options_partner(self, options):
        domains = []
        if options.get("partner_ids"):
            partner_ids = [int(partner) for partner in options["partner_ids"]]
            domains.append(Domain("partner_id", "in", partner_ids))
        if options.get("partner_categories"):
            partner_tag_ids = [
                int(category) for category in options["partner_categories"]
            ]
            domains.append(Domain("partner_id.tag_ids", "in", partner_tag_ids))
        return Domain.AND(domains)

    @api.model
    def _get_domain_options_all_entries(self, options):
        if not options.get("all_entries"):
            return Domain("parent_state", "=", "posted")
        else:
            return Domain("parent_state", "!=", "cancel")

    def _init_options_reconciled(self, options, previous_options) -> None:
        if self.filter_unreconciled:
            options["unreconciled"] = previous_options.get("unreconciled", False)
        else:
            options["unreconciled"] = False

    @api.model
    def _get_domain_options_unreconciled(self, options):
        if options.get("unreconciled"):
            return Domain("full_reconcile_id", "=", False) & Domain(
                "balance", "!=", "0"
            )
        return Domain.TRUE

    @_debug.perf.timed
    def _init_options_account_type(self, options, previous_options) -> None:
        if self.filter_account_type in ("disabled", False):
            _debug.logic("account_type_skipped", report=self, reason="filter_disabled")
            return

        account_type_list = [
            {
                "id": "trade_receivable",
                "name": self.env._("Receivable"),
                "selected": True,
            },
            {
                "id": "non_trade_receivable",
                "name": self.env._("Non Trade Receivable"),
                "selected": False,
            },
            {"id": "trade_payable", "name": self.env._("Payable"), "selected": True},
            {
                "id": "non_trade_payable",
                "name": self.env._("Non Trade Payable"),
                "selected": False,
            },
        ]

        if self.filter_account_type == "receivable":
            options["account_type"] = account_type_list[:2]
        elif self.filter_account_type == "payable":
            options["account_type"] = account_type_list[2:]
        else:
            options["account_type"] = account_type_list

        _debug.logic(
            "account_type_scope_chosen",
            report=self,
            filter=self.filter_account_type,
            choices=len(options["account_type"]),
            from_previous=bool(previous_options.get("account_type")),
        )
        if previous_options.get("account_type"):
            previously_selected_ids = {
                x["id"] for x in previous_options["account_type"] if x.get("selected")
            }
            for opt in options["account_type"]:
                opt["selected"] = opt["id"] in previously_selected_ids

    @api.model
    def _get_domain_options_account_type(self, options):
        all_domains = []
        selected_domains = []
        for opt in options.get("account_type") or []:
            account_type_filter = self.ACCOUNT_TYPE_FILTER_DOMAINS.get(opt["id"])
            if not account_type_filter:
                continue
            non_trade, account_type = account_type_filter
            domain = [
                ("account_id.non_trade", "=", non_trade),
                ("account_id.account_type", "=", account_type),
            ]
            if opt.get("selected"):
                selected_domains.append(domain)
            all_domains.append(domain)
        _debug.logic(
            "account_type_domain",
            selected=len(selected_domains),
            available=len(all_domains),
        )
        if not all_domains:
            return Domain.TRUE
        return Domain.OR(selected_domains or all_domains)

    def _init_options_hierarchy(self, options, previous_options) -> None:
        if not self._reads_ledger():
            return
        company_ids = self.get_report_company_ids(options)
        if self.filter_hierarchy != "never" and self.env["account.group"].search_count(
            self.env["account.group"]._get_domain_company_compatible(company_ids),
            limit=1,
        ):
            options["display_hierarchy_filter"] = True
            if "hierarchy" in previous_options:
                options["hierarchy"] = previous_options["hierarchy"]
            else:
                options["hierarchy"] = self.filter_hierarchy == "by_default"
        else:
            options["hierarchy"] = False
            options["display_hierarchy_filter"] = False

    @_debug.perf.timed
    def _multi_company_tax_units_init_options(self, options, previous_options):
        available_tax_units = self.env.company._get_available_tax_units(
            self,
            country=self.env["res.country"].browse(
                previous_options.get("selected_return_country_id")
            ),
        )

        available_tax_units = available_tax_units.filtered(
            lambda x: all(
                unit_company in self.env.user.company_ids
                for unit_company in x.sudo().company_ids
            )
        )

        options["available_tax_units"] = [
            {
                "id": tax_unit.id,
                "name": tax_unit.name,
                "company_ids": tax_unit.company_ids.ids,
            }
            for tax_unit in available_tax_units
        ]

        companies_authorized_tax_unit_opt = {
            *(
                available_tax_units.filtered(
                    lambda x: set(self.env.companies) == set(x.company_ids)
                ).ids
            ),
            "company_only",
        }

        if previous_options.get("tax_unit") in companies_authorized_tax_unit_opt:
            options["tax_unit"] = previous_options["tax_unit"]

        elif companies_authorized_tax_unit_opt == {"company_only"}:
            options["tax_unit"] = "company_only"
        elif (
            len(available_tax_units) == 1
            and available_tax_units[0].id in companies_authorized_tax_unit_opt
        ):
            options["tax_unit"] = available_tax_units[0].id
        else:
            options["tax_unit"] = "company_only"

        _debug.logic(
            "tax_unit_chosen",
            report=self,
            tax_unit=options["tax_unit"],
            previous_tax_unit=previous_options.get("tax_unit"),
            available=len(available_tax_units),
            authorized=len(companies_authorized_tax_unit_opt),
        )
        if options["tax_unit"] == "company_only":
            companies = self.env.company._get_branches_with_same_vat(
                accessible_only=True
            )
        else:
            tax_unit = available_tax_units.filtered(
                lambda x: x.id == options["tax_unit"]
            )
            companies = tax_unit.company_ids

        _debug.pipeline("tax_unit_companies", report=self, companies=companies)
        return companies

    @_debug.perf.timed
    def _init_options_currency_table(self, options, previous_options) -> None:
        companies = self.env["res.company"].browse(self.get_report_company_ids(options))
        table_type = (
            "monocurrency"
            if self.env["res.currency"]._is_currency_table_monocurrency(companies)
            else self.currency_translation
        )

        periods = {}
        for col_group in options["column_groups"].values():
            if col_group["forced_options"].get("no_impact_on_currency_table"):
                continue

            col_group_date = col_group["forced_options"].get("date", options["date"])

            col_group_date_from = (
                col_group_date["date_from"]
                if col_group_date["mode"] == "range"
                else None
            )
            col_group_date_to = col_group_date["date_to"]
            period_key = col_group_date["currency_table_period_key"]

            already_present_period = periods.get(period_key)
            if already_present_period:
                if (
                    col_group_date_from
                    and already_present_period["from"] > col_group_date_from
                ):
                    already_present_period["from"] = col_group_date_from

                already_present_period["to"] = max(
                    already_present_period["to"], col_group_date_to
                )
            else:
                periods[period_key] = {
                    "from": col_group_date_from,
                    "to": col_group_date_to,
                }

        options["currency_table"] = {"type": table_type, "periods": periods}
        _debug.logic(
            "currency_table_chosen",
            report=self,
            table_type=table_type,
            companies=companies,
            column_groups=len(options["column_groups"]),
            periods=len(periods),
        )

    def _init_options_all_entries(self, options, previous_options) -> None:
        if self.filter_show_draft:
            options["all_entries"] = previous_options.get("all_entries", False)
        else:
            options["all_entries"] = False

    def _init_options_budgets(self, options, previous_options) -> None:
        if self.filter_budgets:
            previous_selection = {
                budget_option["id"]
                for budget_option in previous_options.get("budgets", [])
                if budget_option.get("selected")
            }

            options["budgets"] = [
                {
                    "id": budget.id,
                    "name": budget.name,
                    "selected": budget.id in previous_selection,
                    "company_id": budget.company_id.id,
                }
                for budget in self.env["account.report.budget"].search(
                    [("company_id", "in", self.env.companies.ids)]
                )
            ]
            options["show_all_accounts"] = (
                previous_options.get("show_all_accounts") or False
            )

    def _init_options_readonly_query(self, options, previous_options) -> None:
        options["readonly_query"] = options["currency_table"]["type"] == "monocurrency"

    def _init_options_user_groups(self, options, previous_options) -> None:
        options["user_groups"] = {
            "analytic_accounting": self.env.user.has_group(
                "analytic.group_analytic_accounting"
            ),
            "account_readonly": self.env.user.has_group(
                "account.group_account_readonly"
            ),
            "account_user": self.env.user.has_group("account.group_account_user"),
        }

    def _get_source_domains(self, options, date_scope):
        if not self._reads_ledger():
            return super()._get_source_domains(options, date_scope)
        domains = [
            Domain("display_type", "not in", NON_ACCOUNTABLE_DISPLAY_TYPES),
            self._get_domain_options_journals(options)
            if not options.get("compute_budget")
            else Domain.TRUE,
            self._get_domain_options_partner(options),
            self._get_domain_options_all_entries(options),
            self._get_domain_options_unreconciled(options),
            self._get_domain_options_account_type(options),
            self._get_options_aml_ir_filters(options),
            self.env["account.move.line"]._get_domain_tax_exigible()
            if self.only_tax_exigible
            else Domain.TRUE,
        ]
        _debug.pipeline(
            "domain_options_built",
            report=self,
            date_scope=date_scope,
            journals_filtered=not options.get("compute_budget"),
            tax_exigible_only=self.only_tax_exigible,
            forced_domain=bool(options.get("forced_domain")),
            foreign_vat=self.allow_foreign_vat,
        )

        if self.allow_foreign_vat:
            country = self._get_tax_filing_country(options)
            if country == self.env.company.tax_config_id.account_fiscal_country_id:
                _debug.logic(
                    "foreign_vat_scope", report=self, scope="domestic", country=country
                )
                domains.append(
                    [
                        "|",
                        "|",
                        "|",
                        ("move_id.fiscal_position_id", "=", False),
                        ("move_id.fiscal_position_id.foreign_vat", "=", False),
                        ("move_id.fiscal_position_id.country_id", "=", country.id),
                        ("tax_tag_ids.country_id", "=", country.id),
                    ]
                )
            elif country:
                _debug.logic(
                    "foreign_vat_scope", report=self, scope="foreign", country=country
                )
                domains.append(
                    [
                        "|",
                        ("tax_tag_ids.country_id", "=", country.id),
                        "&",
                        ("move_id.fiscal_position_id.country_id", "=", country.id),
                        ("move_id.fiscal_position_id.foreign_vat", "!=", False),
                    ]
                )

        return domains

    def _get_tax_filing_country(self, options):
        return_periodicity = options.get("return_periodicity") or {}
        return (
            self.country_id
            or self.env["res.country"].browse(return_periodicity.get("country_id"))
            or self.env["account.return.type"]
            .browse(return_periodicity.get("return_type_id"))
            .country_id
        )

    def _get_filter_journals(self, options, additional_domain=None):
        return (
            self.env["account.journal"]
            .with_context(active_test=False)
            .search(
                [
                    *self.env["account.journal"]._get_domain_company_compatible(
                        self.get_report_company_ids(options)
                    ),
                    *(additional_domain or []),
                ],
                order="company_id, name",
            )
        )

    def _get_filter_journal_groups(self, options):
        return self.env["account.journal.group"].search(
            [
                *self.env["account.journal.group"]._get_domain_company_compatible(
                    self.get_report_company_ids(options)
                ),
            ],
            order="sequence",
        )

    def _apply_branch_rules_to_buttons(self, options) -> None:
        if not self._reads_ledger():
            super()._apply_branch_rules_to_buttons(options)
            return
        options_companies = self.env["res.company"].browse(
            self.get_report_company_ids(options)
        )
        if options.get("enable_export_buttons_for_common_vat_in_branches"):
            report_accepted_company_ids = set(options_companies.ids)
            same_vat_branch_ids = set(
                self.env.company._get_branches_with_same_vat().ids
            )
            if report_accepted_company_ids == same_vat_branch_ids:
                options["buttons"] = [
                    {**button, "branch_allowed": button.get("branch_allowed", True)}
                    for button in options["buttons"]
                ]

        if not options_companies._is_every_branch_selected():
            for button in filter(
                lambda x: not x.get("branch_allowed"), options["buttons"]
            ):
                button["error_action"] = "show_error_branch_allowed"

    def _get_options_companies(self, options, previous_options):
        if self.filter_multi_company == "tax_units":
            return self._multi_company_tax_units_init_options(
                options, previous_options=previous_options
            )
        return super()._get_options_companies(options, previous_options)

    def _init_options_filters(self, options, previous_options) -> None:
        super()._init_options_filters(options, previous_options)
        options["filters"]["show_draft"] = self.filter_show_draft
        options["filters"]["show_unreconciled"] = self.filter_unreconciled

    def _normalize_date_filter(self, options, options_filter, period_date_to):
        if "return_period" in options_filter and not options.get("return_periodicity"):
            _debug.logic("return_period_fallback", report=self, filter=options_filter)
            options_filter = "this_month"
        elif "return_period" in options_filter:
            months_per_period = options["return_periodicity"]["months_per_period"]
            start_day = options["return_periodicity"]["start_day"]
            start_month = options["return_periodicity"]["start_month"]

            if (
                "fy_start_day" not in options["return_periodicity"]
                or "fy_start_month" not in options["return_periodicity"]
            ):
                fy_start = self._get_year_bounds(
                    fields.Date.from_string(period_date_to)
                    if period_date_to
                    else fields.Date.context_today(self)
                )["date_from"]
                options["return_periodicity"]["fy_start_day"] = fy_start.day
                options["return_periodicity"]["fy_start_month"] = fy_start.month

            if start_day == 1 and start_month == 1 and months_per_period in (1, 3):
                match months_per_period:
                    case 1:
                        options_filter = (
                            "custom_month" if period_date_to else "previous_month"
                        )
                    case 3:
                        options_filter = (
                            "custom_quarter" if period_date_to else "previous_quarter"
                        )
            elif (
                start_day == options["return_periodicity"]["fy_start_day"]
                and start_month == options["return_periodicity"]["fy_start_month"]
                and months_per_period == 12
            ):
                options_filter = "custom_year" if period_date_to else "previous_year"
            else:
                options["return_periodicity"]["is_filter_visible"] = True
        return options_filter

    def _get_custom_period_bounds(
        self, options, options_filter, period_date_from, period_date_to, current
    ):
        if "return_period" not in options_filter:
            return super()._get_custom_period_bounds(
                options, options_filter, period_date_from, period_date_to, current
            )
        if period_date_from and "custom_return_period" in options_filter:
            date_from = fields.Date.to_date(period_date_from)
            date_to = fields.Date.to_date(period_date_to)
        else:
            if "custom_return_period" in options_filter:
                base_date = fields.Date.to_date(period_date_to)
            else:
                base_date = fields.Date.context_today(self)
            return_type = self.env["account.return.type"].browse(
                options["return_periodicity"]["return_type_id"]
            )
            date_from, date_to = return_type._get_period_boundaries(
                self.env.company, base_date
            )
        period_type = "return_period"
        return date_from, date_to, period_type

    def _convert_custom_period_filter(
        self, options, options_filter, date, period_date_to, date_to
    ):
        if options_filter in {"custom_month", "custom_quarter", "custom_year"}:
            options_date = fields.Date.from_string(period_date_to)
            diff_years = options_date.year - date_to.year
            offsetted_date = options_date + relativedelta(years=diff_years)
            diff_months = offsetted_date.month - date_to.month
            diff_months += diff_years * 12

            months_per_period = options["return_periodicity"]["months_per_period"]

            if options_date > date_to:
                prefix = "next"
            elif options_date < date_to:
                prefix = "previous"
            else:
                prefix = "this"

            match months_per_period:
                case 1:
                    date["period"] = diff_months
                    options_filter = f"{prefix}_month"
                case 3:
                    date["period"] = diff_months // months_per_period
                    options_filter = f"{prefix}_quarter"
                case 12:
                    date["period"] = diff_months // months_per_period
                    options_filter = f"{prefix}_year"
        return options_filter

    def _finalize_custom_period_options(self, options, options_filter) -> None:
        if "custom_return_period" in options_filter:
            return_type = self.env["account.return.type"].browse(
                options["return_periodicity"]["return_type_id"]
            )
            current_date_to = return_type._get_period_boundaries(
                self.env.company, fields.Date.context_today(self)
            )[1]
            delta = relativedelta(
                fields.Date.from_string(options["date"]["date_to"]), current_date_to
            )
            months = delta.years * 12 + delta.months
            diffs = months // options["return_periodicity"]["months_per_period"]
            options["date"]["period"] = diffs

    def _get_custom_period_name(self, period_type, date_from, date_to, options_return):
        if period_type != "return_period" or not options_return:
            return super()._get_custom_period_name(
                period_type, date_from, date_to, options_return
            )
        day = options_return["start_day"]
        month = options_return["start_month"]
        return self.env["account.return.type"]._get_period_name(
            period_from=fields.Date.to_string(date_from),
            period_to=fields.Date.to_string(date_to),
            start_day=day,
            start_month=month,
        )

    def _get_shifted_custom_period(
        self, options, periods, return_period, period_type, mode, date_from
    ):
        if not (return_period or "return_period" in period_type):
            return super()._get_shifted_custom_period(
                options, periods, return_period, period_type, mode, date_from
            )
        month_per_period = options["return_periodicity"]["months_per_period"]
        return_type = self.env["account.return.type"].browse(
            options["return_periodicity"]["return_type_id"]
        )
        date_from, date_to = return_type._get_period_boundaries(
            self.env.company,
            date_from + relativedelta(months=month_per_period * periods),
        )
        return self._get_dates_period(
            date_from,
            date_to,
            mode,
            period_type="return_period",
            options_return=options["return_periodicity"],
        )

    def _get_custom_date_scope_bounds(
        self, options, date_scope, date_from, date_to
    ) -> tuple:
        if date_scope != "previous_return_period":
            return super()._get_custom_date_scope_bounds(
                options, date_scope, date_from, date_to
            )
        return_types = self.return_type_ids

        _debug.logic(
            "previous_return_period_scope",
            report=self,
            return_types=return_types,
        )
        if len(return_types) > 1:
            if len(set(return_types.mapped("deadline_periodicity"))) > 1:
                raise UserError(
                    self.env._(
                        "'%s' date scope cannot be evaluated for a report used by multiple return types using different periodicities.",
                        dict(
                            self.env["report.formula.expression"]
                            ._fields["date_scope"]
                            ._description_selection(self.env)
                        )["previous_return_period"],
                    )
                )
            return_types = return_types[0]

        current_period_start, _current_period_end = return_types._get_period_boundaries(
            self.env.company,
            fields.Date.from_string(options["date"]["date_from"]),
        )
        eve_of_period_start = current_period_start - relativedelta(days=1)
        date_from, date_to = return_types._get_period_boundaries(
            self.env.company, eve_of_period_start
        )
        return date_from, date_to

    def _get_variant_preferred_country(self):
        return self.env.company.tax_config_id.account_fiscal_country_id

    def _init_options_buttons(self, options, previous_options) -> None:
        super()._init_options_buttons(options, previous_options)
        if not self._reads_ledger():
            return
        if self.return_type_ids and self.env.user.has_group(
            "account.group_account_user"
        ):
            options["buttons"].append(
                {
                    "name": self.env._("Returns"),
                    "action": "action_view_returns",
                    "sequence": 110,
                    "always_show": True,
                    "branch_allowed": True,
                }
            )

    @_debug.perf.timed
    def _get_formula_batch_with_engine_tax_tags(
        self,
        options,
        date_scope,
        formulas_dict,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
        batch_ids_cache=None,
    ):
        self._check_groupby_fields(
            (next_groupby.split(",") if next_groupby else [])
            + ([current_groupby] if current_groupby else [])
        )
        all_expressions = self.env["report.formula.expression"]
        for expressions in formulas_dict.values():
            all_expressions |= expressions
        tags = all_expressions._get_matching_tags()
        _debug.pipeline(
            "tax_tags_matched",
            report=self,
            date_scope=date_scope,
            formulas=len(formulas_dict),
            expressions=len(all_expressions),
            tags=len(tags),
            groupby=current_groupby,
            offset=offset,
            limit=limit,
        )

        query = self._get_report_query(options, date_scope)
        acc_tag_name = (
            self.with_context(lang="en_US")
            .env["account.account.tag"]
            ._field_to_sql("acc_tag", "name")
        )
        sql = SQL(
            """
            SELECT
                %(acc_tag_name)s AS formula,
                SUM(%(balance_select)s) AS balance,
                COUNT(account_move_line.id) AS aml_count,
                %(groupby_sql)s AS grouping_key

            FROM %(table_references)s

            JOIN account_account_tag_account_move_line_rel aml_tag
                ON aml_tag.account_move_line_id = account_move_line.id
            JOIN account_account_tag acc_tag
                ON aml_tag.account_account_tag_id = acc_tag.id
            %(currency_table_join)s

            WHERE %(search_condition)s
              AND aml_tag.account_account_tag_id = ANY(%(tag_ids)s)

            GROUP BY 1, 4
            """,
            acc_tag_name=acc_tag_name,
            groupby_sql=self.env["account.move.line"]._field_to_sql(
                "account_move_line", current_groupby, query
            )
            if current_groupby
            else SQL("CAST(NULL AS INTEGER)"),
            table_references=query.from_clause,
            tag_ids=tags.ids,
            balance_select=self._currency_table_apply_rate(
                SQL("account_move_line.balance")
            ),
            currency_table_join=self._currency_table_aml_join(options),
            search_condition=query.where_clause,
        )
        if current_groupby and (offset or limit):
            sql = self._paginate_grouping_keys(
                sql, ("formula", "balance", "aml_count", "grouping_key"), offset, limit
            )
        else:
            sql = SQL("%s ORDER BY 4, 1", sql)

        signed_formulas_by_tag = defaultdict(list)
        for formula_str in formulas_dict:
            signed_formulas_by_tag[formula_str.lstrip("-")].append(
                (-1 if formula_str.startswith("-") else 1, formula_str)
            )
        rslt = {
            (formula_str.lstrip("-"), formula_expr): []
            if current_groupby
            else {"result": 0, "has_sublines": False}
            for formula_str, formula_expr in formulas_dict.items()
        }
        tag_rows = 0
        for tax_tag, balance, aml_count, grouping_key in self.env.execute_query(sql):
            tag_rows += 1
            for sign, formula_str in signed_formulas_by_tag[tax_tag]:
                rslt_key = (tax_tag, formulas_dict[formula_str])
                rslt_dict = {"result": sign * balance, "has_sublines": aml_count > 0}
                if current_groupby:
                    rslt[rslt_key].append((grouping_key, rslt_dict))
                else:
                    rslt[rslt_key] = rslt_dict
        _debug.perf.count("tax_tag_rows_fetched", rows=tag_rows)

        if _debug.pipeline.enabled:
            _debug.pipeline(
                "tax_tags_results",
                report=self,
                results=len(rslt),
                groups=sum(len(v) for v in rslt.values() if isinstance(v, list))
                if current_groupby
                else None,
            )
        return rslt

    @_debug.perf.timed
    def _get_formula_batch_with_engine_account_codes(
        self,
        options,
        date_scope,
        formulas_dict,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
        batch_ids_cache=None,
    ):
        self._check_groupby_fields(
            (next_groupby.split(",") if next_groupby else [])
            + ([current_groupby] if current_groupby else [])
        )
        terms_by_account_id, account_ids_by_balance_character = (
            self._map_account_codes_formulas(options, formulas_dict)
        )
        _debug.pipeline(
            "account_prefixes_mapped",
            report=self,
            date_scope=date_scope,
            groupby=current_groupby,
            formulas=len(formulas_dict),
            matched_accounts=len(terms_by_account_id),
        )

        groups_by_formula = {formula: {} for formula in formulas_dict}
        rows = self.env.execute_query(
            self._get_account_codes_query(
                options,
                date_scope,
                account_ids_by_balance_character,
                current_groupby,
                offset,
                limit,
            )
        )
        for account_id, account_sign, grouping_key, balance in rows:
            for formula, multiplicator, balance_character in terms_by_account_id[
                account_id
            ]:
                if (balance_character == "D" and account_sign < 0) or (
                    balance_character == "C" and account_sign >= 0
                ):
                    continue
                group = groups_by_formula[formula].setdefault(
                    grouping_key, {"result": 0, "has_sublines": True}
                )
                group["result"] += multiplicator * balance
        _debug.perf.count("account_codes_rows_fetched", rows=len(rows))

        rslt = {}
        for formula, groups in groups_by_formula.items():
            if current_groupby:
                result = list(groups.items())
            else:
                result = groups.get(None, {"result": 0, "has_sublines": False})
            rslt[formula, formulas_dict[formula]] = result

        _debug.pipeline("account_codes_results", report=self, results=len(rslt))
        return rslt

    def _map_account_codes_formulas(self, options, formulas) -> tuple[dict, dict]:
        prefilter = self.env["account.account"]._get_domain_company_compatible(
            self.get_report_company_ids(options)
        )

        all_accounts = (
            self.env["account.account"]
            .with_context(active_test=False)
            .search([*prefilter])
        )
        accounts = []

        for account in all_accounts:
            account_code = account.code
            if not account_code:
                for company in account.company_ids:
                    account_code = account.with_company(company).code
                    if account_code:
                        break
            accounts.append(
                {
                    "id": account.id,
                    "code": account_code,
                    "tag_ids": account.tag_ids.ids,
                }
            )

        accounts.sort(key=lambda acc: acc["code"])
        tags_map = defaultdict(list)
        for acc in accounts:
            for tag in acc["tag_ids"]:
                tags_map[tag].append(acc)

        resolve_tag = functools.cache(self._resolve_account_codes_tag)
        account_ids_by_prefix_key = {}
        prefix_details_by_formula = {}
        for formula in formulas:
            prefix_details_by_formula[formula] = []
            try:
                terms = parse_account_codes_formula(formula)
            except AccountCodesFormulaError as error:
                raise UserError(
                    self.env._(
                        "Invalid token '%(token)s' in account_codes formula '%(formula)s'",
                        token=error.token,
                        formula=formula,
                    )
                ) from None
            for term in terms:
                prefix_key = term.key
                prefix_details_by_formula[formula].append(
                    (term.sign, prefix_key, term.balance_character)
                )
                if prefix_key not in account_ids_by_prefix_key:
                    account_ids_by_prefix_key[prefix_key] = {
                        account["id"]
                        for account in self._get_account_codes_term_accounts(
                            term, accounts, tags_map, resolve_tag
                        )
                        if term.matches_account(
                            account["code"],
                            account["tag_ids"],
                            resolve_tag,
                        )
                    }

        account_ids_by_balance_character = defaultdict(set)
        terms_by_account_id = defaultdict(list)
        for formula, prefix_details in prefix_details_by_formula.items():
            for multiplicator, prefix_key, balance_character in prefix_details:
                account_ids_by_balance_character[balance_character] |= (
                    account_ids_by_prefix_key[prefix_key]
                )
                for account_id in account_ids_by_prefix_key[prefix_key]:
                    terms_by_account_id[account_id].append(
                        (formula, multiplicator, balance_character)
                    )
        return terms_by_account_id, account_ids_by_balance_character

    def _get_account_codes_term_accounts(self, term, accounts, tags_map, resolve_tag):
        if term.is_tag:
            tag_id = resolve_tag(term.tag)
            return tags_map[tag_id] if tag_id else []
        idx = bisect.bisect_left(accounts, term.prefix, key=lambda acc: acc["code"])
        return itertools.takewhile(
            functools.partial(_has_code_prefix, term.prefix),
            itertools.islice(accounts, idx, None),
        )

    def _resolve_account_codes_tag(self, tag) -> int | None:
        if tag.ref:
            model, tag_id = self.env["ir.model.data"]._xmlid_to_res_model_res_id(
                tag.ref
            )
            if model != "account.account.tag":
                tag_id = None
        else:
            tag_id = tag.id
        if not tag_id:
            _debug.logic("account_codes_tag_unresolved", report=self, tag=tag.token)
        return tag_id or None

    def _get_account_codes_query(
        self,
        options,
        date_scope,
        account_ids_by_balance_character,
        current_groupby,
        offset,
        limit,
    ) -> SQL:
        query = self._get_report_query(options, date_scope)
        groupby_sql = (
            self.env["account.move.line"]._field_to_sql(
                "account_move_line", current_groupby, query
            )
            if current_groupby
            else SQL("CAST(NULL AS INTEGER)")
        )
        contributing_rows = SQL(
            """
            SELECT account_id, account_sign, grouping_key, balance
            FROM (
                SELECT grouped.*,
                       SIGN(ROUND(CAST(SUM(grouped.balance) OVER (PARTITION BY grouped.account_id) AS NUMERIC) / CAST(%(rounding)s AS NUMERIC))) AS account_sign
                FROM (
                    SELECT account_move_line.account_id AS account_id,
                           %(groupby_sql)s AS grouping_key,
                           SUM(%(balance_select)s) AS balance
                    FROM %(table_references)s
                    %(currency_table_join)s
                    WHERE %(search_condition)s
                      AND account_move_line.account_id = ANY(%(account_ids)s)
                    GROUP BY 1, 2
                ) grouped
            ) signed
            WHERE account_id = ANY(%(unconditional_ids)s)
               OR (account_id = ANY(%(debit_ids)s) AND account_sign >= 0)
               OR (account_id = ANY(%(credit_ids)s) AND account_sign < 0)
            """,
            rounding=self.env.company.currency_id.rounding,
            groupby_sql=groupby_sql,
            balance_select=self._currency_table_apply_rate(
                SQL("account_move_line.balance")
            ),
            table_references=query.from_clause,
            currency_table_join=self._currency_table_aml_join(options),
            search_condition=query.where_clause,
            account_ids=list(set().union(*account_ids_by_balance_character.values())),
            unconditional_ids=list(account_ids_by_balance_character[""]),
            debit_ids=list(account_ids_by_balance_character["D"]),
            credit_ids=list(account_ids_by_balance_character["C"]),
        )
        columns = ("account_id", "account_sign", "grouping_key", "balance")
        if current_groupby and (offset or limit):
            return self._paginate_grouping_keys(
                contributing_rows, columns, offset, limit
            )
        return SQL("%s ORDER BY grouping_key", contributing_rows)

    def _paginate_grouping_keys(self, rows: SQL, columns, offset, limit) -> SQL:
        _debug.logic("grouping_keys_paginated", report=self, offset=offset, limit=limit)
        return SQL(
            """
            SELECT %(columns)s FROM (
                SELECT ranked.*, DENSE_RANK() OVER (ORDER BY ranked.grouping_key) AS grouping_key_rank
                FROM (%(rows)s) ranked
            ) page
            WHERE page.grouping_key_rank > %(offset)s
            %(limit_condition)s
            ORDER BY page.grouping_key
            """,
            columns=SQL(", ").join(
                SQL.identifier("page", column) for column in columns
            ),
            rows=rows,
            offset=offset or 0,
            limit_condition=SQL(
                "AND page.grouping_key_rank <= %s", (offset or 0) + limit
            )
            if limit
            else SQL(),
        )

    @_debug.perf.timed
    def _get_domain_expression_audit(self, expression_to_audit, options):
        _debug.logic(
            "audit_domain_engine",
            report=self,
            expression=expression_to_audit,
            engine=expression_to_audit.engine,
            supported=expression_to_audit.engine
            in ("account_codes", "tax_tags", "domain"),
        )
        if expression_to_audit.engine == "account_codes":
            terms_by_account_id, account_ids_by_balance_character = (
                self._map_account_codes_formulas(options, [expression_to_audit.formula])
            )
            if (
                account_ids_by_balance_character["D"]
                or account_ids_by_balance_character["C"]
            ):
                self._init_currency_table(options)
                account_ids = {
                    account_id
                    for account_id, *_row in self.env.execute_query(
                        self._get_account_codes_query(
                            options,
                            expression_to_audit.date_scope,
                            account_ids_by_balance_character,
                            None,
                            0,
                            None,
                        )
                    )
                }
            else:
                account_ids = set(terms_by_account_id)
            _debug.pipeline(
                "account_codes_audit_domain",
                expression=expression_to_audit,
                accounts=len(account_ids),
            )
            return [("account_id", "in", list(account_ids))]

        if expression_to_audit.engine == "tax_tags":
            tags = self.env["account.account.tag"]._get_tax_tags(
                expression_to_audit.formula,
                expression_to_audit.report_line_id.report_id.country_id.id,
            )
            return [("tax_tag_ids", "in", tags.ids)]

        return super()._get_domain_expression_audit(expression_to_audit, options)

    @api.model
    def _currency_table_apply_rate(self, value: SQL) -> SQL:
        if not self._reads_ledger():
            return super()._currency_table_apply_rate(value)
        return SQL(
            "(%(value)s) * COALESCE(account_currency_table.rate, 1)", value=value
        )

    @api.model
    def _get_sum_select(self, value: SQL | None) -> SQL:
        if value is None:
            return SQL("0.0")
        return SQL("COALESCE(SUM(%s), 0.0)", self._currency_table_apply_rate(value))

    @api.model
    def _get_sums_select(
        self, debit: SQL | None, credit: SQL | None, balance: SQL
    ) -> SQL:
        return SQL(
            "%s AS debit, %s AS credit, %s AS balance",
            self._get_sum_select(debit),
            self._get_sum_select(credit),
            self._get_sum_select(balance),
        )

    @api.model
    def _get_aml_sums_select(self) -> SQL:
        return self._get_sums_select(
            SQL("account_move_line.debit"),
            SQL("account_move_line.credit"),
            SQL("account_move_line.balance"),
        )

    @api.model
    @_debug.perf.timed
    def _currency_table_aml_join(self, options, aml_alias=None) -> SQL:
        if not self._reads_ledger():
            return super()._currency_table_aml_join(options, aml_alias)
        if aml_alias is None:
            aml_alias = SQL("account_move_line")
        _debug.logic(
            "currency_table_join",
            table_type=options.get("currency_table", {}).get("type"),
            period_key=options.get("date", {}).get("currency_table_period_key"),
        )
        if options["currency_table"]["type"] == "cta":
            return SQL(
                """
                JOIN account_account aml_ct_account
                    ON aml_ct_account.id = %(aml_table)s.account_id
                LEFT JOIN %(currency_table)s
                    ON %(aml_table)s.company_id = account_currency_table.company_id
                    AND (
                        account_currency_table.rate_type = CASE
                            WHEN aml_ct_account.account_type LIKE ANY (ARRAY[%(income_prefix)s, %(expense_prefix)s, 'equity_unaffected']) THEN 'average'
                            WHEN aml_ct_account.account_type LIKE %(equity_prefix)s THEN 'historical'
                            ELSE 'current'
                        END
                    )
                    AND (account_currency_table.date_from IS NULL OR account_currency_table.date_from <= %(aml_table)s.date)
                    AND (account_currency_table.date_next IS NULL OR account_currency_table.date_next > %(aml_table)s.date)
                    AND (account_currency_table.period_key = %(period_key)s OR account_currency_table.period_key IS NULL)
                """,
                aml_table=aml_alias,
                equity_prefix="equity%",
                income_prefix="income%",
                expense_prefix="expense%",
                currency_table=self._get_currency_table(options),
                period_key=options["date"]["currency_table_period_key"],
            )

        return SQL(
            """
            JOIN %(currency_table)s
                ON %(aml_table)s.company_id = account_currency_table.company_id
                AND (account_currency_table.period_key = %(period_key)s OR account_currency_table.period_key IS NULL)
            """,
            aml_table=aml_alias,
            currency_table=self._get_currency_table(options),
            period_key=options["date"]["currency_table_period_key"],
        )

    @api.model
    def _get_currency_table(self, options) -> SQL:
        if options["currency_table"]["type"] == "monocurrency":
            companies = self.env["res.company"].browse(
                self.get_report_company_ids(options)
            )
            return self.env["res.currency"]._get_monocurrency_currency_table_sql(
                companies, use_cta_rates=False
            )

        return SQL("account_currency_table")

    def _currency_table_external_value_join(self, options) -> SQL:
        if not self._reads_ledger():
            return super()._currency_table_external_value_join(options)
        return SQL(
            """
            JOIN %(currency_table)s
            ON account_currency_table.company_id = report_formula_external_value.company_id
            AND account_currency_table.rate_type = 'current'
            AND (account_currency_table.period_key = %(period_key)s OR account_currency_table.period_key IS NULL)
            """,
            currency_table=self._get_currency_table(options),
            period_key=options["date"]["currency_table_period_key"],
        )

    def _adapt_report_query_domain(self, options, domain):
        if options.get("compute_budget"):
            domain = domain.optimize(self._get_source_model())
            aml_required_columns = {
                "move_id",
                "currency_id",
                "journal_id",
                "display_type",
            }
            domain = domain.map_conditions(
                lambda condition: (
                    Domain.TRUE
                    if condition.field_expr in aml_required_columns
                    else condition
                )
            )
        return domain

    def _adapt_report_query(self, options, query) -> None:
        if options.get("compute_budget"):
            query._tables["account_move_line"] = (
                self._create_aml_shadowing_query_for_budget(options)
            )
            query.add_where(SQL("budget_id = %s", options["compute_budget"]))

    def _init_options_horizontal_groups(self, options, previous_options) -> None:
        if not self._reads_ledger():
            super()._init_options_horizontal_groups(options, previous_options)
            return
        options["available_horizontal_groups"] = [
            {
                "id": horizontal_group.id,
                "name": horizontal_group.name,
            }
            for horizontal_group in self.horizontal_group_ids
        ]
        previous_selected = previous_options.get("selected_horizontal_group_id")
        options["selected_horizontal_group_id"] = (
            previous_selected
            if previous_selected in self.horizontal_group_ids.ids
            else None
        )

    def _get_options_initializers_forced_sequence_map(self):
        return {
            **super()._get_options_initializers_forced_sequence_map(),
            "_init_options_return_periodicity": 29,
            "_init_options_journals": 80,
            "_init_options_journals_names": 90,
            "_init_options_audit": 100,
            "_init_options_hierarchy": 1030,
            "_init_options_currency_table": 1055,
            "_init_options_readonly_query": 1070,
            "_init_options_analytic_groupby": 995,
        }

    def _get_totals_below_sections(self):
        if not self._reads_ledger():
            return super()._get_totals_below_sections()
        return self.env.company.account_config_id.totals_below_sections

    def _prepare_info_popup_data(
        self,
        options,
        col_group_key,
        column_expr_label,
        target_line_res_dict,
        line_expressions_map,
    ):
        if not self._reads_ledger():
            return super()._prepare_info_popup_data(
                options,
                col_group_key,
                column_expr_label,
                target_line_res_dict,
                line_expressions_map,
            )
        info_popup_data = {}

        carryover_expr_label = "_carryover_%s" % column_expr_label
        carryover_value = target_line_res_dict.get(carryover_expr_label, {}).get(
            "value", 0
        )
        if self.env.company.currency_id.compare_amounts(0, carryover_value) != 0:
            info_popup_data["carryover"] = self._format_value(
                options, carryover_value, "monetary"
            )

            carryover_expression = line_expressions_map[carryover_expr_label]
            if carryover_expression.carryover_target:
                info_popup_data["carryover_target"] = (
                    carryover_expression._get_carryover_target_expression(
                        options
                    ).report_line_name
                )

        applied_carryover_value = target_line_res_dict.get(
            "_applied_carryover_%s" % column_expr_label, {}
        ).get("value", 0)
        if (
            self.env.company.currency_id.compare_amounts(0, applied_carryover_value)
            != 0
        ):
            info_popup_data["applied_carryover"] = self._format_value(
                options, applied_carryover_value, "monetary"
            )
            info_popup_data["allow_carryover_audit"] = self.env.user.has_group(
                "base.group_no_one"
            )
            info_popup_data["expression_id"] = line_expressions_map[
                "_applied_carryover_%s" % column_expr_label
            ]["id"]
            info_popup_data["column_group_key"] = col_group_key
        return info_popup_data

    @_debug.perf.timed
    def get_annotations(self, options, lines):
        if not self._reads_ledger():
            return super().get_annotations(options, lines)
        self.check_singleton()
        annotations_by_line = defaultdict(list)
        line_dict_ids_by_record = defaultdict(set)
        model_ids_map = defaultdict(set)
        for line in lines:
            if line.get("chatter"):
                line_dict_ids_by_record[
                    line["chatter"]["model"], line["chatter"]["id"]
                ].add(line["id"])
                model_ids_map[line["chatter"]["model"]].add(line["chatter"]["id"])

        domain = Domain.OR(
            [
                Domain("message_id.model", "=", model)
                & Domain("message_id.res_id", "in", ids)
                for model, ids in model_ids_map.items()
            ]
        )
        if options.get("date"):
            period_date_from = self._get_annotations_domain_date_from(options)
            period_date_from = self._adjust_date_for_joined_comparison(
                options, period_date_from
            )
            dates_domain = Domain("date", ">=", period_date_from) & Domain(
                "date", "<=", options["date"]["date_to"]
            )
            dates_domain = self._adjust_domain_for_unjoined_comparison(
                options, dates_domain
            )
            domain &= dates_domain

        order = "create_date ASC" if options["export_mode"] else ""
        _debug.logic(
            "annotations_scope_decided",
            report=self,
            models=len(model_ids_map),
            records=len(line_dict_ids_by_record),
            dated=bool(options.get("date")),
            order=order,
        )
        report_annotations = self.env["account.report.annotation"].search(
            domain, order=order
        )
        for annotation in report_annotations:
            message = annotation.message_id
            for line_id in line_dict_ids_by_record[message.model, message.res_id]:
                annotations_by_line[line_id].append(
                    {
                        "id": message.id,
                        "model": message.model,
                        "res_id": message.res_id,
                        "date": annotation.date,
                        "body": message.body,
                        "line_id": line_id,
                    }
                )
        _debug.pipeline(
            "annotations_fetched",
            report=self,
            lines=len(lines),
            annotations=len(report_annotations),
            annotated_lines=len(annotations_by_line),
        )
        return annotations_by_line

    def _get_engines_without_next_groupby(self):
        return super()._get_engines_without_next_groupby() | LEDGER_ENGINES

    def _reads_ledger(self) -> bool:
        return self[:1]._get_source_model_name() in {None, "account.move.line"}

    def _get_source_model(self):
        source_model = super()._get_source_model()
        return self.env["account.move.line"] if source_model is None else source_model

    def _get_source_measure_field(self):
        measure_field = super()._get_source_measure_field()
        if measure_field or not self._reads_ledger():
            return measure_field
        return "balance"

    def _get_year_bounds(self, date):
        if not self._reads_ledger():
            return super()._get_year_bounds(date)
        return self.env.company.compute_fiscalyear_dates(date)

    def _get_year_end(self) -> tuple:
        if not self._reads_ledger():
            return super()._get_year_end()
        config = self.env.company.account_config_id
        return config.fiscalyear_last_day, int(config.fiscalyear_last_month)

    def _init_currency_table(self, options) -> None:
        if not self._reads_ledger():
            return
        if options["currency_table"]["type"] != "monocurrency":
            companies = self.env["res.company"].browse(
                self.get_report_company_ids(options)
            )

            self.env["res.currency"]._create_currency_table(
                companies,
                [
                    (period_key, period["from"], period["to"])
                    for period_key, period in options["currency_table"][
                        "periods"
                    ].items()
                ],
                use_cta_rates=options["currency_table"]["type"] == "cta",
            )

    @_debug.perf.timed
    def _create_aml_shadowing_query_for_budget(self, options):
        _stored_fields, fields_to_insert = self.env[
            "account.move.line"
        ]._prepare_aml_shadowing_for_report(
            {
                "id": SQL.identifier("item", "id"),
                "balance": SQL.identifier("item", "amount"),
                "company_id": SQL.identifier("budget", "company_id"),
                "parent_state": "posted",
                "date": SQL.identifier("item", "date"),
                "account_id": SQL.identifier("item", "account_id"),
                "debit": SQL("CASE WHEN (item.amount > 0) THEN item.amount else 0 END"),
                "credit": SQL(
                    "CASE WHEN (item.amount < 0) THEN -item.amount else 0 END"
                ),
            },
            prefix_fields_to_insert=False,
        )

        available_budget_ids = tuple(
            budget_option["id"] for budget_option in options["budgets"]
        )
        queries = [
            SQL(
                """
                SELECT %(fields_to_insert)s, item.budget_id
                FROM account_report_budget_item item
                JOIN account_report_budget budget ON budget.id = item.budget_id
                WHERE item.budget_id IN %(available_budget_ids)s
            """,
                fields_to_insert=fields_to_insert,
                available_budget_ids=available_budget_ids,
            )
        ]

        if options.get("show_all_accounts"):
            _stored_fields, fields_to_insert = self.env[
                "account.move.line"
            ]._prepare_aml_shadowing_for_report(
                {
                    "id": SQL("-(ROW_NUMBER() OVER ())"),
                    "balance": SQL("0"),
                    "company_id": SQL.identifier("budgets", "company_id"),
                    "parent_state": "posted",
                    "date": SQL("%s", options["date"]["date_from"]),
                    "account_id": SQL.identifier("accounts", "id"),
                    "debit": SQL("0"),
                    "credit": SQL("0"),
                },
                prefix_fields_to_insert=False,
            )
            accounts_subquery = (
                self.env["account.account"]
                .sudo()
                ._search(
                    [
                        ("company_ids", "in", self.get_report_company_ids(options)),
                        ("internal_group", "in", ["income", "expense"]),
                    ]
                )
            )

            queries.append(
                SQL(
                    """
                    SELECT %(fields_to_insert)s, budgets.id AS budget_id
                    FROM (%(accounts_subquery)s) AS accounts
                    CROSS JOIN (
                        SELECT id, company_id
                        FROM account_report_budget
                        WHERE id IN %(available_budget_ids)s
                    ) AS budgets
                """,
                    fields_to_insert=fields_to_insert,
                    accounts_subquery=accounts_subquery.select(),
                    available_budget_ids=available_budget_ids,
                )
            )

        _debug.logic(
            "budget_shadowing_built",
            report=self,
            budgets=len(available_budget_ids),
            show_all_accounts=bool(options.get("show_all_accounts")),
            queries=len(queries),
        )
        return SQL("(%s)", SQL(" UNION ALL ").join(queries))

    @_debug.perf.timed
    def _add_common_warnings(self, options, warnings) -> None:
        if not self._reads_ledger():
            super()._add_common_warnings(options, warnings)
            return
        if options.get("available_tax_units") and options["tax_unit"] == "company_only":
            warnings["account.common_warning_tax_unit"] = {}

        if options.get("date") and (
            off_anchor := self._get_companies_off_fiscalyear_anchor(options)
        ):
            warnings["account.common_warning_fiscalyear_anchor"] = {
                "alert_type": "warning",
                "main_company": self.env.company.display_name,
                "companies": ", ".join(off_anchor.mapped("display_name")),
            }

        report_company_ids = self.get_report_company_ids(options)
        if self.filter_multi_company == "tax_units" and any(
            accessible_branch.id not in report_company_ids
            for accessible_branch in self.env.company._get_accessible_branches()
        ):
            warnings["account.tax_report_warning_tax_id_selected_companies"] = {
                "alert_type": "warning"
            }

        if options.get("date") and options.get("all_entries") is not None:
            domain = (
                Domain(
                    self.env["account.move"]._get_domain_company_compatible(
                        report_company_ids
                    )
                )
                & Domain("state", "=", "draft")
                & Domain("date", "<=", options["date"]["date_to"])
            )
            if options.get("partner_ids"):
                domain &= (
                    Domain("partner_id", "in", options["partner_ids"])
                    | Domain("partner_shipping_id", "in", options["partner_ids"])
                    | Domain("commercial_partner_id", "in", options["partner_ids"])
                )
            if self.env["account.move"].search_count(domain, limit=1):
                warnings["account.common_warning_draft_in_period"] = {}
        if _debug.logic.enabled:
            _debug.logic(
                "common_warnings_checked",
                report=self,
                tax_unit=options.get("tax_unit"),
                draft_check=bool(
                    options.get("date") and options.get("all_entries") is not None
                ),
                warnings=sorted(warnings),
            )

    def _add_account_status_on_lines(self, lines, options):
        if not self._reads_ledger():
            return super()._add_account_status_on_lines(lines, options)
        if not self.allow_account_audit_status_on_lines:
            return lines
        if not options["audit"]["id"]:
            _debug.logic("account_status_skipped", report=self, reason="no_audit")
            return lines

        accounts_to_search = set()
        for line in lines:
            model, id = self._get_model_info_from_id(line["id"])
            if model == "account.account":
                accounts_to_search.add(id)

        account_statuses = self.env["account.audit.account.status"].search_read(
            domain=[
                ("audit_id", "=", options["audit"]["id"]),
                ("account_id", "in", tuple(accounts_to_search)),
            ],
            fields=["id", "account_id", "audit_id", "status"],
        )
        _debug.perf.count(
            "account_statuses_fetched",
            rows=len(account_statuses),
            accounts=len(accounts_to_search),
        )

        account_statuses = {
            account_status["account_id"][0]: account_status
            for account_status in account_statuses
        }

        for line in lines:
            model, id = self._get_model_info_from_id(line["id"])
            if model == "account.account" and id in account_statuses:
                line["account_status"] = account_statuses[id]

        return lines

    def _update_line_names_for_consolidation(self, lines) -> None:
        if not self._reads_ledger():
            super()._update_line_names_for_consolidation(lines)
            return
        account_codes = []
        for line in lines:
            markup = self._get_markup(line["id"])
            if isinstance(markup, dict) and markup.get("groupby") == "account_code":
                account_codes.append(line["name"])
        if not account_codes:
            _debug.logic(
                "consolidation_names_skipped", report=self, reason="no_code_lines"
            )
            return

        account_code_to_account_name_dict = {
            account.code: account.name
            for account in self.env["account.account"].search(
                [
                    *self.env["account.account"]._get_domain_company_compatible(
                        self.env.company
                    ),
                    ("code", "in", account_codes),
                ]
            )
        }
        _debug.perf.count(
            "consolidation_accounts_fetched",
            rows=len(account_code_to_account_name_dict),
            codes=len(account_codes),
        )
        for line in lines:
            markup = self._get_markup(line["id"])
            if isinstance(markup, dict) and markup.get("groupby") == "account_code":
                account_code = line["name"]
                account_name = account_code_to_account_name_dict.get(account_code)
                if account_code and account_name:
                    line["name"] = f"{account_code} {account_name}"

    @_debug.perf.timed
    def _create_carryover_external_values(self, options) -> None:
        self.check_singleton()

        if len(options["column_groups"]) > 1:
            raise UserError(
                self.env._("Carryover can only be generated for a single column group.")
            )

        carryover_expressions = self.line_ids.expression_ids.filtered(
            lambda x: x.label.startswith("_carryover_")
        )
        expressions_to_evaluate = carryover_expressions._expand_aggregations()

        expression_totals_per_col_group = (
            self._compute_expression_totals_for_each_column_group(
                expressions_to_evaluate, options
            )
        )
        expression_totals = expression_totals_per_col_group[
            next(iter(options["column_groups"].keys()))
        ]
        carryover_values = {
            expression: expression_totals[expression]["value"]
            for expression in carryover_expressions
        }
        _debug.pipeline(
            "carryover_totals_computed",
            report=self,
            carryover_expressions=carryover_expressions,
            expressions_to_evaluate=len(expressions_to_evaluate),
            companies=len(options["companies"]),
            split_per_company=len(options["companies"]) > 1,
        )

        if len(options["companies"]) == 1:
            company = self.env["res.company"].browse(
                self.get_report_company_ids(options)
            )
            self._create_carryover_for_company(
                options, company, dict(carryover_values.items())
            )
        else:
            multi_company_carryover_values_sum = defaultdict(lambda: 0)

            column_group_key = next(
                col_group_key for col_group_key in options["column_groups"]
            )
            for company_opt in options["companies"]:
                company = self.env["res.company"].browse(company_opt["id"])
                company_options = {
                    **options,
                    "companies": [{"id": company.id, "name": company.name}],
                }
                company_expressions_totals = (
                    self._compute_expression_totals_for_each_column_group(
                        expressions_to_evaluate, company_options
                    )
                )
                company_carryover_values = {
                    expression: company_expressions_totals[column_group_key][
                        expression
                    ]["value"]
                    for expression in carryover_expressions
                }
                self._create_carryover_for_company(
                    options, company, company_carryover_values
                )

                for carryover_expr, carryover_val in company_carryover_values.items():
                    multi_company_carryover_values_sum[carryover_expr] += carryover_val

            main_company = self._get_sender_company_for_export(options)
            _debug.logic(
                "carryover_adjusted_on_main",
                report=self,
                main_company=main_company,
                expressions=carryover_expressions,
            )
            for expr in carryover_expressions:
                difference = (
                    carryover_values[expr] - multi_company_carryover_values_sum[expr]
                )
                self._create_carryover_for_company(
                    options,
                    main_company,
                    {expr: difference},
                    label=self.env._("Carryover adjustment for tax unit"),
                )

    @api.model
    @_debug.perf.timed
    def _create_default_external_values(
        self, date_from, date_to, is_tax_report=False, company=None
    ) -> None:
        if date_from >= date_to:
            _debug.logic(
                "default_values_skipped",
                reason="empty_period",
                date_from=date_from,
                date_to=date_to,
            )
            return

        options_dict = {}
        default_expr_by_report = defaultdict(list)
        tax_report = self.env.ref("account.generic_tax_report")
        company = company or self.env.company
        previous_options = {
            "date": {
                "date_from": date_from,
                "date_to": date_to,
            }
        }

        default_expressions = self.env["report.formula.expression"].search(
            [("label", "=like", "_default_%")]
        )
        for expr in default_expressions:
            report = expr.report_line_id.report_id
            if is_tax_report == (
                tax_report
                in (
                    report
                    + report.root_report_id
                    + report.section_main_report_ids.root_report_id
                )
            ):
                if report not in options_dict:
                    options = report.with_context(
                        allowed_company_ids=[company.id]
                    ).get_options(previous_options)
                    options_dict[report] = options

                if report._filtered_available_for(options_dict[report]):
                    default_expr_by_report[report].append(expr)
        _debug.pipeline(
            "default_expressions_grouped",
            company=company,
            is_tax_report=is_tax_report,
            default_expressions=len(default_expressions),
            options_built=len(options_dict),
            reports=len(default_expr_by_report),
        )

        external_values_create_vals = []
        for report, report_default_expressions in default_expr_by_report.items():
            options = options_dict[report]

            target_by_default_expression = {}
            for default_expression in report_default_expressions:
                target_label = default_expression.label[len("_default_") :]
                target_by_default_expression[default_expression] = (
                    default_expression.report_line_id.expression_ids.filtered_domain(
                        [("label", "=", target_label)]
                    )
                )
            targets_with_value = {
                value.target_report_expression_id.id
                for value in self.env["report.formula.external.value"].search(  # noqa: E8507 -- one query per report, over every default expression at once
                    [
                        ("company_id", "=", company.id),
                        ("date", ">=", date_from),
                        ("date", "<=", date_to),
                        (
                            "target_report_expression_id",
                            "in",
                            [
                                target.id
                                for target in target_by_default_expression.values()
                            ],
                        ),
                    ]
                )
            }
            expressions_to_compute = {
                default_expression: target_external_expression.id
                for default_expression, target_external_expression in target_by_default_expression.items()
                if target_external_expression.id not in targets_with_value
            }
            _debug.logic(
                "default_values_to_compute",
                report=report,
                to_compute=len(expressions_to_compute),
                already_set=len(report_default_expressions)
                - len(expressions_to_compute),
            )

            expression_totals_per_col_group = report.with_company(
                company
            )._compute_expression_totals_for_each_column_group(
                expressions_to_compute, options, include_default_vals=True
            )
            expression_totals = expression_totals_per_col_group[
                next(iter(options["column_groups"].keys()))
            ]

            for expression, target_expression in expressions_to_compute.items():
                value = expression_totals[expression]["value"]
                field_name = (
                    "value" if isinstance(value, (int, float)) else "text_value"
                )
                external_values_create_vals.append(
                    {
                        "name": self.env._("Manual value"),
                        field_name: expression_totals[expression]["value"],
                        "date": date_to,
                        "target_report_expression_id": target_expression,
                        "company_id": company.id,
                    }
                )

        _debug.pipeline(
            "default_values_prepared",
            company=company,
            count=len(external_values_create_vals),
        )
        self.env["report.formula.external.value"].create(external_values_create_vals)

    @_debug.perf.timed
    def _create_carryover_for_company(
        self, options, company, carryover_per_expression, label=None
    ) -> None:
        date_from = options["date"]["date_from"]
        date_to = options["date"]["date_to"]

        external_values_create_vals = []
        for expression, carryover_value in carryover_per_expression.items():
            if not company.currency_id.is_zero(carryover_value):
                target_expression = expression._get_carryover_target_expression(options)
                external_values_create_vals.append(
                    {
                        "name": label
                        or self.env._(
                            "Carryover from %(date_from)s to %(date_to)s",
                            date_from=format_date(self.env, date_from),
                            date_to=format_date(self.env, date_to),
                        ),
                        "value": carryover_value,
                        "date": date_to,
                        "target_report_expression_id": target_expression.id,
                        "carryover_origin_expression_label": expression.label,
                        "carryover_origin_report_line_id": expression.report_line_id.id,
                        "company_id": company.id,
                    }
                )

        self.env["report.formula.external.value"].create(external_values_create_vals)

    @_debug.perf.timed
    def _filtered_available_for(self, options: dict[str, Any]) -> Self:
        if not self._reads_ledger():
            return super()._filtered_available_for(options)
        companies = self.env["res.company"].browse(self.get_report_company_ids(options))

        reports = self.filtered(lambda r: r.availability_condition == "always")

        reports_by_country = self.filtered(
            lambda r: r.availability_condition == "country"
        )
        if reports_by_country:
            company_countries = companies.tax_config_id.account_fiscal_country_id

            reports_foreign_vat = reports_by_country.filtered("allow_foreign_vat")
            reports_no_foreign_vat = reports_by_country - reports_foreign_vat

            fp_countries = self.env["res.country"]
            if reports_foreign_vat:
                foreign_vat_fpos = self.env["account.fiscal.position"].search(
                    [
                        ("foreign_vat", "!=", False),
                        ("company_id", "in", companies.ids),
                    ]
                )
                fp_countries |= foreign_vat_fpos.country_id

            reports += reports_by_country.filtered(lambda r: not r.country_id)
            reports += reports_no_foreign_vat.filtered(
                lambda r: r.country_id and r.country_id in company_countries
            )
            reports += reports_foreign_vat.filtered(
                lambda r: (
                    r.country_id and r.country_id in (company_countries | fp_countries)
                )
            )

        reports_by_coa = self.filtered(lambda r: r.availability_condition == "coa")
        if reports_by_coa:
            chart_templates = set(companies.account_config_id.mapped("chart_template"))
            reports += reports_by_coa.filtered(
                lambda r: r.chart_template in chart_templates
            )

        _debug.logic(
            "availability_resolved",
            reports=self,
            available=reports,
            by_country=reports_by_country,
            by_coa=reports_by_coa,
        )
        return reports

    def _get_fiscalyear_dates_by_company(self, options, date):
        if not self._reads_ledger():
            return super()._get_fiscalyear_dates_by_company(options, date)
        return (
            self.env["res.company"]
            .browse(self.get_report_company_ids(options))
            ._compute_fiscalyear_dates_by_company(fields.Date.to_date(date))
        )

    def _get_companies_off_fiscalyear_anchor(self, options):
        periods = [options["date"], *options.get("comparison", {}).get("periods", [])]
        company_ids = set()
        for period in periods:
            if period.get("mode") != "range" or period.get("period_type") not in {
                "fiscalyear",
                "today",
            }:
                continue
            date_to = fields.Date.to_date(period["date_to"])
            anchor = self._get_year_bounds(date_to)
            company_ids.update(
                company_id
                for company_id, fiscal_year in self._get_fiscalyear_dates_by_company(
                    options, date_to
                ).items()
                if (fiscal_year["date_from"], fiscal_year["date_to"])
                != (anchor["date_from"], anchor["date_to"])
            )
        _debug.logic(
            "fiscalyear_anchor_checked",
            report=self,
            anchor_company=self.env.company,
            periods=len(periods),
            off_anchor=sorted(company_ids),
        )
        return self.env["res.company"].browse(sorted(company_ids))

    def _get_fiscalyear_start_by_company(self, options) -> dict:
        if starts := options.get("fiscalyear_start_by_company"):
            return {
                int(company_id): fields.Date.to_date(start)
                for company_id, start in starts.items()
            }
        return {
            company_id: fiscal_year["date_from"]
            for company_id, fiscal_year in self._get_fiscalyear_dates_by_company(
                options, options["date"]["date_from"]
            ).items()
        }

    def _get_fiscalyear_pnl_domain(self, fiscalyear_start_by_company):
        return Domain(
            "account_id.include_initial_balance", "=", True
        ) | self._get_fiscalyear_date_domain(fiscalyear_start_by_company, ">=")

    def _get_unallocated_earnings_domain(self, fiscalyear_start_by_company):
        return Domain(
            "account_id.include_initial_balance", "=", False
        ) & self._get_fiscalyear_date_domain(fiscalyear_start_by_company, "<")

    @_debug.perf.timed
    def _get_custom_engine_unfold_all_batch_data(
        self,
        options,
        lines_to_expand_by_function,
        engine_formula,
        get_engine_rows,
        exclusive_engine=False,
    ):
        results = {}
        for line_to_expand in lines_to_expand_by_function.get(
            "_report_expand_unfoldable_line_with_groupby", []
        ):
            report_line = self.env["report.formula.line"].browse(
                self._get_res_id_from_line_id(
                    line_to_expand["id"], "report.formula.line"
                )
            )
            expressions = report_line.expression_ids.filtered(
                lambda expression: (
                    expression.engine == "custom"
                    and expression.formula == engine_formula
                )
            )
            if not expressions or (
                exclusive_engine and expressions != report_line.expression_ids
            ):
                _debug.logic(
                    "unfold_batch_skipped",
                    report=self,
                    report_line=report_line,
                    reason="mixed_engine_expressions"
                    if expressions
                    else "no_engine_expressions",
                )
                continue
            for (
                column_group_key,
                column_group_options,
            ) in self._split_options_per_column_group(options).items():
                for date_scope, expressions_by_date_scope in groupby(
                    expressions, lambda expression: expression.date_scope
                ):
                    for sub_groupby_key, rows in get_engine_rows(
                        report_line,
                        expressions_by_date_scope,
                        column_group_options,
                        date_scope,
                    ):
                        results.setdefault(sub_groupby_key, {}).setdefault(
                            column_group_key, {}
                        ).update(
                            {
                                expression: {
                                    "value": [
                                        (grouping_key, values[expression.subformula])
                                        for grouping_key, values in rows
                                    ],
                                    "sublines_info": {
                                        grouping_key
                                        for grouping_key, values in rows
                                        if values["has_sublines"]
                                    },
                                }
                                for expression in expressions_by_date_scope
                            }
                        )
        _debug.pipeline(
            "unfold_batch_generated",
            report=self,
            engine=engine_formula,
            groupby_keys=len(results),
        )
        return results

    @_debug.perf.timed
    def _get_unallocated_earnings_lines(
        self, options, date_scope, auditable=False
    ) -> list:
        def get_column_group_result(query_options, date_scope):
            query = self._get_report_query(
                query_options,
                date_scope,
                domain=self._get_unallocated_earnings_domain(
                    self._get_fiscalyear_start_by_company(query_options)
                ),
            )
            return self.env.execute_query_dict(
                SQL(
                    """
                SELECT account_move_line.company_id, %(sums_select)s
                  FROM %(table_references)s
                       %(currency_table_join)s
                 WHERE %(search_condition)s
              GROUP BY account_move_line.company_id
                """,
                    sums_select=self._get_aml_sums_select(),
                    table_references=query.from_clause,
                    currency_table_join=self._currency_table_aml_join(query_options),
                    search_condition=query.where_clause,
                )
            )

        if not self.custom_handler_model_id:
            _debug.logic("unallocated_earnings_no_handler", report=self)
            return []
        unallocated_earnings_lines = defaultdict(dict)
        company_to_line_id = {}
        for (
            column_group_key,
            column_group_options,
        ) in self._split_options_per_column_group(options).items():
            data = get_column_group_result(column_group_options, date_scope)
            _debug.perf.count(
                "unallocated_earnings_rows",
                rows=len(data),
                column_group_key=column_group_key,
            )

            for company_line in data:
                line_id = self._get_generic_line_id(
                    "res.company",
                    company_line["company_id"],
                    markup="undistributed_profits_losses",
                )
                company_to_line_id[company_line["company_id"]] = line_id
                unallocated_earnings_lines[column_group_key] |= {line_id: company_line}

        _debug.pipeline(
            "unallocated_earnings_fetched",
            report=self,
            date_scope=date_scope,
            column_groups=len(unallocated_earnings_lines),
            companies=len(company_to_line_id),
            auditable=auditable,
        )
        search_text = (options.get("filter_search_bar") or "").lower()
        lines = []
        for company in self.env["res.company"].browse(company_to_line_id).sorted():
            line_id = company_to_line_id[company.id]
            line_name = (
                str(UNDISTR_LINE_NAME)
                if len(self.env.companies) == 1
                else self.env._(
                    "%(line_name)s - %(company)s",
                    line_name=UNDISTR_LINE_NAME,
                    company=company.name,
                )
            )
            if search_text not in line_name.lower():
                _debug.logic(
                    "unallocated_earnings_search_mismatch",
                    report=self,
                    filter_search_bar=search_text,
                    line_name=line_name,
                )
                continue
            lines.append(
                {
                    "id": line_id,
                    "name": line_name,
                    "level": 1,
                    "columns": [
                        self._prepare_column_dict(
                            unallocated_earnings_lines.get(
                                column["column_group_key"], {}
                            )
                            .get(line_id, {})
                            .get(
                                column["expression_label"],
                                0.0 if column["figure_type"] == "monetary" else None,
                            ),
                            column,
                            options=options,
                        )
                        | {"auditable": auditable}
                        for column in options["columns"]
                    ],
                    "unfoldable": False,
                    "unfolded": False,
                    "caret_options": "undistributed_profits_losses",
                }
            )
        return lines

    @_debug.perf.timed
    def _get_partner_and_general_ledger_initial_balance_line(
        self, options, parent_line_id, eval_dict, account_currency=None, level_shift=0
    ) -> dict | None:
        line_columns = []
        for column in options["columns"]:
            col_value = eval_dict[column["column_group_key"]].get(
                column["expression_label"]
            )
            col_expr_label = column["expression_label"]

            if col_value is None or (
                col_expr_label == "amount_currency" and not account_currency
            ):
                line_columns.append(self._prepare_column_dict(None, None))
            else:
                line_columns.append(
                    self._prepare_column_dict(
                        col_value,
                        column,
                        options=options,
                        currency=account_currency
                        if col_expr_label == "amount_currency"
                        else None,
                    )
                )

        if not any(
            isinstance(column.get("no_format"), (int, float))
            and column.get("expression_label") != "balance"
            for column in line_columns
        ):
            return None

        return {
            "id": self._get_generic_line_id(
                None, None, parent_line_id=parent_line_id, markup="initial"
            ),
            "name": self.env._("Initial Balance"),
            "level": 3 + level_shift,
            "parent_id": parent_line_id,
            "columns": line_columns,
        }

    @_debug.perf.timed
    def _set_budget_column_comparisons(self, options, line) -> None:
        if not self._reads_ledger():
            super()._set_budget_column_comparisons(options, line)
            return
        for col_index, col in enumerate(line["columns"]):
            col_group_data = options["column_groups"][col["column_group_key"]]
            if "budget_percentage" in col_group_data.get("forced_options", {}):
                budget_id = col_group_data["forced_options"]["budget_percentage"]
                date_key = col_group_data.get("forced_options", {}).get("date")
                if not date_key:
                    continue

                budget_base_col = None
                budget_amount_col = None
                for line_col in line["columns"]:
                    other_col_group_key = line_col["column_group_key"]
                    other_col_options = options["column_groups"][other_col_group_key]
                    if (
                        other_col_options.get("forced_options", {}).get("date")
                        == date_key
                    ):
                        if (
                            other_col_options.get("forced_options", {}).get(
                                "budget_base"
                            )
                            and line_col["figure_type"] == "monetary"
                        ):
                            budget_base_col = line_col
                        elif (
                            other_col_options.get("forced_options", {}).get(
                                "compute_budget"
                            )
                            == budget_id
                        ):
                            budget_amount_col = line_col
                if budget_base_col is None or budget_amount_col is None:
                    continue
                value = self._get_column_percent_comparison_data(
                    options,
                    budget_base_col["no_format"],
                    budget_amount_col["no_format"],
                    green_on_positive=budget_base_col["green_on_positive"],
                )
                comparison_column = self._prepare_column_dict(
                    value["name"],
                    {
                        **budget_amount_col,
                        "figure_type": "string",
                        "comparison_mode": value["mode"],
                    },
                )
                line["columns"][col_index] = comparison_column

    def show_error_branch_allowed(self, *args, **kwargs) -> None:
        raise UserError(
            self.env._(
                "Please select the main company and its branches in the company selector to proceed."
            )
        )

    @api.model
    def _prepare_editable_cell_data(
        self, options, col_group_key, groupby_model, column_expression, column_value
    ) -> dict | None:
        if not self._reads_ledger():
            return super()._prepare_editable_cell_data(
                options, col_group_key, groupby_model, column_expression, column_value
            )
        editable_budget = groupby_model == "account.account" and options[
            "column_groups"
        ][col_group_key]["forced_options"].get("compute_budget")
        if not editable_budget or not self.env.user.has_group(
            "account.group_account_manager"
        ):
            return None

        return {
            "column_group_key": col_group_key,
            "target_expression_id": column_expression.id,
            "rounding": self.env.company.currency_id.decimal_places,
            "figure_type": "monetary",
            "column_value": self.env.company.currency_id.round(column_value)
            if column_value
            else column_value,
        }

    @_debug.perf.timed
    def _create_hierarchy(self, lines, options):
        if not self._reads_ledger():
            return super()._create_hierarchy(lines, options)
        if not lines:
            _debug.logic("hierarchy_skipped", report=self, reason="no_lines")
            return lines

        def get_account_group_hierarchy(account):
            groups = self.env["account.group"]
            if account.group_id:
                group = account.group_id
                while group:
                    groups += group
                    group = group.parent_id
            return list(groups.sorted(reverse=True))

        def create_hierarchy_line(account_group, column_totals, level, parent_id):
            line_id = self._get_generic_line_id(
                "account.group",
                account_group.id if account_group else None,
                parent_line_id=parent_id,
            )
            unfolded = line_id in options.get("unfolded_lines") or options["unfold_all"]
            name = (
                account_group.display_name
                if account_group
                else self.env._("(No Group)")
            )
            columns = []
            for col_total, column in zip(
                column_totals, options["columns"], strict=False
            ):
                if isinstance(col_total, tuple):
                    col_value, currency = col_total
                else:
                    col_value = col_total
                    currency = None

                columns.append(
                    self._prepare_column_dict(
                        col_value, column, options=options, currency=currency
                    )
                )

            return {
                "id": line_id,
                "name": name,
                "title_hover": name,
                "unfoldable": True,
                "unfolded": unfolded,
                "level": level,
                "parent_id": parent_id,
                "columns": columns,
            }

        def compute_group_totals(line, group=None):
            totals = []

            for total, column in zip(
                hierarchy[group]["totals"], line["columns"], strict=False
            ):
                if not isinstance(column.get("no_format"), (int, float)):
                    total = None

                if isinstance(total, (int, float)):
                    total += column["no_format"]
                elif isinstance(total, tuple):
                    if total == (None, None):
                        amount = 0.0
                        currency = column.get("currency")
                    else:
                        amount, currency = total

                    if currency != column.get("currency"):
                        total = None
                    else:
                        total = (amount + column["no_format"], currency)

                totals.append(total)

            return totals

        def render_lines(
            account_groups, current_level, parent_line_id, skip_no_group=True
        ):
            to_treat = [
                (current_level, parent_line_id, group)
                for group in account_groups.sorted()
            ]

            if None in hierarchy and not skip_no_group:
                to_treat.append((current_level, parent_line_id, None))

            while to_treat:
                level_to_apply, parent_id, group = to_treat.pop(0)
                group_data = hierarchy[group]
                hierarchy_line = create_hierarchy_line(
                    group, group_data["totals"], level_to_apply, parent_id
                )
                new_lines.append(hierarchy_line)
                treated_child_groups = self.env["account.group"]

                for account_line in group_data["lines"]:
                    for child_group in group_data["child_groups"]:
                        if (
                            child_group not in treated_child_groups
                            and child_group["code_prefix_end"] < account_line["name"]
                        ):
                            render_lines(
                                child_group,
                                hierarchy_line["level"] + 1,
                                hierarchy_line["id"],
                            )
                            treated_child_groups += child_group

                    markup, model, account_id = self._parse_line_id(account_line["id"])[
                        -1
                    ]
                    account_line_id = self._get_generic_line_id(
                        model,
                        account_id,
                        markup=markup,
                        parent_line_id=hierarchy_line["id"],
                    )
                    account_line.update(
                        {
                            "id": account_line_id,
                            "parent_id": hierarchy_line["id"],
                            "level": hierarchy_line["level"] + 1,
                        }
                    )
                    new_lines.append(account_line)

                    for child_line in account_line_children_map[account_id]:
                        markup, model, res_id = self._parse_line_id(child_line["id"])[
                            -1
                        ]
                        child_line.update(
                            {
                                "id": self._get_generic_line_id(
                                    model,
                                    res_id,
                                    markup=markup,
                                    parent_line_id=account_line_id,
                                ),
                                "parent_id": account_line_id,
                                "level": account_line["level"] + 1,
                            }
                        )
                        new_lines.append(child_line)

                to_treat = [
                    (level_to_apply + 1, hierarchy_line["id"], child_group)
                    for child_group in group_data["child_groups"].sorted()
                    if child_group not in treated_child_groups
                ] + to_treat

        def create_hierarchy_dict():
            def create_totals():
                totals = []

                for column in options["columns"]:
                    default_value = None
                    if figure_type := column.get("figure_type"):
                        if figure_type == "float":
                            default_value = 0.0
                        elif figure_type == "integer":
                            default_value = 0
                        elif figure_type == "monetary":
                            default_value = (None, None)
                    totals.append(default_value)

                return totals

            return defaultdict(
                lambda: {
                    "lines": [],
                    "totals": create_totals(),
                    "child_groups": self.env["account.group"],
                }
            )

        account_ids = []
        for line in lines:
            markup, res_model, model_id = self._parse_line_id(line["id"])[-1]
            if res_model == "account.account":
                account_ids.append(model_id)
        self.env["account.account"].browse(account_ids).mapped("group_id")
        _debug.pipeline(
            "hierarchy_input",
            report=self,
            lines=len(lines),
            account_lines=len(account_ids),
        )
        hierarchy_segments = 1

        new_lines, total_lines = [], []

        root_line_id = (
            self._prepare_parent_line_id(self._parse_line_id(lines[0]["id"])) or None
        )
        last_account_line_id = account_id = None
        current_level = 0
        account_line_children_map = defaultdict(list)
        account_groups = self.env["account.group"]
        root_account_groups = self.env["account.group"]
        hierarchy = create_hierarchy_dict()

        for line in lines:
            markup, res_model, model_id = self._parse_line_id(line["id"])[-1]

            if res_model == "account.account":
                last_account_line_id = line["id"]
                current_level = line["level"]
                account_id = model_id
                account = self.env[res_model].browse(account_id)
                account_groups = get_account_group_hierarchy(account)

                if not account_groups:
                    hierarchy[None]["lines"].append(line)
                    hierarchy[None]["totals"] = compute_group_totals(line)
                else:
                    for i, group in enumerate(account_groups):
                        if i == 0:
                            hierarchy[group]["lines"].append(line)
                        if (
                            i == len(account_groups) - 1
                            and group not in root_account_groups
                        ):
                            root_account_groups += group
                        if (
                            group.parent_id
                            and group not in hierarchy[group.parent_id]["child_groups"]
                        ):
                            hierarchy[group.parent_id]["child_groups"] += group

                        hierarchy[group]["totals"] = compute_group_totals(
                            line, group=group
                        )

            elif last_account_line_id and line.get("parent_id", "").startswith(
                last_account_line_id
            ):
                account_line_children_map[account_id].append(line)

            elif markup == "total":
                total_lines.append(line)

            else:
                render_lines(
                    root_account_groups,
                    current_level,
                    root_line_id,
                    skip_no_group=False,
                )

                new_lines.append(line)

                root_line_id = line["id"]
                last_account_line_id = account_id = None
                current_level = 0
                account_line_children_map = defaultdict(list)
                root_account_groups = self.env["account.group"]
                account_groups = self.env["account.group"]
                hierarchy = create_hierarchy_dict()
                hierarchy_segments += 1

        render_lines(
            root_account_groups, current_level, root_line_id, skip_no_group=False
        )

        _debug.pipeline(
            "hierarchy_built",
            report=self,
            segments=hierarchy_segments,
            new_lines=len(new_lines),
            total_lines=len(total_lines),
        )
        return new_lines + total_lines

    @_debug.perf.timed
    def _get_annotations_domain_date_from(self, options):
        if (
            options["date"]["filter"] in {"today", "custom"}
            and options["date"]["mode"] == "single"
        ):
            date_to = fields.Date.to_date(options["date"]["date_to"])
            root_companies = (
                self.env["res.company"]
                .browse(self.get_report_company_ids(options))
                .root_id
            )
            period_date_from = min(
                fiscal_year["date_from"]
                for fiscal_year in root_companies._compute_fiscalyear_dates_by_company(
                    date_to
                ).values()
            )
            _debug.logic(
                "date_from_earliest_fiscal_year",
                report=self,
                companies=root_companies,
                date_from=period_date_from,
            )
            return datetime.datetime.combine(period_date_from, datetime.time.min)

        date_from = datetime.datetime.strptime(options["date"]["date_from"], "%Y-%m-%d")
        if options["date"]["period_type"] == "fiscalyear":
            period_date_from, _ = date_utils.get_fiscal_year(
                date_from,
                day=self.env.company.account_config_id.fiscalyear_last_day,
                month=int(self.env.company.account_config_id.fiscalyear_last_month),
            )
        elif options["date"]["period_type"] in [
            "year",
            "quarter",
            "month",
            "week",
            "day",
            "hour",
        ]:
            period_date_from = date_utils.start_of(
                date_from, options["date"]["period_type"]
            )
        else:
            period_date_from = date_from
        _debug.logic(
            "date_from_period_type",
            report=self,
            period_type=options["date"]["period_type"],
            date_from=period_date_from,
        )
        return period_date_from

    @api.model
    def _postprocess_chatter_for_annotations(self, lines) -> None:
        if not self._reads_ledger():
            super()._postprocess_chatter_for_annotations(lines)
            return
        aml_id_to_report_lines_map = defaultdict(list)
        for line in lines:
            if line.get("unfoldable"):
                continue

            model, record_id = self._get_model_info_from_id(line.get("id"))
            if model == "account.move.line" and record_id is not None:
                aml_id_to_report_lines_map[record_id].append(line)
            elif model in self._get_annotatable_models():
                line["chatter"] = {
                    "model": model,
                    "id": record_id,
                }

        aml_id_to_account_move_id = {
            line["id"]: line["move_id"]
            for line in self.env["account.move.line"]
            .browse(aml_id_to_report_lines_map.keys())
            .read(["id", "move_id"], load=False)
        }
        _debug.pipeline(
            "annotation_chatter_mapped",
            report=self,
            lines=len(lines),
            amls=len(aml_id_to_account_move_id),
        )
        for aml_id, aml_lines in aml_id_to_report_lines_map.items():
            for line in aml_lines:
                line["chatter"] = {
                    "model": "account.move",
                    "id": aml_id_to_account_move_id[aml_id],
                }

    @api.model
    def _get_annotatable_models(self) -> set:
        return {"account.account", "account.move", "account.tax"}
