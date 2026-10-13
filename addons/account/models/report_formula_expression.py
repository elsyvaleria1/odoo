import re
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog

from odoo.addons.account.tools.report_engines import (
    LEDGER_ENGINES,
    AccountCodesFormulaError,
    parse_account_codes_formula,
)

_debug = DebugLog(__name__)


class AccountReportExpression(models.Model):
    _inherit = "report.formula.expression"

    engine = fields.Selection(
        selection_add=[
            ("domain",),
            ("tax_tags", "Tax Tags"),
            ("aggregation",),
            ("account_codes", "Prefix of Account Codes"),
        ],
        ondelete={"tax_tags": "cascade", "account_codes": "cascade"},
    )
    date_scope = fields.Selection(
        selection_add=[("previous_return_period", "From previous return period")],
        ondelete={"previous_return_period": "set default"},
    )
    carryover_target = fields.Char(
        string="Carry Over To",
        help="Formula in the form line_code.expression_label. This allows setting the target of the carryover for this expression "
        "(on a _carryover_*-labeled expression), in case it is different from the parent line.",
    )

    def _get_auditable_engines(self):
        return super()._get_auditable_engines() | LEDGER_ENGINES

    @api.constrains("engine", "formula")
    def _check_formula_account_codes(self) -> None:
        report = self.env["report.formula"]
        tag_ids_by_expression = {}
        for expression in self.filtered(lambda x: x.engine == "account_codes"):
            try:
                terms = parse_account_codes_formula(expression.formula)
            except AccountCodesFormulaError:
                expression._raise_formula_error()
            tag_ids_by_expression[expression] = {
                tag.token: report._resolve_account_codes_tag(tag)
                for term in terms
                for tag in term.tags
            }
        existing = set(
            self.env["account.account.tag"]
            .browse(
                [
                    tag_id
                    for tag_ids in tag_ids_by_expression.values()
                    for tag_id in tag_ids.values()
                    if tag_id
                ]
            )
            .exists()
            .ids
        )
        for expression, tag_ids in tag_ids_by_expression.items():
            missing = [
                prefix for prefix, tag_id in tag_ids.items() if tag_id not in existing
            ]
            if not missing:
                continue
            _debug.logic(
                "account_codes_formula_tag_missing", expression=expression, tags=missing
            )
            raise ValidationError(
                self.env._(
                    "The formula of expression '%(label)s' on line '%(line)s' names "
                    "account tags that do not exist: %(tags)s. Install the module "
                    "defining them, or create them, before the report that reads "
                    "them.",
                    label=expression.label,
                    line=expression.report_line_name,
                    tags=", ".join(missing),
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        result.filtered(lambda x: x.engine == "tax_tags")._create_missing_tax_tags()
        return result

    def write(self, vals):
        self._strip_formula_vals(vals)

        tax_tags_expressions = self.filtered(lambda x: x.engine == "tax_tags")
        _debug.logic(
            "tax_tags_engine_change",
            records=self,
            tax_tags_expressions=tax_tags_expressions,
            new_engine=vals.get("engine"),
            formula_changed="formula" in vals,
        )

        if vals.get("engine") == "tax_tags":
            (self - tax_tags_expressions)._create_missing_tax_tags(
                formula_override=vals.get("formula")
            )

        if vals.get("engine") and vals["engine"] != "tax_tags":
            tax_tags_expressions._release_tax_tags()

        if "formula" not in vals or (
            vals.get("engine") and vals["engine"] != "tax_tags"
        ):
            _debug.logic(
                "tag_rename_skipped", records=self, reason="no_tax_tags_formula"
            )
            return super().write(vals)

        former_formulas_by_country = defaultdict(list)
        for expr in tax_tags_expressions:
            former_formulas_by_country[expr.report_line_id.report_id.country_id].append(
                expr.formula
            )

        result = super().write(vals)
        new_formula = vals["formula"]
        tag_model = self.env["account.account.tag"]
        for country, former_formulas_list in former_formulas_by_country.items():
            new_tag_exists = bool(tag_model._get_tax_tags(new_formula, country.id))
            _debug.logic(
                "tag_rename_country",
                records=self,
                country=country,
                new_tag_exists=new_tag_exists,
                former_formulas=len(former_formulas_list),
            )
            for former_formula in former_formulas_list:
                if new_tag_exists:
                    break
                former_tax_tags = tag_model._get_tax_tags(former_formula, country.id)
                if former_tax_tags and all(
                    tag_expr in self
                    for tag_expr in former_tax_tags._get_related_tax_report_expressions()
                ):
                    former_tax_tags._update_field_translations(
                        "name", {"en_US": new_formula.lstrip("-")}
                    )
                    _debug.logic(
                        "former_tag_renamed", records=self, tags=former_tax_tags
                    )
                else:
                    _debug.logic(
                        "new_tag_created",
                        records=self,
                        country=country,
                        shared_former_tags=former_tax_tags,
                    )
                    tag_model.create(self._prepare_tag_vals(new_formula, country.id))
                new_tag_exists = True

        return result

    @api.constrains("carryover_target", "label")
    @_debug.perf.timed
    def _check_carryover_target(self) -> None:
        for expression in self:
            if not expression.carryover_target:
                continue
            if not expression.label.startswith("_carryover_"):
                _debug.logic(
                    "carryover_target_rejected",
                    expression=expression,
                    label=expression.label,
                    reason="label_prefix",
                )
                raise ValidationError(
                    self.env._(
                        "You cannot use the field carryover_target in an expression that does not have the label starting with _carryover_"
                    )
                )
            _line_code, target_label = expression._parse_carryover_target()
            if not target_label.startswith("_applied_carryover_"):
                _debug.logic(
                    "carryover_target_label_rejected",
                    expression=expression,
                    target_label=target_label,
                )
                raise ValidationError(
                    self.env._(
                        "When targeting an expression for carryover, the label of that expression must start with _applied_carryover_"
                    )
                )

    def _parse_carryover_target(self) -> tuple:
        self.check_singleton()
        parts = self.carryover_target.split(".")
        if len(parts) != 2 or not all(parts):
            raise ValidationError(
                self.env._(
                    "The carryover target of expression '%(label)s' must have the form "
                    "'line_code.expression_label', but is '%(target)s'.",
                    label=self.label,
                    target=self.carryover_target,
                )
            )
        return parts[0], parts[1]

    def _tax_tag_key(self) -> tuple:
        self.check_singleton()
        return (
            self.formula.lstrip("-"),
            self.report_line_id.report_id.country_id.id,
        )

    @api.model
    @_debug.perf.timed
    def _search_tax_tags(self, tag_keys):
        tag_model = self.env["account.account.tag"]
        if not tag_keys:
            return tag_model
        return tag_model.with_context(active_test=False, lang="en_US").search(
            Domain.OR(
                Domain(tag_model._get_domain_tax_tags(tag_name, country_id))
                for tag_name, country_id in tag_keys
            )
        )

    @_debug.perf.timed
    def _create_missing_tax_tags(self, formula_override=None) -> None:
        wanted_keys = set()
        for expression in self:
            tag_name, country_id = expression._tax_tag_key()
            if formula_override:
                tag_name = formula_override.lstrip("-")
            wanted_keys.add((tag_name, country_id))
        existing_keys = {
            (tag.name, tag.country_id.id) for tag in self._search_tax_tags(wanted_keys)
        }
        tags_create_vals = [
            tag_vals
            for tag_name, country_id in sorted(
                wanted_keys - existing_keys, key=lambda key: (key[0], key[1] or 0)
            )
            for tag_vals in self._prepare_tag_vals(tag_name, country_id)
        ]
        _debug.pipeline(
            "missing_tax_tags_resolved",
            expressions=self,
            wanted=len(wanted_keys),
            existing=len(existing_keys),
            to_create=len(tags_create_vals),
            formula_override=bool(formula_override),
        )
        if tags_create_vals:
            self.env["account.account.tag"].create(tags_create_vals)

    @api.ondelete(at_uninstall=False)
    @_debug.perf.timed
    def _unlink_archive_used_tags(self) -> None:
        _debug.lifecycle("_unlink_archive_used_tags", records=self)
        self._release_tax_tags()

    @_debug.perf.timed
    def _release_tax_tags(self) -> None:
        expressions_tags = self._get_matching_tags().with_context(lang="en_US")
        if not expressions_tags:
            _debug.logic("tag_release_skipped", records=self, reason="no_matching_tags")
            return

        still_referenced_keys = {
            expression._tax_tag_key()
            for expression in expressions_tags.sudo()._get_related_tax_report_expressions()
            - self
        }
        orphan_tags = expressions_tags.filtered(
            lambda tag: (tag.name, tag.country_id.id) not in still_referenced_keys
        )
        if not orphan_tags:
            _debug.logic(
                "tag_release_skipped",
                records=self,
                reason="all_tags_still_referenced",
                tags=expressions_tags,
            )
            return

        tags_used_by_aml_ids = {
            tag.id
            for [tag] in self.env["account.move.line"]
            .sudo()
            ._read_group(
                [("tax_tag_ids", "in", orphan_tags.ids)], groupby=["tax_tag_ids"]
            )
        }
        tags_to_archive = orphan_tags.filtered(
            lambda tag: tag.id in tags_used_by_aml_ids
        )
        tags_to_unlink = orphan_tags - tags_to_archive

        rep_lines_with_tag = (
            self.env["account.tax.repartition.line"]
            .sudo()
            .search([("tag_ids", "in", orphan_tags.ids)])
        )
        rep_lines_with_tag.write(
            {"tag_ids": [Command.unlink(tag.id) for tag in orphan_tags]}
        )
        _debug.pipeline(
            "tags_released",
            records=self,
            orphan_tags=orphan_tags,
            archived=tags_to_archive,
            unlinked=tags_to_unlink,
            repartition_lines=rep_lines_with_tag,
        )
        tags_to_archive.active = False
        tags_to_unlink.unlink()

    def _get_matching_tags(self):
        return self._search_tax_tags(
            {
                expression._tax_tag_key()
                for expression in self
                if expression.engine == "tax_tags"
            }
        )

    @api.model
    def _prepare_tag_vals(self, tag_name, country_id) -> list:
        return [
            {
                "name": tag_name.lstrip("-"),
                "applicability": "taxes",
                "country_id": country_id,
            }
        ]

    def _get_carryover_target_expression(self, options):
        self.check_singleton()

        if self.carryover_target:
            line_code, expr_label = self._parse_carryover_target()
            _debug.logic(
                "carryover_target_explicit",
                expression=self,
                line_code=line_code,
                expr_label=expr_label,
            )
            return self.env["report.formula.expression"].search(
                [
                    ("report_line_id.code", "=", line_code),
                    ("label", "=", expr_label),
                    ("report_line_id.report_id", "=", self.report_line_id.report_id.id),
                ],
                limit=1,
            )

        main_expr_label = re.sub(r"^_carryover_", "", self.label)
        target_label = "_applied_carryover_%s" % main_expr_label
        auto_chosen_target = self.report_line_id.expression_ids.filtered(
            lambda x: x.label == target_label
        )

        if not auto_chosen_target:
            _debug.logic(
                "carryover_target_not_found", expression=self, target_label=target_label
            )
            raise UserError(
                self.env._(
                    "Could not determine carryover target automatically for expression %s.",
                    self.label,
                )
            )

        _debug.logic(
            "carryover_target_auto", expression=self, target=auto_chosen_target
        )
        return auto_chosen_target

    @_debug.perf.timed
    def action_view_carryover_lines(self, options, column_group_key=None) -> dict:
        _debug.lifecycle("action_view_carryover_lines", records=self)
        if column_group_key:
            options = self.report_line_id.report_id._get_column_group_options(
                options, column_group_key
            )

        report = self.report_line_id.report_id
        domain = (
            Domain("target_report_expression_id", "=", self.id)
            & report._get_date_scope_domain(options, self.date_scope)
            & Domain("company_id", "in", report.get_report_company_ids(options))
        )

        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Carryover lines for: %s", self.report_line_name),
            "res_model": "report.formula.external.value",
            "views": [(False, "list")],
            "domain": list(domain),
        }
