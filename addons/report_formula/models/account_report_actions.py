from ast import literal_eval
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.libs.numbers import float_round
from odoo.service.model import get_public_method
from odoo.tools import SQL

from odoo.addons.web.controllers.utils import clean_action

_debug = DebugLog(__name__)


class AccountReportActions(models.Model):
    _inherit = "report.formula"

    @_debug.perf.timed
    def action_view_report_form(self, options, params) -> dict:
        _debug.lifecycle("action_view_report_form", records=self)
        return {
            "type": "ir.actions.act_window",
            "res_model": "report.formula",
            "view_mode": "form",
            "views": [(False, "form")],
            "res_id": self.id,
        }

    def _get_caret_options(self) -> dict:
        return {
            **self._caret_options_initializer_default(),
            **(
                self.env[self.custom_handler_model_name]._caret_options_initializer()
                if self.custom_handler_model_id
                else {}
            ),
        }

    def _caret_options_initializer_default(self) -> dict:
        return {
            "res.partner": [
                {
                    "name": self.env._("View Partner"),
                    "action": "caret_option_open_record_form",
                },
            ],
        }

    def caret_option_open_record_form(self, options, params):
        model, record_id = self._get_model_info_from_id(params["line_id"])
        record = self.env[model].browse(record_id)
        target_record = (
            record[params["action_param"]] if "action_param" in params else record
        )

        view_id = self._resolve_caret_option_view(target_record)

        action = {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "views": [(view_id, "form")],
            "res_model": target_record._name,
            "res_id": target_record.id,
            "context": self.env.context,
        }

        if view_id is not None:
            action["view_id"] = view_id

        return action

    def _get_caret_option_view_map(self) -> dict:
        return {"res.partner": "base.view_partner_form"}

    def _resolve_caret_option_view(self, target):
        view_map = self._get_caret_option_view_map()

        view_xmlid = view_map.get(target._name)
        if not view_xmlid:
            return None

        return self.env["ir.model.data"]._get_xmlid_target(view_xmlid)[1]

    @_debug.perf.timed
    def dispatch_report_action(
        self, options, action, action_param=None, on_sections_source=False
    ):
        self.check_singleton()

        if on_sections_source:
            report_to_call = self.env["report.formula"].browse(
                options["sections_source_id"]
            )
            if report_to_call != self and not (
                self in report_to_call.section_report_ids
                or report_to_call in self.variant_report_ids
            ):
                raise UserError(
                    self.env._(
                        "Trying to dispatch an action on a report unrelated to the provided sections source."
                    )
                )
            _debug.logic(
                "dispatch_rerouted_sections_source",
                report=self,
                sections_source=report_to_call,
                action=action,
            )
            return report_to_call.dispatch_report_action(
                {**options, "report_id": report_to_call.id},
                action,
                action_param=action_param,
                on_sections_source=False,
            )

        if self.id not in (options["report_id"], options.get("sections_source_id")):
            raise UserError(
                self.env._(
                    "Trying to dispatch an action on a report not compatible with the provided options."
                )
            )

        model = self
        custom_handler_model = self._get_custom_handler_model()
        if custom_handler_model and hasattr(self.env[custom_handler_model], action):
            model = self.env[custom_handler_model]
        _debug.logic(
            "dispatch_handler_chosen",
            report=self,
            action=action,
            custom_handler_model=custom_handler_model,
            on_handler=model is not self,
            has_param=action_param is not None,
        )
        report_method = get_public_method(model, action)
        args = [options, action_param] if action_param is not None else [options]
        with _debug.perf(
            "dispatch", cr=self.env.cr, report=self, model=model._name, action=action
        ):
            return report_method(model, *args)

    @_debug.perf.timed
    def action_audit_cell(self, options, params):
        _debug.lifecycle("action_audit_cell", records=self)
        report_line = self.env["report.formula.line"].browse(params["report_line_id"])
        expression_label = params["expression_label"]
        expression = report_line.expression_ids.filtered(
            lambda x: x.label == expression_label
        )
        column_group_options = self._get_column_group_options(
            options, params["column_group_key"]
        )

        _debug.logic(
            "audit_target_resolved",
            report=self,
            expression=expression,
            engine=expression.engine,
            column_group_key=params["column_group_key"],
        )
        if expression.engine == "external":
            external_values_domain = (
                Domain("target_report_expression_id", "=", expression.id)
                & self._get_date_scope_domain(
                    column_group_options, expression.date_scope
                )
                & Domain(
                    "company_id",
                    "in",
                    self.get_report_company_ids(column_group_options),
                )
            )

            if expression.formula == "most_recent":
                query = self.env["report.formula.external.value"]._search(
                    external_values_domain, bypass_access=True
                )
                where_clause = query.where_clause or SQL("TRUE")
                external_value_ids = self.env.execute_query(
                    SQL(
                        "SELECT id FROM %s WHERE %s AND %s",
                        query.from_clause,
                        where_clause,
                        self._get_external_values_latest_per_company(where_clause),
                    )
                )
                external_values_domain = Domain(
                    "id", "in", [row[0] for row in external_value_ids]
                )
                _debug.logic(
                    "audit_most_recent_narrowed",
                    report=self,
                    expression=expression,
                    narrowed=len(external_value_ids),
                )

            return {
                "name": self.env._("Manual values"),
                "type": "ir.actions.act_window",
                "res_model": "report.formula.external.value",
                "view_mode": "list",
                "views": [(False, "list")],
                "domain": list(external_values_domain),
            }

        column = next(
            (
                col
                for col in report_line.report_id.column_ids
                if col.expression_label == expression_label
            ),
            self.env["report.formula.column"],
        )
        if column.custom_audit_action_id:
            action_dict = column.custom_audit_action_id._get_action_dict()
        else:
            action_dict = self._get_default_audit_action_dict()

        _debug.logic(
            "audit_action_chosen",
            report=self,
            column=column,
            custom_action=column.custom_audit_action_id,
        )
        action = clean_action(action_dict, env=self.env)
        action["domain"] = self._get_domain_audit_line(
            column_group_options, expression, params
        )
        return action

    def _get_default_audit_action_dict(self) -> dict:
        source_model = self._get_required_source_model()
        return {
            "name": source_model._description,
            "type": "ir.actions.act_window",
            "res_model": source_model._name,
            "view_mode": "list",
            "views": [(False, "list")],
            "context": {
                "active_test": False,
            },
        }

    @_debug.perf.timed
    def action_view_all_variants(self, options, params) -> dict:
        _debug.lifecycle("action_view_all_variants", records=self)
        return {
            "name": self.env._("All Report Variants"),
            "type": "ir.actions.act_window",
            "res_model": "report.formula",
            "view_mode": "list",
            "views": [(False, "list"), (False, "form")],
            "context": {
                "active_test": False,
            },
            "domain": [
                (
                    "id",
                    "in",
                    self._get_variants(options["variants_source_id"])
                    ._filtered_available_for(options)
                    .ids,
                )
            ],
        }

    @_debug.perf.timed
    def action_modify_manual_value(
        self,
        line_id,
        options,
        column_group_key,
        new_value_str,
        target_expression_id,
        rounding,
        json_friendly_column_group_totals,
    ) -> dict:
        _debug.lifecycle("action_modify_manual_value", records=self)
        self.check_singleton()

        target_column_group_options = self._get_column_group_options(
            options, column_group_key
        )
        self._init_currency_table(target_column_group_options)

        expressions_to_recompute = self._modify_manual_value(
            line_id,
            target_column_group_options,
            new_value_str,
            target_expression_id,
            rounding,
        )

        _debug.logic(
            "manual_value_target",
            report=self,
            column_group_key=column_group_key,
            budget=target_column_group_options.get("compute_budget"),
            target_expression_id=target_expression_id,
            expressions_to_recompute=expressions_to_recompute,
        )

        all_column_groups_expression_totals = (
            self._convert_json_friendly_column_group_totals(
                json_friendly_column_group_totals,
                expressions_to_exclude=expressions_to_recompute,
            )
        )

        recomputed_expression_totals = self._compute_expression_totals_for_each_column_group(
            expressions_to_recompute,
            options,
            forced_all_column_groups_expression_totals=all_column_groups_expression_totals,
        )
        _debug.pipeline(
            "manual_value_recomputed",
            report=self,
            expressions=len(expressions_to_recompute),
            column_groups=len(recomputed_expression_totals),
        )

        return {
            "lines": self._get_lines(
                options,
                all_column_groups_expression_totals=recomputed_expression_totals,
            ),
            "column_groups_totals": self._get_json_friendly_column_group_totals(
                recomputed_expression_totals
            ),
        }

    def _modify_manual_value(
        self,
        line_id,
        target_column_group_options,
        new_value_str,
        target_expression_id,
        rounding,
    ):
        self._action_modify_manual_external_value(
            target_column_group_options,
            new_value_str,
            target_expression_id,
            rounding,
        )
        return self.line_ids.expression_ids.filtered(
            lambda x: x.engine in ("external", "aggregation")
        )

    @_debug.perf.timed
    def action_create_composite_report(self) -> dict:
        _debug.lifecycle("action_create_composite_report", records=self)
        return {
            "type": "ir.actions.act_window",
            "res_model": "report.formula",
            "views": [[False, "form"]],
            "context": {
                "default_section_report_ids": self.ids,
            },
        }

    def _get_existing_menuitem(self) -> tuple:
        self.check_singleton()
        action = (
            self.env["ir.actions.client"]
            .search([("name", "=", self.name), ("tag", "=", "account_report")])
            .filtered(
                lambda act: (
                    self.env["ir.actions.actions"]
                    ._eval_action_context(act.context)
                    .get("report_id")
                    == self.id
                )
            )
        )
        menuitem = (
            self.env["ir.ui.menu"]
            .with_context({"active_test": False})
            .search([("action", "=", f"ir.actions.client,{action.id}")])
        )
        return action, menuitem

    @_debug.perf.timed
    def _create_menu_item_for_report(self) -> dict:
        self.check_singleton()

        action, menuitem = self._get_existing_menuitem()

        if menuitem:
            raise UserError(self.env._("This report already has a menuitem."))

        _debug.logic("menu_action_resolved", report=self, existing_action=action)
        if not action:
            action = self.env["ir.actions.client"].create(
                {
                    "name": self.name,
                    "tag": "account_report",
                    "context": {"report_id": self.id},
                }
            )

        self.env["ir.ui.menu"].create(
            {
                "name": self.name,
                "parent_id": self._get_reports_parent_menu_id(),
                "action": f"ir.actions.client,{action.id}",
            }
        )

        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def _get_reports_parent_menu_id(self):
        return False

    def _get_action_name(self, params, record_model=None, record_id=None):
        if not (record_model or record_id):
            record_model, record_id = self._get_model_info_from_id(
                params.get("line_id")
            )
        return (
            params.get("name")
            or self.env[record_model].browse(record_id).display_name
            or ""
        )

    @_debug.perf.timed
    def execute_action(self, options, params=None):
        action_id = int(params.get("actionId"))
        action = self.env["ir.actions.actions"].sudo().browse([action_id])
        action_type = action.type
        _debug.pipeline(
            "execute_action",
            report=self,
            action_id=action_id,
            action_type=action_type,
            line=params.get("id"),
        )
        action = self.env[action.type].sudo().browse([action_id])
        action_read = clean_action(action.read()[0], env=action.env)

        if action_type == "ir.actions.client":
            if action.tag == "account_report":
                target_report = self.env["report.formula"].browse(
                    self.env["ir.actions.actions"]._eval_action_context(
                        action_read["context"]
                    )["report_id"]
                )
                new_options = target_report.get_options(previous_options=options)
                action_read.update(
                    {"params": {"options": new_options, "ignore_session": True}}
                )

        if params.get("id"):
            if isinstance(params["id"], int):
                model_id = params["id"]
            else:
                model_id = self._get_model_info_from_id(params["id"])[1]

            context = (
                action_read.get("context")
                and self.env["ir.actions.actions"]._eval_action_context(
                    action_read["context"]
                )
            ) or {}
            context.setdefault("active_id", model_id)
            action_read["context"] = context

        return action_read

    @_debug.perf.timed
    def _action_modify_manual_external_value(
        self, target_column_group_options, new_value_str, target_expression_id, rounding
    ) -> None:
        _debug.lifecycle("_action_modify_manual_external_value", records=self)
        if len(target_column_group_options["companies"]) > 1:
            raise UserError(
                self.env._(
                    "Editing a manual report line is not allowed when multiple companies are selected."
                )
            )

        target_expression = self.env["report.formula.expression"].browse(
            target_expression_id
        )
        company = self.env["res.company"].browse(
            self.get_report_company_ids(target_column_group_options)
        )
        date_scope = target_expression.date_scope
        date_to = self._get_manual_value_date(
            target_column_group_options, date_scope, company
        )

        external_values_domain = Domain(
            "target_report_expression_id", "=", target_expression.id
        ) & Domain("company_id", "=", company.id)

        if target_expression.formula == "most_recent":
            value_to_adjust = 0
            existing_value_to_modify = self.env["report.formula.external.value"].search(
                external_values_domain & Domain("date", "=", date_to)
            )

            if len(existing_value_to_modify) > 1:
                raise UserError(
                    self.env._(
                        "Inconsistent data: more than one external value at the same date for a 'most_recent' external line."
                    )
                )
        else:
            existing_external_values = self.env["report.formula.external.value"].search(
                external_values_domain
                & self._get_date_scope_domain(target_column_group_options, date_scope),
                order="date ASC",
            )
            existing_value_to_modify = (
                existing_external_values[-1]
                if existing_external_values
                and str(existing_external_values[-1].date) == date_to
                else None
            )
            value_to_adjust = sum(
                existing_external_values.filtered(
                    lambda x: x != existing_value_to_modify
                ).mapped("value")
            )

        _debug.logic(
            "external_value_located",
            report=self,
            expression=target_expression,
            formula=target_expression.formula,
            company=company,
            date_scope=date_scope,
            date_to=date_to,
            existing=existing_value_to_modify,
            value_to_adjust=value_to_adjust,
        )
        if not new_value_str and target_expression.figure_type != "string":
            new_value_str = "0"

        try:
            float(new_value_str)
            is_number = True
        except ValueError:
            is_number = False

        if target_expression.figure_type == "string":
            value_to_set = new_value_str
        else:
            if not is_number:
                raise UserError(self.env._("%s is not a numeric value", new_value_str))
            if target_expression.figure_type == "boolean":
                rounding = 0
            value_to_set = float_round(
                float(new_value_str) - value_to_adjust, precision_digits=rounding
            )

        field_name = (
            "value" if target_expression.figure_type != "string" else "text_value"
        )

        _debug.logic(
            "external_value_write_mode",
            report=self,
            expression=target_expression,
            field_name=field_name,
            rounding=rounding,
            update_existing=bool(existing_value_to_modify),
        )
        if existing_value_to_modify:
            existing_value_to_modify[field_name] = value_to_set
            existing_value_to_modify.flush_recordset()
        else:
            self.env["report.formula.external.value"].create(
                {
                    "name": self.env._("Manual value"),
                    field_name: value_to_set,
                    "date": date_to,
                    "target_report_expression_id": target_expression.id,
                    "company_id": company.id,
                }
            )

    def _get_manual_value_date(self, options, date_scope, company):
        if date_scope == "to_beginning_of_fiscalyear":
            fiscal_year = self._get_fiscalyear_dates_by_company(
                options, options["date"]["date_to"]
            )[company.id]
            return fields.Date.to_string(
                fiscal_year["date_from"] - relativedelta(days=1)
            )
        return self._get_date_bounds_info(options, date_scope)[1]

    @_debug.perf.timed
    def _get_domain_audit_line(self, column_group_options, expression, params):
        groupby_domain = Domain(
            self._get_domain_audit_line_groupby(params["calling_line_dict_id"])
        )
        audit_or_domains_per_date_scope = defaultdict(list)
        for expression_to_audit in expression._expand_aggregations():
            expression_domain = self._get_domain_expression_audit(
                expression_to_audit, column_group_options
            )

            if expression_domain is None:
                continue

            date_scope = (
                expression.date_scope
                if expression.subformula
                and expression.subformula.startswith("cross_report")
                else expression_to_audit.date_scope
            )
            audit_or_domains_per_date_scope[date_scope].append(expression_domain)

        if _debug.logic.enabled:
            _debug.logic(
                "audit_domain_scopes",
                report=self,
                expression=expression,
                date_scopes=sorted(audit_or_domains_per_date_scope),
            )
        if audit_or_domains_per_date_scope:
            domain = Domain.OR(
                Domain.OR(audit_or_domains)
                & self._get_domain_options(column_group_options, date_scope)
                for date_scope, audit_or_domains in audit_or_domains_per_date_scope.items()
            )
        else:
            domain = self._get_domain_options(column_group_options, "strict_range")
        return domain & groupby_domain

    def _get_domain_expression_audit(self, expression_to_audit, options):
        if expression_to_audit.engine == "domain":
            return literal_eval(expression_to_audit.formula)
        return None

    def _get_domain_audit_line_groupby(self, calling_line_dict_id):
        parsed_line_dict_id = self._parse_line_id(calling_line_dict_id)
        groupby_domain = []
        for markup, _model, grouping_key in parsed_line_dict_id:
            if isinstance(markup, dict) and "groupby" in markup:
                groupby_field_name = markup["groupby"]
                custom_handler_model = self._get_custom_handler_model()
                if custom_handler_model and (
                    custom_groupby_data := self.env[custom_handler_model]
                    ._get_custom_groupby_map()
                    .get(groupby_field_name)
                ):
                    groupby_domain += custom_groupby_data["domain_builder"](
                        grouping_key
                    )
                else:
                    groupby_domain.append((groupby_field_name, "=", grouping_key))

        _debug.logic(
            "audit_groupby_domain",
            report=self,
            segments=len(parsed_line_dict_id),
            conditions=len(groupby_domain),
        )
        return groupby_domain
