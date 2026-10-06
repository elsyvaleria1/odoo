from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import ormcache
from odoo.tools.misc import format_date
from odoo.tools.safe_eval import safe_eval


def _rule_code_domain(code):
    """Domain matching any hr.salary.rule referencing `code` (as a quoted
    Python literal) in its condition or amount formula."""
    return Domain.OR(
        [
            Domain("condition_python", "like", "'" + code + "'"),
            Domain("amount_python_compute", "like", "'" + code + "'"),
            Domain("condition_python", "like", '"' + code + '"'),
            Domain("amount_python_compute", "like", '"' + code + '"'),
        ]
    )


class HrRuleParameterValue(models.Model):
    _name = "hr.rule.parameter.value"
    _description = "Salary Rule Parameter Value"
    _order = "date_from desc"

    rule_parameter_id = fields.Many2one(
        comodel_name="hr.rule.parameter",
        default=lambda self: self.env.context.get("active_id"),
        index=True,
        required=True,
        ondelete="cascade",
    )
    rule_parameter_name = fields.Char(
        related="rule_parameter_id.name",
        readonly=True,
    )
    code = fields.Char(
        related="rule_parameter_id.code",
        readonly=True,
    )
    date_from = fields.Date(
        string="From",
        index=True,
        required=True,
    )
    parameter_value = fields.Text(help="Python data structure")
    country_id = fields.Many2one(related="rule_parameter_id.country_id")

    _unique_parameter = models.Constraint(
        "unique (rule_parameter_id, date_from)",
        "Two rules with the same code cannot start the same day",
    )

    @api.constrains("parameter_value")
    def _check_parameter_value(self) -> None:
        for value in self:
            try:
                safe_eval(value.parameter_value)
            except Exception as e:
                raise UserError(
                    self.env._(
                        "Wrong rule parameter value for %(rule_parameter_name)s at date %(date)s.\n%(error)s",
                        rule_parameter_name=value.rule_parameter_name,
                        date=format_date(self.env, value.date_from),
                        error=str(e),
                    )
                ) from e

    @api.model_create_multi
    def create(self, vals_list):
        self.env.registry.clear_cache()
        return super().create(vals_list)

    def write(self, vals):
        if (
            "date_from" in vals
            or "parameter_value" in vals
            or "rule_parameter_id" in vals
        ):
            self.env.registry.clear_cache()
            self._log_parameter_value_updates(vals)
        return super().write(vals)

    def _log_parameter_value_updates(self, vals) -> None:
        """Log the old and the new value on the parent parameter's chatter.

        The value lines have no chatter of their own -- they are edited inline
        in the parameter's form -- so the trace belongs to the parameter.
        """
        for value in self:
            for fname in ("parameter_value", "date_from"):
                if fname not in vals:
                    continue
                field = self._fields[fname]
                old_value = value[fname]
                # convert through the field: vals carries the raw client value,
                # so comparing it to the record value straight would report a
                # change on every re-save of an untouched line.
                new_value = field.convert_to_record(
                    field.convert_to_cache(vals[fname], value, validate=False), value
                )
                if old_value == new_value:
                    continue
                value.rule_parameter_id._message_log(
                    body=Markup(
                        "<ul class='mb-0 list-unstyled'><li>"
                        "<span class='o-mail-Message-trackingOld me-1 px-1 text-muted fw-bold'>{old}</span>"
                        "<i class='o-mail-Message-trackingSeparator fa fa-long-arrow-right mx-1 text-600'/>"
                        "<span class='o-mail-Message-trackingNew me-1 fw-bold text-info'>{new}</span>"
                        "<span class='o-mail-Message-trackingField ms-1 fst-italic text-muted'>({field})</span>"
                        "</li></ul>"
                    ).format(old=old_value, new=new_value, field=field.string)
                )

    def unlink(self):
        self.env.registry.clear_cache()
        return super().unlink()


class HrRuleParameter(models.Model):
    _name = "hr.rule.parameter"
    _description = "Salary Rule Parameter"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]

    name = fields.Char(
        required=True,
        tracking=True,
    )
    code = fields.Char(
        required=True,
        tracking=True,
        help="This code is used in salary rules to refer to this parameter.",
    )
    description = fields.Html()
    country_id = fields.Many2one(
        comodel_name="res.country",
        default=lambda self: self.env.company.country_id,
    )
    parameter_version_ids = fields.One2many(
        comodel_name="hr.rule.parameter.value",
        inverse_name="rule_parameter_id",
        string="Versions",
    )
    current_value_one_line = fields.Text(
        string="Current Value (short)",
        compute="_compute_current_value",
    )
    valid_since = fields.Date(compute="_compute_current_value")
    salary_rule_ids = fields.One2many(
        comodel_name="hr.salary.rule",
        string="Salary Rules",
        compute="_compute_salary_rule",
    )
    salary_rule_count = fields.Count(count_of="salary_rule_ids")

    _unique_code = models.Constraint(
        "unique (code)",
        "Two rule parameters cannot have the same code.",
    )

    def copy_data(self, default=None):
        """Suffix name and code, which `_unique_code` would otherwise reject."""
        vals_list = super().copy_data(default=default)
        default = default or {}
        for parameter, vals in zip(self, vals_list, strict=False):
            if "name" not in default:
                vals["name"] = self.env._("%s (copy)", parameter.name)
            if "code" not in default:
                vals["code"] = self.env._("%s_copy", parameter.code)
        return vals_list

    @api.model
    @ormcache(
        "code",
        "date",
        "raise_if_not_found",
        'tuple(self.env.context.get("allowed_company_ids", []))',
    )
    def _get_parameter_from_code(self, code, date=None, raise_if_not_found=True):
        """Return the parameter value in force for code at date.

        :param str code: rule parameter code
        :param date: date to evaluate at (defaults to today)
        :param bool raise_if_not_found: raise UserError instead of returning None when missing
        :return: the evaluated parameter value, or None
        """
        if not date:
            date = fields.Date.today()
        # This should be quite fast as it uses a limit and fields are indexed
        # moreover the method is cached
        rule_parameter = self.env["hr.rule.parameter.value"].search(
            [("code", "=", code), ("date_from", "<=", date)], limit=1
        )
        if rule_parameter:
            return safe_eval(rule_parameter.parameter_value)
        if raise_if_not_found:
            raise UserError(
                self.env._(
                    'No rule parameter with code "%(code)s" was found for %(date)s',
                    code=code,
                    date=date,
                )
            )
        return None

    @api.depends("parameter_version_ids")
    def _compute_current_value(self) -> None:
        for rule_parameter in self:
            rule_parameter.current_value_one_line = False
            rule_parameter.valid_since = False
            if not rule_parameter.parameter_version_ids:
                continue

            # All values are already order from most recent to oldest.
            # Here we get the first value that is not in the future, i.e. the current value.
            for value_id in rule_parameter.parameter_version_ids:
                if value_id.date_from <= fields.Date.today():
                    parameter_value = value_id.parameter_value or ""
                    try:
                        float(parameter_value)
                        is_number = True
                    except ValueError:
                        is_number = False
                    rule_parameter.current_value_one_line = (
                        parameter_value if is_number else "(...)"
                    )
                    rule_parameter.valid_since = value_id.date_from
                    break

    def _compute_salary_rule(self) -> None:
        rule_parameters_with_code = self.filtered("code")
        (self - rule_parameters_with_code).salary_rule_ids = False
        if not rule_parameters_with_code:
            return

        codes = rule_parameters_with_code.mapped("code")
        matched_rules = self.env["hr.salary.rule"].search(
            Domain.OR(_rule_code_domain(code) for code in codes)
        )
        matched_rules_data = matched_rules.read(
            ["condition_python", "amount_python_compute"]
        )

        for rule_parameter in rule_parameters_with_code:
            quoted_codes = (
                "'" + rule_parameter.code + "'",
                '"' + rule_parameter.code + '"',
            )
            rule_parameter.salary_rule_ids = self.env["hr.salary.rule"].browse(
                data["id"]
                for data in matched_rules_data
                if any(
                    quoted in (data["condition_python"] or "")
                    or quoted in (data["amount_python_compute"] or "")
                    for quoted in quoted_codes
                )
            )

    def action_view_salary_rules(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_payroll.action_salary_rule_form"
        )
        action.update({"domain": _rule_code_domain(self.code)})
        return action
