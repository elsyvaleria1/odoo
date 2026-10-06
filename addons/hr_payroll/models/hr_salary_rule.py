from ast import literal_eval
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools.safe_eval import safe_eval

_debug = DebugLog(__name__)


class HrSalaryRule(models.Model):
    _name = "hr.salary.rule"
    _order = "sequence, id"
    _description = "Salary Rule"

    name = fields.Char(
        translate=True,
        required=True,
    )
    code = fields.Char(
        index=True,
        required=True,
        help="The code of salary rules can be used as reference in computation of other rules. "
        "In that case, it is case sensitive.",
    )
    struct_id = fields.Many2one(
        comodel_name="hr.payroll.structure",
        string="Salary Structure",
        index=True,
        required=True,
        ondelete="cascade",
    )
    country_id = fields.Many2one(related="struct_id.country_id")
    sequence = fields.Integer(
        default=5,
        index=True,
        required=True,
        help="Use to arrange calculation sequence",
    )
    quantity = fields.Char(
        default="1.0",
        help="It is used in computation for percentage and fixed amount. "
        "E.g. a rule for Meal Voucher having fixed amount of "
        "1€ per worked day can have its quantity defined in expression "
        "like worked_days['WORK100'].number_of_days.",
    )
    category_id = fields.Many2one(
        comodel_name="hr.salary.rule.category",
        domain="['|', ('country_id', '=', False), ('country_id', '=', country_id)]",
    )
    active = fields.Boolean(
        default=True,
        help="If the active field is set to false, it will allow you to hide the salary rule without removing it.",
    )
    appears_on_payslip = fields.Boolean(
        string="Appears on Payslip",
        default=True,
        help="Used to display the salary rule on payslip.",
    )
    appears_on_employee_cost_dashboard = fields.Boolean(
        string="Contributes to Employer Cost",
        default=False,
        help="Used to compute the employer cost of a payslip.",
    )
    condition_select = fields.Selection(
        selection=[
            ("none", "Always True"),
            ("property_input", "Salary Input"),
            ("input", "Other Input"),
            ("python", "Python Expression"),
            ("domain", "Domain"),
        ],
        string="Condition Based on",
        default="none",
        required=True,
    )
    condition_other_input_id = fields.Many2one(
        comodel_name="hr.payslip.input.type",
        domain=[("is_quantity", "=", False)],
    )
    condition_python = fields.Text(
        string="Python Condition",
        default="""
result = result_rules['NET']['total'] > categories['NET'] * 0.10""",
        required=True,
        help="Applied this rule for calculation if condition is true. You can specify condition like basic > 1000.",
    )
    condition_domain = fields.Char(
        string="Applicability Domain",
        help="Define the applicability rules for this rule.",
    )
    amount_select = fields.Selection(
        selection=[
            ("percentage", "Percentage (%)"),
            ("fix", "Fixed Amount"),
            ("input", "Other Input"),
            ("code", "Python Code"),
        ],
        string="Amount Type",
        default="fix",
        index=True,
        required=True,
        help="The computation method for the rule amount.",
    )
    amount_fix = fields.Float(
        string="Fixed Amount",
        digits="Payroll",
    )
    amount_percentage = fields.Float(
        string="Percentage (%)",
        digits="Payroll Rate",
        help="For example, enter 50.0 to apply a percentage of 50%",
    )
    amount_other_input_id = fields.Many2one(
        comodel_name="hr.payslip.input.type",
        domain=[("is_quantity", "=", False)],
    )
    amount_python_compute = fields.Text(
        string="Python Code",
        default="""
result = version.wage
result_rate = 10""",
    )
    amount_percentage_base = fields.Char(
        string="Percentage based on",
        help="result will be affected to a variable",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        help="Eventual third party involved in the salary payment of the employees.",
    )
    note = fields.Html(
        string="Description",
        translate=True,
    )
    color = fields.Char(default="#000000")
    title = fields.Boolean(
        help="When selected, this salary rule will only be displayed as a title with its description, without numeric values."
    )
    bold = fields.Boolean()
    underline = fields.Boolean()
    italic = fields.Boolean()
    indented = fields.Boolean()
    space_above = fields.Boolean()

    input_usage_employee = fields.Boolean()
    input_usage_payslip = fields.Boolean()
    input_default_value = fields.Float(string="Default Value")
    input_default_boolean = fields.Boolean(string="Selected by Default")
    input_description = fields.Char()
    input_section = fields.Many2one(
        comodel_name="hr.salary.rule.section",
        string="Section",
        default=lambda self: self.env.ref(
            "hr_payroll.default_salary_rule_section", raise_if_not_found=False
        ),
        domain="['|', ('struct_ids', 'in', struct_id), ('struct_ids', '=', False)]",
    )
    input_unit = fields.Selection(
        selection=[
            ("monetary", "Monetary"),
            ("quantity", "Quantity"),
            ("percentage", "Percentage"),
            ("boolean", "Checkbox"),
        ],
        string="Unit",
        default="monetary",
    )
    input_suffix = fields.Char()
    dependent_input_id = fields.Many2one(
        comodel_name="hr.salary.rule",
        string="Dependent Salary Input",
        domain="[('id', '!=', id), ('struct_id', '=', struct_id), ('dependent_input_id', '=', False), ('condition_select', '=', 'property_input')]",
    )
    input_used_in_definition = fields.Boolean(
        compute="_compute_input_used_in_definition",
        search="_search_input_used_in_definition",
    )
    modified_by_user = fields.Boolean(
        copy=False,
        readonly=True,
        help="Set when someone edits a rule that a payroll localization ships. The "
        "weekly payroll data update then leaves this rule alone, until it is reset.",
    )

    @api.model
    def update_properties_definition_domain(self, salary_rule_ids, res_model) -> None:
        grouped_rules = self.browse(salary_rule_ids).grouped("struct_id")
        for struct, rules in grouped_rules.items():
            struct._update_payroll_properties(rules, res_model)

    def _compute_input_used_in_definition(self) -> None:
        all_structures = self.grouped("struct_id")
        definitions_inputs_by_structure = defaultdict(set)

        for struct in all_structures:
            definitions_inputs_by_structure[struct] = {
                prop["name"]
                for prop in struct.payslip_properties_definition
                if not prop["name"].startswith("separator_")
            } | {
                prop["name"]
                for prop in struct.version_properties_definition
                if not prop["name"].startswith("separator_")
            }

        for rule in self:
            rule.input_used_in_definition = (
                rule.condition_select == "property_input"
                and str(rule.id) in definitions_inputs_by_structure[rule.struct_id]
            )

    def _search_input_used_in_definition(self, operator, value):
        # operator should be '=' or '!='
        # value is True/False
        if operator not in ("=", "!="):
            raise UserError(self.env._("Unsupported operator %s") % operator)

        # find rule ids that match the condition
        rules = self.env["hr.salary.rule"].search(
            [("condition_select", "=", "property_input")]
        )

        # collect struct->input_names mapping, only for structures these
        # rules actually reference (not every structure in the database)
        definitions_inputs_by_structure = defaultdict(set)
        for struct in rules.struct_id:
            definitions_inputs_by_structure[struct.id] = {
                prop["name"]
                for prop in struct.payslip_properties_definition
                if not prop["name"].startswith("separator_")
            } | {
                prop["name"]
                for prop in struct.version_properties_definition
                if not prop["name"].startswith("separator_")
            }

        matching_rules = [
            rule.id
            for rule in rules
            if str(rule.id)
            in definitions_inputs_by_structure.get(rule.struct_id.id, set())
        ]

        domain = [("id", "in", matching_rules)]
        if (operator == "=" and not value) or (operator == "!=" and value):
            domain = [("id", "not in", matching_rules)]

        return domain

    def _prepare_rule_error(self, localdict, error_type, e):
        _debug.logic(
            "rule_failed",
            rule=self,
            code=self.code,
            employee=localdict["employee"],
            payslip=localdict["payslip"],
            error=type(e).__name__,
        )
        return UserError(
            self.env._(
                """%(error_type)s
- Employee: %(employee)s
- Version: %(version)s
- Payslip: %(payslip)s
- Salary rule: %(name)s (%(code)s)
- Error: %(error_message)s""",
                error_type=error_type,
                employee=localdict["employee"].name,
                version=localdict["version"].name,
                payslip=localdict["payslip"].name,
                name=self.name,
                code=self.code,
                error_message=e,
            )
        )

    def _compute_rule(self, localdict) -> tuple[float, float, float]:
        """
        :param localdict: dictionary containing the current computation environment
        :return: returns a tuple (amount, qty, rate)
        :rtype: tuple[float, float, float]
        """
        self.check_singleton()
        localdict["localdict"] = localdict

        if self.condition_select == "property_input":
            if self.id not in localdict["property_inputs"]:
                _debug.logic("rule_amount", by="property_input_absent", rule=self)
                return 0.0, 1.0, 100.0
            return localdict["property_inputs"][self.id], 1.0, 100.0

        if self.amount_select == "fix":
            try:
                return (
                    self.amount_fix or 0.0,
                    float(safe_eval(self.quantity, localdict)),
                    100.0,
                )
            except Exception as e:
                raise self._prepare_rule_error(
                    localdict, self.env._("Wrong quantity defined for:"), e
                ) from e
        if self.amount_select == "percentage":
            try:
                return (
                    float(safe_eval(self.amount_percentage_base, localdict)),
                    float(safe_eval(self.quantity, localdict)),
                    self.amount_percentage or 0.0,
                )
            except Exception as e:
                raise self._prepare_rule_error(
                    localdict,
                    self.env._("Wrong percentage base or quantity defined for:"),
                    e,
                ) from e
        if self.amount_select == "input":
            if not self.amount_other_input_id:
                raise self._prepare_rule_error(
                    localdict,
                    self.env._("No input configured for:"),
                    self.env._(
                        "amount_select is 'Input' but no other input is selected."
                    ),
                )
            if self.amount_other_input_id.code not in localdict["inputs"]:
                _debug.logic(
                    "rule_amount",
                    by="input_absent",
                    rule=self,
                    input=self.amount_other_input_id.code,
                )
                return 0.0, 1.0, 100.0
            return (
                localdict["inputs"][self.amount_other_input_id.code].amount,
                1.0,
                100.0,
            )
        # python code
        try:
            safe_eval(self.amount_python_compute or 0.0, localdict, mode="exec")
            return (
                float(localdict["result"]),
                localdict.get("result_qty", 1.0),
                localdict.get("result_rate", 100.0),
            )
        except Exception as e:
            raise self._prepare_rule_error(
                localdict, self.env._("Wrong python code defined for:"), e
            ) from e

    def _satisfy_condition(self, localdict):
        self.check_singleton()
        localdict["localdict"] = localdict
        if self.condition_select == "none":
            return True
        if self.condition_select == "input":
            return self.condition_other_input_id.code in localdict["inputs"]
        if self.condition_select == "domain":
            _debug.logic("rule_condition", by="domain", rule=self)
            return localdict["payslip"].filtered_domain(
                literal_eval(self.condition_domain or "[]")
            )
        if self.condition_select == "property_input":
            return self.id in localdict["property_inputs"]
        # python code
        try:
            safe_eval(self.condition_python, localdict, mode="exec")
            return localdict.get("result", False)
        except Exception as e:
            raise self._prepare_rule_error(
                localdict, self.env._("Wrong python condition defined for:"), e
            ) from e

    def _get_report_field_name(self) -> str:
        self.check_singleton()
        return "x_l10n_%s_%s" % (
            self.struct_id.country_id.code.lower()
            if self.struct_id.country_id.code
            else "xx",
            self.code.lower().replace(".", "_").replace("-", "_").replace(" ", "_"),
        )

    def write(self, vals):
        # A write on a field the data file owns, made by anything other than the data
        # loader itself, hands the rule over to the user -- see _release_from_data_file.
        release = not self.env.context.get(
            "install_mode"
        ) and not vals.keys().isdisjoint(self._get_data_file_owned_fields())
        res = super().write(vals)
        if release:
            self._release_from_data_file()
        return res

    @api.model
    def _get_data_file_owned_fields(self) -> list:
        """The fields a payroll localization's data file sets, and would set again."""
        return [
            "code",
            "category_id",
            "struct_id",
            "sequence",
            "quantity",
            "condition_select",
            "condition_other_input_id",
            "condition_python",
            "condition_domain",
            "amount_select",
            "amount_fix",
            "amount_percentage",
            "amount_percentage_base",
            "amount_other_input_id",
            "amount_python_compute",
            "input_usage_employee",
            "input_usage_payslip",
            "input_default_value",
            "input_default_boolean",
            "input_description",
            "input_unit",
            "input_suffix",
            "input_section",
            "dependent_input_id",
        ]

    def _release_from_data_file(self) -> None:
        """Stop `hr.payslip._update_payroll_data` from maintaining these rules.

        `hr_payroll.ir_cron_update_payroll_data` re-converts the salary data of every
        installed localization once a week, so without this an edit made in the form
        does not survive seven days. Flagging the external identifier `noupdate` is
        what makes the loader skip the record (`_load_records` in
        `core/odoo/orm/models/mixins/load.py:693` reads `not (update and d_noupdate)`),
        and the flag survives the pass because the upsert in
        `ir.model.data._update_xmlids` never rewrites that column.
        """
        identifiers = (
            self.env["ir.model.data"]
            .sudo()
            .search(
                [
                    ("model", "=", "hr.salary.rule"),
                    ("res_id", "in", self.ids),
                    ("noupdate", "=", False),
                ]
            )
        )
        if not identifiers:
            # Nothing to release: a rule with no external identifier is nobody's but
            # the user's already.
            return
        identifiers.noupdate = True
        # The loader reads noupdate straight out of ir_model_data with raw SQL
        # (ir.model.data._get_xmlids), so an unflushed value would not be seen.
        identifiers.flush_recordset(["noupdate"])
        self.browse(identifiers.mapped("res_id")).modified_by_user = True

    def action_reset_rule(self) -> dict:
        """Give the rule back to the payroll localization that ships it."""
        self.check_singleton()
        self.env["ir.model.data"].sudo().search(
            [
                ("model", "=", "hr.salary.rule"),
                ("res_id", "=", self.id),
            ]
        ).noupdate = False
        self.modified_by_user = False
        self.env.flush_all()
        # Re-applies the salary data of every installed localization, not just this
        # rule's. Wasteful, but idempotent -- every other rule is either already at
        # its shipped value or flagged noupdate -- and reset is a rare, deliberate
        # click.
        self.env["hr.payslip"].sudo()._update_payroll_data()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._(
                    "%s is maintained by its payroll localization again.", self.name
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        if default and "name" in default:
            return vals_list
        return [
            dict(vals, name=self.env._("%s (copy)", rule.name))
            for rule, vals in zip(self, vals_list, strict=False)
        ]

    def copy_translations(self, new, excluded=()) -> None:
        super().copy_translations(new, excluded=(*excluded, "name"))
        self._copy_translations_of_renamed_field(
            new, "name", lambda record, term: record.env._("%s (copy)", term)
        )

    @api.constrains("category_id", "struct_id")
    def _check_category_country(self) -> None:
        for rule in self:
            if (
                rule.category_id.country_id
                and rule.country_id
                and rule.category_id.country_id != rule.country_id
            ):
                raise ValidationError(
                    self.env._(
                        "Rule category and structure should belong to the same country"
                    )
                )
