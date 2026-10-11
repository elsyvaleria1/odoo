import re
from ast import literal_eval
from collections import defaultdict, deque
from itertools import chain

from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.libs.numbers import float_round
from odoo.tools import SQL, Query
from odoo.tools.safe_eval import expr_eval, safe_eval

_debug = DebugLog(__name__)


class AccountReportExpressionEval(models.Model):
    _inherit = "report.formula"

    def _get_expression_values(self, options, expressions=None, warnings=None):
        self.check_singleton()
        if expressions is None:
            expressions = self.line_ids.expression_ids
        self._init_currency_table(options)
        totals = self._compute_expression_totals_for_each_column_group(
            expressions, options, warnings=warnings
        )
        first_column_group = next(iter(totals.values()), {})
        return {
            expression: result.get("value")
            for expression, result in first_column_group.items()
        }

    @_debug.perf.timed
    def _compute_expression_totals_for_each_column_group(
        self,
        expressions,
        options,
        groupby_to_expand=None,
        forced_all_column_groups_expression_totals=None,
        col_groups_restrict=None,
        offset=0,
        limit=None,
        include_default_vals=False,
        warnings=None,
    ):
        engines_without_next_groupby = self._get_engines_without_next_groupby()

        def add_expressions_to_groups(
            expressions_to_add, grouped_formulas, force_date_scope=None
        ):
            for expression in expressions_to_add:
                engine = expression.engine

                if engine not in grouped_formulas:
                    grouped_formulas[engine] = {}

                date_scope = (
                    force_date_scope
                    or self._standardize_date_scope_for_date_range(
                        expression.date_scope
                    )
                )
                groupby_data = expression.report_line_id._parse_groupby(
                    options, groupby_to_expand=groupby_to_expand
                )

                next_groupby = (
                    groupby_data["next_groupby"]
                    if engine not in engines_without_next_groupby
                    else None
                )
                grouping_key = (
                    date_scope,
                    groupby_data["current_groupby"],
                    next_groupby,
                )

                if grouping_key not in grouped_formulas[engine]:
                    grouped_formulas[engine][grouping_key] = {}

                formula = expression.formula

                if (
                    expression.engine == "aggregation"
                    and expression.formula == "sum_children"
                ):
                    formula = " + ".join(
                        f"_expression:{child_expr.id}"
                        for child_expr in expression.report_line_id.children_ids.expression_ids.filtered(
                            lambda e, expression=expression: e.label == expression.label
                        )
                    )

                if formula not in grouped_formulas[engine][grouping_key]:
                    grouped_formulas[engine][grouping_key][formula] = expression
                else:
                    grouped_formulas[engine][grouping_key][formula] |= expression

        if groupby_to_expand and any(
            not expression.report_line_id._get_groupby(options)
            for expression in expressions
        ):
            raise UserError(
                self.env._(
                    "Trying to expand groupby results on lines without a groupby value."
                )
            )

        grouped_formulas = {}
        if expressions and not include_default_vals:
            expressions = expressions.filtered(
                lambda x: not x.label.startswith("_default")
            )
        for expression in expressions:
            add_expressions_to_groups(expression, grouped_formulas)

            if (
                expression.engine == "aggregation"
                and expression.subformula
                and expression.subformula.startswith("cross_report")
            ):
                expanded_cross = expression._expand_aggregations()
                forced_date_scope = self._standardize_date_scope_for_date_range(
                    expression.date_scope
                )
                add_expressions_to_groups(
                    expanded_cross, grouped_formulas, force_date_scope=forced_date_scope
                )

        if _debug.pipeline.enabled:
            _debug.pipeline(
                "formulas_grouped",
                report=self,
                expressions=len(expressions),
                groupby=groupby_to_expand,
                include_default_vals=include_default_vals,
                cross_report_expanded=sum(
                    1
                    for expression in expressions
                    if expression.engine == "aggregation"
                    and expression.subformula
                    and expression.subformula.startswith("cross_report")
                ),
                batches_per_engine={
                    engine: len(batches) for engine, batches in grouped_formulas.items()
                },
                column_groups=len(options.get("column_groups", {})),
                col_groups_restrict=col_groups_restrict,
                forced=bool(forced_all_column_groups_expression_totals),
                offset=offset,
                limit=limit,
            )

        all_column_groups_expression_totals = {}
        batch_ids_cache = {}
        for group_key, group_options in self._split_options_per_column_group(
            options
        ).items():
            if forced_all_column_groups_expression_totals:
                forced_column_group_totals = (
                    forced_all_column_groups_expression_totals.get(group_key, None)
                )
            else:
                forced_column_group_totals = None

            if _debug.logic.enabled and col_groups_restrict:
                _debug.logic(
                    "column_group_restricted",
                    report=self,
                    group_key=group_key,
                    computed=group_key in col_groups_restrict,
                    reused_forced=forced_column_group_totals is not None,
                )
            if not col_groups_restrict or group_key in col_groups_restrict:
                current_group_expression_totals = self._compute_expression_totals_for_single_column_group(
                    group_options,
                    grouped_formulas,
                    forced_column_group_expression_totals=forced_column_group_totals,
                    offset=offset,
                    limit=limit,
                    warnings=warnings,
                    batch_ids_cache=batch_ids_cache,
                )
            else:
                current_group_expression_totals = forced_column_group_totals

            all_column_groups_expression_totals[group_key] = (
                current_group_expression_totals
            )

        _debug.pipeline(
            "column_groups_totals_computed",
            report=self,
            column_groups=len(all_column_groups_expression_totals),
            batch_ids_cached=len(batch_ids_cache),
        )
        return all_column_groups_expression_totals

    @_debug.perf.timed
    def _compute_expression_totals_for_single_column_group(
        self,
        column_group_options,
        grouped_formulas,
        forced_column_group_expression_totals=None,
        offset=0,
        limit=None,
        warnings=None,
        batch_ids_cache=None,
    ):

        def update_expression_totals(
            formula_results,
            column_group_expression_totals,
            cross_report_expression_totals=None,
        ):
            _debug.logic(
                "totals_update",
                report=self,
                results=len(formula_results),
                integer_rounding=column_group_options.get("integer_rounding_enabled"),
                rounding_method=column_group_options.get("integer_rounding"),
                cross_report=cross_report_expression_totals is not None,
            )
            for (_key, expressions), result in formula_results.items():
                for expression in expressions:
                    subformula_error_format = self.env._(
                        'Invalid subformula in expression "%(expression)s" of line "%(line)s": %(subformula)s',
                        expression=expression.label,
                        line=expression.report_line_id.name,
                        subformula=expression.subformula,
                    )
                    if (
                        expression.engine not in ("aggregation", "external")
                        and expression.subformula
                    ):
                        result_value_key = expression.subformula
                    else:
                        result_value_key = "result"


                    if isinstance(result, list):
                        expression_value = []
                        sublines_info = set()
                        for key, result_dict in result:
                            if result_dict.get("has_sublines"):
                                sublines_info.add(key)
                            try:
                                expression_value.append(
                                    (key, safe_eval(result_value_key, result_dict))
                                )
                            except ValueError, SyntaxError:
                                raise UserError(subformula_error_format) from None
                    else:
                        try:
                            expression_value = safe_eval(result_value_key, result)
                            sublines_info = result.get("has_sublines", False)
                        except ValueError, SyntaxError:
                            raise UserError(subformula_error_format) from None

                    if column_group_options.get("integer_rounding_enabled"):
                        in_monetary_column = any(
                            col["expression_label"] == expression.label
                            for col in column_group_options["columns"]
                            if col["figure_type"] == "monetary"
                        )

                        if (
                            in_monetary_column and not expression.figure_type
                        ) or expression.figure_type == "monetary":
                            method = column_group_options["integer_rounding"]
                            if isinstance(expression_value, list):
                                expression_value = [
                                    (
                                        key,
                                        float_round(
                                            value,
                                            precision_digits=0,
                                            rounding_method=method,
                                        )
                                        if value is not None
                                        else value,
                                    )
                                    for key, value in expression_value
                                ]
                            else:
                                expression_value = float_round(
                                    expression_value,
                                    precision_digits=0,
                                    rounding_method=method,
                                )

                    expression_result = {
                        "value": expression_value,
                        "sublines_info": sublines_info,
                    }

                    if expression.report_line_id.report_id == self:
                        if expression in column_group_expression_totals:
                            raise UserError(
                                self.env._(
                                    "Expression labelled '%(label)s' of line '%(line)s' is being overwritten when computing the current report. "
                                    "Make sure the cross-report aggregations of this report only reference terms belonging to other reports.",
                                    label=expression.label,
                                    line=expression.report_line_id.name,
                                )
                            )
                        column_group_expression_totals[expression] = expression_result
                    elif cross_report_expression_totals is not None:
                        cross_report_expression_totals[expression] = expression_result

            _debug.pipeline(
                "totals_updated",
                report=self,
                totals=len(column_group_expression_totals),
                cross_report_totals=len(cross_report_expression_totals)
                if cross_report_expression_totals is not None
                else None,
            )

        column_group_expression_totals = (
            dict(forced_column_group_expression_totals)
            if forced_column_group_expression_totals
            else {}
        )
        cross_report_expr_totals_by_scope = {}
        batchable_engines = [
            selection_val[0]
            for selection_val in self.env["report.formula.expression"]
            ._fields["engine"]
            .selection
            if selection_val[0] != "aggregation"
        ]
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "column_group_started",
                report=self,
                column_group=column_group_options.get("owner_column_group"),
                date=column_group_options.get("date", {}).get("string"),
                forced_totals=len(column_group_expression_totals),
                batches_per_engine={
                    engine: len(grouped_formulas[engine])
                    for engine in batchable_engines
                    if grouped_formulas.get(engine)
                },
                aggregation_batches=len(grouped_formulas.get("aggregation", {})),
            )
        for engine in batchable_engines:
            for (
                date_scope,
                current_groupby,
                next_groupby,
            ), formulas_dict in grouped_formulas.get(engine, {}).items():
                formula_results = self._get_formula_batch(
                    column_group_options,
                    engine,
                    date_scope,
                    formulas_dict,
                    current_groupby,
                    next_groupby,
                    offset=offset,
                    limit=limit,
                    warnings=warnings,
                    batch_ids_cache=batch_ids_cache,
                )
                update_expression_totals(
                    formula_results,
                    column_group_expression_totals,
                    cross_report_expression_totals=cross_report_expr_totals_by_scope.setdefault(
                        date_scope, {}
                    ),
                )

        aggregation_formulas_dict = {}
        for (
            date_scope,
            _current_groupby,
            _next_groupby,
        ), formulas_dict in grouped_formulas.get("aggregation", {}).items():
            for formula, expressions in formulas_dict.items():
                for expression in expressions:
                    forced_date_scope = (
                        date_scope
                        if (
                            expression.subformula
                            and expression.subformula.startswith("cross_report")
                        )
                        or expression.report_line_id.report_id != self
                        else None
                    )
                    aggreation_formula_dict_key = (formula, forced_date_scope)
                    aggregation_formulas_dict.setdefault(
                        aggreation_formula_dict_key,
                        self.env["report.formula.expression"],
                    )
                    aggregation_formulas_dict[aggreation_formula_dict_key] |= expression

        if _debug.pipeline.enabled:
            _debug.pipeline(
                "aggregations_collected",
                report=self,
                batch_totals=len(column_group_expression_totals),
                cross_report_scopes=len(cross_report_expr_totals_by_scope),
                cross_report_totals=sum(
                    len(scope_totals)
                    for scope_totals in cross_report_expr_totals_by_scope.values()
                ),
                aggregation_formulas=len(aggregation_formulas_dict),
                forced_scope_formulas=sum(
                    1 for _formula, scope in aggregation_formulas_dict if scope
                ),
            )
        if aggregation_formulas_dict:
            aggregation_formula_results = self._get_totals_no_batch_aggregation(
                column_group_options,
                aggregation_formulas_dict,
                column_group_expression_totals,
                cross_report_expr_totals_by_scope,
            )
            update_expression_totals(
                aggregation_formula_results, column_group_expression_totals
            )

        _debug.pipeline(
            "column_group_totals_computed",
            report=self,
            column_group=column_group_options.get("owner_column_group"),
            totals=len(column_group_expression_totals),
        )
        return column_group_expression_totals

    @_debug.perf.timed
    def _get_totals_no_batch_aggregation(
        self,
        column_group_options,
        formulas_dict,
        other_current_report_expr_totals,
        other_cross_report_expr_totals_by_scope,
    ):

        def _resolve_subformula_on_dict(result, line_codes_expression_map, subformula):
            split_subformula = subformula.split(".")
            if len(split_subformula) > 1:
                line_code, expression_label = split_subformula
                return result[line_codes_expression_map[line_code][expression_label]]

            if subformula.startswith("_expression:"):
                expression_id = int(subformula.split(":")[1])
                return result[expression_id]

            raise KeyError

        def _is_float(to_test) -> bool:
            try:
                float(to_test)
                return True
            except ValueError:
                return False

        def add_expression_to_map(
            expression,
            expression_res,
            figure_types_cache,
            current_report_eval_dict,
            current_report_codes_map,
            other_reports_eval_dict,
            other_reports_codes_map,
            cross_report=False,
        ):

            expr_report = expression.report_line_id.report_id
            report_default_figure_types = figure_types_cache.setdefault(expr_report, {})
            expression_label = report_default_figure_types.get(
                expression.label, "_not_in_cache"
            )
            if expression_label == "_not_in_cache":
                report_default_figure_types[expression.label] = (
                    expr_report.column_ids.filtered(
                        lambda x: x.expression_label == expression.label
                    ).figure_type
                )

            default_figure_type = figure_types_cache[expr_report][expression.label]
            figure_type = expression.figure_type or default_figure_type
            value = expression_res["value"]
            if figure_type == "monetary" and value:
                value = self.env.company.currency_id.round(value)

            if cross_report:
                other_reports_eval_dict.setdefault(forced_date_scope, {})[
                    expression.id
                ] = value
            else:
                current_report_eval_dict[expression.id] = value

        current_report_eval_dict = {}
        other_reports_eval_dict = {}
        current_report_codes_map = {}
        other_reports_codes_map = {}

        figure_types_cache = {}
        for expression, expression_res in other_current_report_expr_totals.items():
            add_expression_to_map(
                expression,
                expression_res,
                figure_types_cache,
                current_report_eval_dict,
                current_report_codes_map,
                other_reports_eval_dict,
                other_reports_codes_map,
            )
            if expression.report_line_id.code:
                current_report_codes_map.setdefault(expression.report_line_id.code, {})[
                    expression.label
                ] = expression.id

        for (
            forced_date_scope,
            scope_expr_totals,
        ) in other_cross_report_expr_totals_by_scope.items():
            for expression, expression_res in scope_expr_totals.items():
                add_expression_to_map(
                    expression,
                    expression_res,
                    figure_types_cache,
                    current_report_eval_dict,
                    current_report_codes_map,
                    other_reports_eval_dict,
                    other_reports_codes_map,
                    True,
                )
                if expression.report_line_id.code:
                    other_reports_codes_map.setdefault(
                        forced_date_scope, {}
                    ).setdefault(expression.report_line_id.code, {})[
                        expression.label
                    ] = expression.id

        aggregations_terms_to_evaluate = set()
        for (formula, forced_date_scope), expressions in formulas_dict.items():
            for expression in expressions:
                aggregations_terms_to_evaluate.add(
                    f"_expression:{expression.id}"
                )

                if expression.report_line_id.code:
                    if expression.report_line_id.report_id == self:
                        current_report_codes_map.setdefault(
                            expression.report_line_id.code, {}
                        )[expression.label] = expression.id
                    else:
                        other_reports_codes_map.setdefault(
                            forced_date_scope, {}
                        ).setdefault(expression.report_line_id.code, {})[
                            expression.label
                        ] = expression.id

                    aggregations_terms_to_evaluate.add(
                        f"{expression.report_line_id.code}.{expression.label}"
                    )

                    if not expression.subformula:
                        if expression.report_line_id.report_id == self:
                            eval_dict = current_report_eval_dict
                        else:
                            eval_dict = other_reports_eval_dict.setdefault(
                                forced_date_scope, {}
                            )

                        eval_dict[expression.id] = formula

        rslt = {}
        to_treat = deque(
            (formula, formula, forced_date_scope)
            for (formula, forced_date_scope) in formulas_dict
        )
        term_separator_regex = r"(?<!\de)[+-]|[ ()/*]"
        term_replacement_regex = r"(^|(?<=[ ()+/*-]))%s((?=[ ()+/*-])|$)"
        max_expansion_rounds = (
            len(aggregations_terms_to_evaluate) + len(formulas_dict) + 1
        )
        expansion_rounds = defaultdict(int)
        _debug.pipeline(
            "aggregation_maps_built",
            report=self,
            formulas=len(formulas_dict),
            current_values=len(current_report_eval_dict),
            current_codes=len(current_report_codes_map),
            cross_report_scopes=len(other_reports_eval_dict),
            terms_to_evaluate=len(aggregations_terms_to_evaluate),
            max_expansion_rounds=max_expansion_rounds,
        )
        while to_treat:
            formula, unexpanded_formula, forced_date_scope = to_treat.popleft()

            expansion_rounds[unexpanded_formula, forced_date_scope] += 1
            if (
                expansion_rounds[unexpanded_formula, forced_date_scope]
                > max_expansion_rounds
            ):
                _debug.logic(
                    "cyclic_aggregation_detected",
                    report=self,
                    formula=unexpanded_formula,
                    date_scope=forced_date_scope,
                    max_expansion_rounds=max_expansion_rounds,
                )
                raise UserError(
                    self.env._(
                        "Cyclic aggregation: %(expressions)s cannot be computed, because its formula %(formula)s references expressions that reference it back.",
                        expressions=", ".join(
                            sorted(
                                f"{expression.report_line_name} > {expression.label}"
                                for expression in formulas_dict[
                                    unexpanded_formula, forced_date_scope
                                ]
                            )
                        ),
                        formula=unexpanded_formula,
                    )
                )

            full_eval_dict = {
                **current_report_eval_dict,
                **other_reports_eval_dict.get(forced_date_scope, {}),
            }
            full_codes_map = {
                **current_report_codes_map,
                **other_reports_codes_map.get(forced_date_scope, {}),
            }

            terms_to_eval = [
                term
                for term in re.split(term_separator_regex, formula)
                if term and not _is_float(term)
            ]
            if terms_to_eval:
                for term in terms_to_eval:
                    try:
                        expanded_term = _resolve_subformula_on_dict(
                            full_eval_dict,
                            full_codes_map,
                            term,
                        )
                    except KeyError:
                        if term in aggregations_terms_to_evaluate:
                            continue
                        _debug.logic(
                            "term_unresolvable",
                            report=self,
                            term=term,
                            formula=unexpanded_formula,
                            date_scope=forced_date_scope,
                        )
                        raise UserError(
                            self.env._(
                                "Could not expand term %(term)s while evaluating formula %(unexpanded_formula)s",
                                term=term,
                                unexpanded_formula=unexpanded_formula,
                            )
                        ) from None

                    formula = re.sub(
                        term_replacement_regex % re.escape(term),
                        f"({expanded_term})",
                        formula,
                    )
                to_treat.append((formula, unexpanded_formula, forced_date_scope))

            else:
                try:
                    formula_result = expr_eval(formula)
                except ZeroDivisionError:
                    for expr in formulas_dict[unexpanded_formula, forced_date_scope]:
                        if expr.subformula != "ignore_zero_division":
                            raise UserError(
                                self.env._(
                                    "Division by zero occurred while evaluating Expression: %(line_name)s > %(label)s.",
                                    line_name=expr.report_line_name,
                                    label=expr.label,
                                )
                            ) from None
                    _debug.logic(
                        "zero_division_ignored",
                        report=self,
                        formula=unexpanded_formula,
                        date_scope=forced_date_scope,
                    )
                    formula_result = 0

                for expression in formulas_dict[
                    (unexpanded_formula, forced_date_scope)
                ]:
                    if expression.subformula and expression.subformula.startswith(
                        "if_other_expr_"
                    ):
                        other_expr_criterium_match = re.match(
                            r"^(?P<criterium>\w+)\("
                            r"(?P<line_code>\w+)[.](?P<expr_label>\w+),[ ]*"
                            r"(?P<bound_params>.*)\)$",
                            expression.subformula,
                        )
                        if not other_expr_criterium_match:
                            raise UserError(
                                self.env._(
                                    "Wrong format for if_other_expr_above/if_other_expr_below formula: %s",
                                    expression.subformula,
                                )
                            )

                        criterium_code = other_expr_criterium_match["line_code"]
                        criterium_label = other_expr_criterium_match["expr_label"]
                        criterium_expression_id = full_codes_map.get(
                            criterium_code, {}
                        ).get(criterium_label)
                        criterium_val = full_eval_dict.get(criterium_expression_id)

                        if not criterium_expression_id:
                            raise UserError(
                                self.env._(
                                    "This subformula references an unknown expression: %s",
                                    expression.subformula,
                                )
                            )

                        if not isinstance(criterium_val, (float, int)):
                            _debug.logic(
                                "other_expr_criterium_postponed",
                                report=self,
                                expression=expression,
                                criterium_code=criterium_code,
                                criterium_label=criterium_label,
                            )
                            to_treat.append(
                                (formula, unexpanded_formula, forced_date_scope)
                            )
                            continue

                        bound_subformula = other_expr_criterium_match[
                            "criterium"
                        ].replace(
                            "other_expr_", ""
                        )
                        bound_params = other_expr_criterium_match["bound_params"]
                        bounded_value = self._aggregation_apply_bounds(
                            column_group_options,
                            f"{bound_subformula}({bound_params})",
                            criterium_val,
                        )
                        expression_result = formula_result * int(
                            bool(bounded_value is not None)
                        )
                    else:
                        expression_result = (
                            self._aggregation_apply_bounds(
                                column_group_options,
                                expression.subformula,
                                formula_result,
                            )
                            or 0
                        )

                    if column_group_options.get("integer_rounding_enabled"):
                        expression_result = float_round(
                            expression_result,
                            precision_digits=0,
                            rounding_method=column_group_options["integer_rounding"],
                        )

                    standardized_expression_scope = (
                        self._standardize_date_scope_for_date_range(
                            expression.date_scope
                        )
                    )
                    if (
                        forced_date_scope == standardized_expression_scope
                        or not forced_date_scope
                    ) and expression.report_line_id.report_id == self:
                        rslt[(unexpanded_formula, expression)] = {
                            "result": expression_result
                        }

                    if expression.report_line_id.report_id == self:
                        current_report_eval_dict[expression.id] = expression_result
                    else:
                        other_reports_eval_dict.setdefault(forced_date_scope, {})[
                            expression.id
                        ] = expression_result

        if _debug.pipeline.enabled:
            _debug.pipeline(
                "aggregations_resolved",
                report=self,
                results=len(rslt),
                rounds=sum(expansion_rounds.values()),
                deepest_rounds=max(expansion_rounds.values(), default=0),
                integer_rounding=column_group_options.get("integer_rounding_enabled"),
            )
        return rslt

    @_debug.perf.timed
    def _aggregation_apply_bounds(
        self, column_group_options, subformula, unbounded_value
    ):
        if not subformula:
            return unbounded_value

        if subformula and subformula.startswith("round"):
            matches = re.match(
                r"round\((?P<precision>-?\d+)(,\s*(?P<rounding_method>(HALF-UP|HALF-DOWN|HALF-EVEN|UP|DOWN)))?\)",
                subformula.replace(" ", ""),
            )
            if not matches:
                raise UserError(
                    self.env._(
                        "Invalid rounding subformula: %(subformula)s. Expected round(decimal_places) or round(decimal_places, ROUNDING-METHOD), with a method among HALF-UP, HALF-DOWN, HALF-EVEN, UP, DOWN.",
                        subformula=subformula,
                    )
                )
            precision = int(matches["precision"])
            rounding_method = matches["rounding_method"] or "HALF-DOWN"
            _debug.logic(
                "rounding_subformula_applied",
                report=self,
                precision=precision,
                rounding_method=rounding_method,
                negative_precision=precision < 0,
            )
            if precision < 0:
                precision_power = abs(precision)
                unbounded_value /= 10**precision_power
                unbounded_value = float_round(
                    unbounded_value, precision_digits=0, rounding_method=rounding_method
                )
                return unbounded_value * (10**precision_power)
            else:
                return float_round(
                    unbounded_value,
                    precision_digits=precision,
                    rounding_method=rounding_method,
                )

        if subformula != "ignore_zero_division" and not subformula.startswith(
            "cross_report"
        ):
            company_currency = self.env.company.currency_id
            date_to = column_group_options["date"]["date_to"]

            match = re.match(
                r"(?P<criterium>\w*)"
                r"\((?P<currency_1>[A-Z]{3})\((?P<amount_1>[-]?\d+(\.\d+)?)\)"
                r"(,(?P<currency_2>[A-Z]{3})\((?P<amount_2>[-]?\d+(\.\d+)?)\))?\)$",
                subformula.replace(" ", ""),
            )
            if not match:
                raise UserError(
                    self.env._(
                        "Invalid bound subformula: %(subformula)s. Expected if_above(CUR(amount)), if_below(CUR(amount)) or if_between(CUR(amount), CUR(amount)), with CUR an upper-case currency code.",
                        subformula=subformula,
                    )
                )
            group_values = match.groupdict()

            currency_code_1 = group_values.get("currency_1")
            currency_code_2 = group_values.get("currency_2")
            currency_codes = [
                currency_code
                for currency_code in [currency_code_1, currency_code_2]
                if currency_code and currency_code != company_currency.name
            ]

            if currency_codes:
                currencies = (
                    self.env["res.currency"]
                    .with_context(active_test=False)
                    .search([("name", "in", currency_codes)])
                )
                missing_codes = set(currency_codes) - set(currencies.mapped("name"))
                if missing_codes:
                    raise UserError(
                        self.env._(
                            "Unknown currency code in bound subformula %(subformula)s: %(codes)s.",
                            subformula=subformula,
                            codes=", ".join(sorted(missing_codes)),
                        )
                    )
            else:
                currencies = self.env["res.currency"]

            amount_1 = float(group_values["amount_1"] or 0)
            amount_2 = float(group_values["amount_2"] or 0)
            for currency in currencies:
                if currency != company_currency:
                    if currency.name == currency_code_1:
                        amount_1 = currency._convert(
                            amount_1, company_currency, self.env.company, date_to
                        )
                    if amount_2 and currency.name == currency_code_2:
                        amount_2 = currency._convert(
                            amount_2, company_currency, self.env.company, date_to
                        )

            criterium = group_values["criterium"]
            _debug.logic(
                "bound_evaluated",
                report=self,
                criterium=criterium,
                value=unbounded_value,
                amount_1=amount_1,
                amount_2=amount_2,
                converted_currencies=currency_codes,
            )
            if criterium == "if_below":
                if company_currency.compare_amounts(unbounded_value, amount_1) >= 0:
                    _debug.logic("below_bound_suppressed", report=self)
                    return None
            elif criterium == "if_above":
                if company_currency.compare_amounts(unbounded_value, amount_1) <= 0:
                    _debug.logic("above_bound_suppressed", report=self)
                    return None
            elif criterium == "if_between":
                if (
                    company_currency.compare_amounts(unbounded_value, amount_1) < 0
                    or company_currency.compare_amounts(unbounded_value, amount_2) > 0
                ):
                    _debug.logic("between_bound_suppressed", report=self)
                    return None
            else:
                raise UserError(self.env._("Unknown bound criterium: %s", criterium))

        return unbounded_value

    @_debug.perf.timed
    def _get_formula_batch(
        self,
        column_group_options,
        formula_engine,
        date_scope,
        formulas_dict,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
        batch_ids_cache=None,
    ):
        engine_function_name = f"_get_formula_batch_with_engine_{formula_engine}"
        with _debug.perf(
            "_get_formula_batch",
            cr=self.env.cr,
            report=self,
            engine=formula_engine,
            scope=date_scope,
            formulas=len(formulas_dict),
            groupby=current_groupby,
        ):
            return getattr(self, engine_function_name)(
                column_group_options,
                date_scope,
                formulas_dict,
                current_groupby,
                next_groupby,
                offset=offset,
                limit=limit,
                warnings=warnings,
                batch_ids_cache=batch_ids_cache,
            )

    @_debug.perf.timed
    def _get_formula_batch_with_engine_domain(
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
        def _format_result_depending_on_groupby(formula_rslt):
            if not current_groupby:
                if formula_rslt:
                    return formula_rslt[0][1]
                else:
                    return {
                        "sum": 0,
                        "sum_if_pos": 0,
                        "sum_if_neg": 0,
                        "count_rows": 0,
                        "has_sublines": False,
                    }
            return formula_rslt

        self._check_groupby_fields(
            (next_groupby.split(",") if next_groupby else [])
            + ([current_groupby] if current_groupby else [])
        )

        batchable_domains_data = {}
        non_batchable_domains_data = []
        for formula, expressions in formulas_dict.items():
            try:
                domain = literal_eval(formula)
            except ValueError, SyntaxError:
                raise UserError(
                    self.env._(
                        'Invalid domain formula in expression "%(expression)s" of line "%(line)s": %(formula)s',
                        expression=expressions[0].label,
                        line=expressions[0].report_line_id.name,
                        formula=formula,
                    )
                ) from None

            if (
                offset
                or limit
                or any(expr.subformula == "count_rows" for expr in expressions)
            ):
                non_batchable_domains_data.append((domain, formula, expressions))
                continue

            aml_root_fields = set()
            traversing_model_domain = []
            batchable = True
            for term in domain:
                match term:
                    case (aml_field_expr, operator, value):
                        aml_field, _dot, model_field_expr = aml_field_expr.partition(
                            "."
                        )
                        aml_root_fields.add(aml_field)
                        if not model_field_expr and not self._is_id_positive_condition(
                            operator, value
                        ):
                            batchable = False
                        traversing_model_domain.append(
                            (model_field_expr or "id", operator, value)
                        )
                    case str():
                        traversing_model_domain.append(term)

            if batchable and len(aml_root_fields) == 1:
                aml_field = self._get_required_source_model()._fields[
                    next(iter(aml_root_fields))
                ]
                if aml_field.type == "many2one":
                    batchable_domains_data.setdefault(
                        (aml_field.comodel_name, aml_field.name), []
                    ).append((traversing_model_domain, formula, expressions))
                else:
                    non_batchable_domains_data.append((domain, formula, expressions))
            else:
                non_batchable_domains_data.append((domain, formula, expressions))

        if _debug.logic.enabled:
            _debug.logic(
                "domains_batched",
                report=self,
                date_scope=date_scope,
                groupby=current_groupby,
                next_groupby=next_groupby,
                formulas=len(formulas_dict),
                batches=sorted(
                    f"{model}.{field}:{len(domains)}"
                    for (model, field), domains in batchable_domains_data.items()
                ),
                non_batchable=len(non_batchable_domains_data),
                paginated=bool(offset or limit),
            )

        folded_rows_by_formula = (
            {}
            if offset or limit
            else self._fetch_folded_domain_formulas(
                options, date_scope, current_groupby, non_batchable_domains_data
            )
        )

        rslt = {}
        for (batch_model, batch_aml_field), batch_domains in chain(
            batchable_domains_data.items(),
            (((None, None), [data]) for data in non_batchable_domains_data),
        ):
            if not batch_model and batch_domains[0][1] in folded_rows_by_formula:
                counts_rows = False
                all_query_res = folded_rows_by_formula[batch_domains[0][1]]
            else:
                counts_rows, all_query_res = self._fetch_domain_batch_rows(
                    options,
                    date_scope,
                    current_groupby,
                    next_groupby,
                    offset,
                    limit,
                    batch_model,
                    batch_aml_field,
                    batch_domains,
                )

            results_by_batch_grouping_key = {}
            if batch_model:
                for query_res in all_query_res:
                    results_by_batch_grouping_key.setdefault(
                        query_res["batch_grouping_key"], []
                    ).append(query_res)

            for domain, formula, expressions in batch_domains:
                formula_rslt = []
                total_sum = 0
                totals_by_grouping_key = {}

                batch_included_ids = self._get_batch_model_ids(
                    batch_model, domain, batch_ids_cache
                )
                for batch_included_id in batch_included_ids:
                    batch_res = (
                        results_by_batch_grouping_key.get(batch_included_id, [])
                        if batch_included_id is not None
                        else all_query_res
                    )

                    for query_res in batch_res:
                        totals = totals_by_grouping_key.setdefault(
                            query_res.get("grouping_key"),
                            {
                                "sum": 0,
                                "sum_if_pos": 0,
                                "sum_if_neg": 0,
                                "count_rows": 0,
                                "has_sublines": False,
                            },
                        )

                        res_sum = query_res["sum"]
                        totals["sum"] += res_sum
                        if counts_rows:
                            totals["count_rows"] += query_res["count_rows"]
                        totals["has_sublines"] = totals["has_sublines"] or bool(
                            query_res["row_count"]
                        )

                        total_sum += res_sum

                for grouping_key, totals in totals_by_grouping_key.items():
                    formula_rslt.append((grouping_key, totals))

                expressions_by_sign_policy = defaultdict(
                    lambda: self.env["report.formula.expression"]
                )
                for expression in expressions:
                    subformula_without_sign = expression.subformula.replace(
                        "-", ""
                    ).strip()
                    if subformula_without_sign in ("sum_if_pos", "sum_if_neg"):
                        expressions_by_sign_policy[subformula_without_sign] += (
                            expression
                        )
                    else:
                        expressions_by_sign_policy["no_sign_check"] += expression

                if (
                    expressions_by_sign_policy["sum_if_pos"]
                    or expressions_by_sign_policy["sum_if_neg"]
                ):
                    sign_policy_with_value = (
                        "sum_if_pos"
                        if self.env.company.currency_id.compare_amounts(total_sum, 0.0)
                        >= 0
                        else "sum_if_neg"
                    )

                    formula_rslt_with_sign = [
                        (
                            grouping_key,
                            {**totals, sign_policy_with_value: totals["sum"]},
                        )
                        for grouping_key, totals in formula_rslt
                    ]

                    for sign_policy in ("sum_if_pos", "sum_if_neg"):
                        policy_expressions = expressions_by_sign_policy[sign_policy]

                        if policy_expressions:
                            if sign_policy == sign_policy_with_value:
                                rslt[formula, policy_expressions] = (
                                    _format_result_depending_on_groupby(
                                        formula_rslt_with_sign
                                    )
                                )
                            else:
                                rslt[formula, policy_expressions] = (
                                    _format_result_depending_on_groupby([])
                                )

                if expressions_by_sign_policy["no_sign_check"]:
                    rslt[formula, expressions_by_sign_policy["no_sign_check"]] = (
                        _format_result_depending_on_groupby(formula_rslt)
                    )

        _debug.pipeline(
            "domain_results",
            report=self,
            results=len(rslt),
            batch_ids_cached=len(batch_ids_cache)
            if batch_ids_cache is not None
            else None,
        )
        return rslt

    def _fetch_domain_batch_rows(
        self,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset,
        limit,
        batch_model,
        batch_aml_field,
        batch_domains,
    ):
        aml_domain = batch_domains[0][0] if not batch_model else None
        query = self._get_report_query(options, date_scope, domain=aml_domain)
        source_model = self._get_required_source_model()
        source_alias = query.table

        groupby_sql = (
            source_model._field_to_sql(source_alias, current_groupby, query)
            if current_groupby
            else None
        )
        batch_groupby_sql = (
            source_model._field_to_sql(source_alias, batch_aml_field, query)
            if batch_aml_field
            else None
        )

        counts_rows = any(
            expression.subformula == "count_rows"
            for _domain, _formula, expressions in batch_domains
            for expression in expressions
        )
        if counts_rows:
            count_field = source_model._field_to_sql(
                source_alias,
                next_groupby.split(",")[0] if next_groupby else "id",
                query,
            )
            count_rows_select = SQL(
                ", COUNT(DISTINCT %(field)s) + (CASE WHEN COUNT(*) FILTER (WHERE %(field)s IS NULL) > 0 THEN 1 ELSE 0 END) AS count_rows",
                field=count_field,
            )
        else:
            count_rows_select = SQL()

        tail_query = self._get_engine_query_tail(offset, limit)
        query = SQL(
            """
            SELECT
                COALESCE(SUM(%(balance_select)s), 0.0) AS sum,
                COUNT(*) AS row_count
                %(count_rows_select)s
                %(select_groupby_sql)s
                %(select_batch_groupby_sql)s
            FROM %(table_references)s
            %(currency_table_join)s
            WHERE %(search_condition)s
            %(groupby_sql)s
            %(order_by_sql)s
            %(tail_query)s
            """,
            count_rows_select=count_rows_select,
            select_groupby_sql=SQL(", %s AS grouping_key", groupby_sql)
            if groupby_sql
            else SQL(),
            select_batch_groupby_sql=SQL(
                ", %s AS batch_grouping_key", batch_groupby_sql
            )
            if batch_groupby_sql
            else SQL(),
            table_references=query.from_clause,
            balance_select=self._currency_table_apply_rate(
                SQL.identifier(source_alias, self._get_source_measure_field())
            ),
            currency_table_join=self._currency_table_aml_join(options),
            search_condition=query.where_clause,
            groupby_sql=SQL(
                "GROUP BY %s",
                SQL(",").join(
                    groupby_term
                    for groupby_term in (groupby_sql, batch_groupby_sql)
                    if groupby_term
                ),
            )
            if groupby_sql or batch_groupby_sql
            else SQL(),
            order_by_sql=SQL(" ORDER BY %s", groupby_sql) if groupby_sql else SQL(),
            tail_query=tail_query,
        )

        self.env.cr.execute(query)
        all_query_res = self.env.cr.dictfetchall()
        _debug.perf.count(
            "domain_rows_fetched",
            report=self,
            batch_model=batch_model,
            batch_field=batch_aml_field,
            domains=len(batch_domains),
            rows=len(all_query_res),
        )
        return counts_rows, all_query_res

    def _is_row_local_domain(self, model, domain, nested=False):
        if (
            not nested
            and not domain.map_conditions(lambda _condition: Domain.TRUE).is_true()
        ):
            return False
        for condition in domain.iter_conditions():
            comodel = model
            for field_name in condition.field_expr.split("."):
                field = comodel._fields.get(field_name)
                if field is None or field.type == "one2many":
                    return False
                if field.type in ("many2one", "many2many"):
                    comodel = comodel.env[field.comodel_name]
            if isinstance(condition.value, Domain) and not self._is_row_local_domain(
                comodel, condition.value, nested=True
            ):
                return False
        return True

    def _fetch_folded_domain_formulas(
        self, options, date_scope, current_groupby, domains_data
    ):
        source_model = self._with_report_query_context(
            options
        )._get_required_source_model()
        formulas = []
        foldable = []
        for domain, formula, expressions in domains_data:
            if any(expression.subformula == "count_rows" for expression in expressions):
                continue
            index = len(formulas)
            formulas.append((domain, formula))
            condition = self._adapt_report_query_domain(
                options, Domain(domain)
            ).optimize_full(source_model)
            if not source_model._active_name and self._is_row_local_domain(
                source_model, condition
            ):
                foldable.append((index, condition))
        if len(formulas) < 2:
            return {}

        branches = {
            index: self._domain_formula_scan_sql(
                options, date_scope, current_groupby, index, domain
            )
            for index, (domain, _formula) in enumerate(formulas)
        }
        folded_indexes = []
        if len(foldable) >= 2 and (
            fold := self._folded_domain_scan_sql(
                options, date_scope, current_groupby, foldable
            )
        ):
            fold_cost, *branch_costs = self._get_statement_costs(
                [fold, *(branches[index] for index, _condition in foldable)]
            )
            folded = [
                (index, cost)
                for (index, _condition), cost in zip(
                    foldable, branch_costs, strict=True
                )
                if cost * len(foldable) >= fold_cost
            ]
            if len(folded) >= 2 and sum(cost for _index, cost in folded) > fold_cost:
                folded_indexes = [index for index, _cost in folded]
        parts = [branches[index] for index in branches if index not in folded_indexes]
        if folded_indexes:
            parts.insert(
                0,
                fold
                if len(folded_indexes) == len(foldable)
                else self._folded_domain_scan_sql(
                    options,
                    date_scope,
                    current_groupby,
                    [
                        (index, condition)
                        for index, condition in foldable
                        if index in folded_indexes
                    ],
                ),
            )
        rows = self.env.execute_query_dict(
            SQL(
                "SELECT * FROM (%s) AS scans ORDER BY formula_index%s",
                SQL(" UNION ALL ").join(SQL("(%s)", part) for part in parts),
                SQL(", grouping_key") if current_groupby else SQL(),
            )
        )
        _debug.perf.count(
            "domain_formulas_folded",
            report=self,
            formulas=len(formulas),
            shared_scan=len(folded_indexes),
            rows=len(rows),
        )
        rows_by_formula = {formula: [] for _domain, formula in formulas}
        for row in rows:
            if current_groupby and not row["row_count"]:
                continue
            rows_by_formula[formulas[row["formula_index"]][1]].append(
                {
                    "sum": row["sum"],
                    "row_count": row["row_count"],
                    "grouping_key": row.get("grouping_key"),
                }
            )
        return rows_by_formula

    def _domain_formula_scan_sql(
        self, options, date_scope, current_groupby, index, domain
    ):
        query = self._get_report_query(options, date_scope, domain=domain)
        source_model = self._get_required_source_model()
        groupby_sql = (
            source_model._field_to_sql(query.table, current_groupby, query)
            if current_groupby
            else None
        )
        return SQL(
            """
            SELECT %(index)s AS formula_index,
                   COALESCE(SUM(%(balance)s), 0.0) AS sum,
                   COUNT(*) AS row_count
                   %(select_groupby)s
            FROM %(table_references)s
            %(currency_table_join)s
            WHERE %(search_condition)s
            %(groupby)s
            """,
            index=SQL(str(int(index))),
            balance=self._currency_table_apply_rate(
                SQL.identifier(query.table, self._get_source_measure_field())
            ),
            select_groupby=SQL(", %s AS grouping_key", groupby_sql)
            if groupby_sql
            else SQL(),
            table_references=query.from_clause,
            currency_table_join=self._currency_table_aml_join(options),
            search_condition=query.where_clause,
            groupby=SQL("GROUP BY %s", groupby_sql) if groupby_sql else SQL(),
        )

    def _folded_domain_scan_sql(self, options, date_scope, current_groupby, foldable):
        source_model = self._with_report_query_context(
            options
        )._get_required_source_model()
        query = self._get_report_query(options, date_scope)
        source_alias = query.table
        base_joins = set(query._joins)
        with query.per_row_conditions():
            conditions = [
                (
                    index,
                    SQL("TRUE")
                    if condition.is_true()
                    else SQL("FALSE")
                    if condition.is_false()
                    else condition._to_sql(source_model, source_alias, query),
                )
                for index, condition in foldable
            ]
        if any(
            not kind.code.startswith("LEFT")
            for alias, (kind, _table, _condition) in query._joins.items()
            if alias not in base_joins
        ):
            return None
        groupby_sql = (
            source_model._field_to_sql(source_alias, current_groupby, query)
            if current_groupby
            else None
        )
        balance = self._currency_table_apply_rate(
            SQL.identifier(source_alias, self._get_source_measure_field())
        )
        return SQL(
            """
            SELECT unfolded.formula_index, unfolded.sum, unfolded.row_count
                   %(select_grouping_key)s
            FROM (
                SELECT %(aggregates)s %(select_groupby)s
                FROM %(table_references)s
                %(currency_table_join)s
                WHERE %(search_condition)s
                %(groupby)s
            ) AS folded
            CROSS JOIN LATERAL (VALUES %(values)s) AS unfolded(formula_index, sum, row_count)
            """,
            select_grouping_key=SQL(", folded.grouping_key") if groupby_sql else SQL(),
            aggregates=SQL(", ").join(
                SQL(
                    "COALESCE(SUM(%(balance)s) FILTER (WHERE %(condition)s), 0.0) AS %(sum)s,"
                    " COUNT(*) FILTER (WHERE %(condition)s) AS %(row_count)s",
                    balance=balance,
                    condition=condition,
                    sum=SQL.identifier(f"sum_{index}"),
                    row_count=SQL.identifier(f"row_count_{index}"),
                )
                for index, condition in conditions
            ),
            select_groupby=SQL(", %s AS grouping_key", groupby_sql)
            if groupby_sql
            else SQL(),
            table_references=query.from_clause,
            currency_table_join=self._currency_table_aml_join(options),
            search_condition=query.where_clause,
            groupby=SQL("GROUP BY %s", groupby_sql) if groupby_sql else SQL(),
            values=SQL(", ").join(
                SQL(
                    "(%s, folded.%s, folded.%s)",
                    SQL(str(int(index))),
                    SQL.identifier(f"sum_{index}"),
                    SQL.identifier(f"row_count_{index}"),
                )
                for index, _condition in conditions
            ),
        )

    def _get_statement_costs(self, statements):
        [[plan]] = self.env.execute_query(
            SQL(
                "EXPLAIN (FORMAT JSON) %s",
                SQL(" UNION ALL ").join(
                    SQL("(%s)", statement) for statement in statements
                ),
            )
        )
        append = plan[0]["Plan"]
        while append["Node Type"] != "Append":
            [append] = append["Plans"]
        return [
            child["Total Cost"]
            for child in append["Plans"]
            if child.get("Parent Relationship") == "Member"
        ]

    @_debug.perf.timed
    def _get_formula_batch_with_engine_external(
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

        if current_groupby or next_groupby or offset or limit:
            raise UserError(
                self.env._(
                    "'external' engine does not support groupby, limit nor offset."
                )
            )

        external_value_domain = self._get_date_scope_domain(
            options, date_scope
        ) & Domain("company_id", "in", self.get_report_company_ids(options))
        _debug.logic(
            "external_date_scope",
            report=self,
            date_scope=date_scope,
            domain=external_value_domain,
        )

        where_clause = (
            self.env["report.formula.external.value"]
            ._search(external_value_domain, bypass_access=True)
            .where_clause
        )

        num_queries = []
        string_queries = []
        monetary_queries = []
        for formula, expressions in formulas_dict.items():
            for expression in expressions:
                expression_where = SQL(
                    "%s AND report_formula_external_value.target_report_expression_id = %s",
                    where_clause,
                    expression.id,
                )
                if expression.figure_type == "string":
                    string_queries.append(
                        SQL(
                            """
                            SELECT %s, text_value
                            FROM report_formula_external_value
                            WHERE %s
                            ORDER BY date DESC, id DESC
                            LIMIT 1
                            """,
                            expression.id,
                            expression_where,
                        )
                    )
                    continue
                if formula == "most_recent":
                    expression_where = SQL(
                        "%s AND %s",
                        expression_where,
                        self._get_external_values_latest_per_company(expression_where),
                    )
                if expression.figure_type == "monetary":
                    monetary_queries.append(
                        SQL(
                            """
                            SELECT %s, COALESCE(SUM(COALESCE(%s, 0)), 0)
                            FROM report_formula_external_value
                                %s
                            WHERE %s
                            """,
                            expression.id,
                            self._currency_table_apply_rate(
                                SQL("CAST(value AS numeric)")
                            ),
                            self._currency_table_external_value_join(options),
                            expression_where,
                        )
                    )
                else:
                    num_queries.append(
                        SQL(
                            """
                            SELECT %s, SUM(COALESCE(value, 0))
                            FROM report_formula_external_value
                            WHERE %s
                            """,
                            expression.id,
                            expression_where,
                        )
                    )

        _debug.pipeline(
            "external_queries_built",
            report=self,
            formulas=len(formulas_dict),
            numeric=len(num_queries),
            string=len(string_queries),
            monetary=len(monetary_queries),
        )
        query_results_dict = {}
        for query_list in (num_queries, string_queries, monetary_queries):
            if query_list:
                query_results = self.env.execute_query(
                    SQL(" UNION ALL ").join(SQL("(%s)", query) for query in query_list)
                )
                query_results_dict.update(dict(query_results))
        _debug.perf.count(
            "external_values_fetched", report=self, rows=len(query_results_dict)
        )

        rslt = {}
        for formula, expressions in formulas_dict.items():
            for expression in expressions:
                expression_value = query_results_dict.get(expression.id)
                expression_value = expression_value or (
                    "" if expression.figure_type == "string" else 0.0
                )
                rslt[(formula, expression)] = {
                    "result": expression_value,
                    "has_sublines": False,
                }

        return rslt

    def _get_external_values_latest_per_company(self, where_clause) -> SQL:
        return SQL(
            """
            (report_formula_external_value.company_id, report_formula_external_value.date) IN (
                SELECT company_id, MAX(date)
                FROM report_formula_external_value
                WHERE %s
                GROUP BY company_id
            )
            """,
            where_clause,
        )

    @_debug.perf.timed
    def _get_formula_batch_with_engine_custom(
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

        rslt = {}
        for formula, expressions in formulas_dict.items():
            custom_engine_function = self._get_custom_report_function(
                formula, "custom_engine"
            )
            rslt[(formula, expressions)] = custom_engine_function(
                expressions,
                options,
                date_scope,
                current_groupby,
                next_groupby,
                offset=offset,
                limit=limit,
                warnings=warnings,
            )
        _debug.pipeline(
            "custom_engine_results",
            report=self,
            date_scope=date_scope,
            groupby=current_groupby,
            formulas=len(formulas_dict),
            results=len(rslt),
        )
        return rslt

    def _get_engines_without_next_groupby(self):
        return frozenset()

    def _currency_table_apply_rate(self, value: SQL) -> SQL:
        return value

    def _currency_table_aml_join(self, options, aml_alias=None) -> SQL:
        return SQL()

    def _currency_table_external_value_join(self, options) -> SQL:
        return SQL()

    def _with_report_query_context(self, options):
        return self

    @_debug.perf.timed
    def _get_report_query(self, options, date_scope, domain=None) -> Query:
        _debug.logic(
            "report_query_scope",
            report=self,
            date_scope=date_scope,
            extra_domain=domain is not None,
            budget=options.get("compute_budget"),
        )
        domain = self._get_domain_options(options, date_scope) & Domain(
            domain or Domain.TRUE
        )

        domain = self._adapt_report_query_domain(options, domain)
        query = self._get_required_source_model()._search(domain)

        self._adapt_report_query(options, query)
        return query

    def _adapt_report_query_domain(self, options, domain):
        return domain

    def _adapt_report_query(self, options, query):
        return

    def _get_engine_query_tail(self, offset, limit) -> SQL:
        query_tail = SQL()

        if offset:
            query_tail = SQL("%s OFFSET %s", query_tail, offset)

        if limit:
            query_tail = SQL("%s LIMIT %s", query_tail, limit)

        return query_tail

    def _get_batch_model_ids(self, batch_model, domain, batch_ids_cache=None):
        if not batch_model:
            return [None]

        cache_key = (batch_model, repr(domain))
        if batch_ids_cache is not None and cache_key in batch_ids_cache:
            _debug.perf.count(
                "batch_ids_cache_hit",
                rows=len(batch_ids_cache[cache_key]),
                batch_model=batch_model,
            )
            return batch_ids_cache[cache_key]

        ids = self.env[batch_model].with_context(active_test=False).search(domain).ids
        _debug.perf.count(
            "batch_ids_searched",
            rows=len(ids),
            batch_model=batch_model,
            cached=batch_ids_cache is not None,
        )
        if batch_ids_cache is not None:
            batch_ids_cache[cache_key] = ids
        return ids

    @api.model
    def _is_id_positive_condition(self, operator, value) -> bool:
        if operator == "=":
            return isinstance(value, int) and not isinstance(value, bool)
        if operator == "in":
            return isinstance(value, (list, tuple, set)) and all(
                isinstance(v, int) and not isinstance(v, bool) for v in value
            )
        return False

    @_debug.perf.timed
    def _check_groupby_fields(self, groupby_fields_name: list[str] | str):
        self.check_singleton()
        if isinstance(groupby_fields_name, str | bool):
            groupby_fields_name = (
                groupby_fields_name.split(",") if groupby_fields_name else []
            )

        custom_handler_name = self._get_custom_handler_model()
        _debug.logic(
            "groupby_fields_checking",
            report=self,
            fields=groupby_fields_name,
            custom_handler=custom_handler_name,
        )

        source_model = self._get_required_source_model()
        for field_name in (fname.strip() for fname in groupby_fields_name):
            groupby_field = source_model._fields.get(field_name)
            if groupby_field:
                if not groupby_field._description_searchable:
                    raise UserError(
                        self.env._(
                            "Field %(field)s of %(model)s is not searchable and can therefore not be used in a groupby expression.",
                            field=field_name,
                            model=source_model._name,
                        )
                    )
                try:
                    source_model._field_to_sql(
                        source_model._table,
                        field_name,
                        Query(self.env, source_model._table),
                    )
                except ValueError:
                    raise UserError(
                        self.env._(
                            "Field %(field)s of %(model)s cannot be used in a groupby expression.",
                            field=field_name,
                            model=source_model._name,
                        )
                    ) from None
            elif custom_handler_name:
                if (
                    field_name
                    not in self.env[custom_handler_name]._get_custom_groupby_map()
                ):
                    raise UserError(
                        self.env._(
                            "Field %(field)s does not exist on %(model)s, and is not supported by this report's custom handler.",
                            field=field_name,
                            model=source_model._name,
                        )
                    )
            else:
                raise UserError(
                    self.env._(
                        "Field %(field)s does not exist on %(model)s.",
                        field=field_name,
                        model=source_model._name,
                    )
                )
