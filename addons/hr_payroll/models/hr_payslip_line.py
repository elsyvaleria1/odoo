from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict


class HrPayslipLine(models.Model):
    _name = "hr.payslip.line"
    _description = "Payslip Line"
    _order = "version_id, sequence, code"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    name = fields.Char(required=True)
    sequence = fields.Integer(
        default=5,
        index=True,
        required=True,
        help="Use to arrange calculation sequence",
    )
    code = fields.Char(
        required=True,
        help="The code of salary rules can be used as reference in computation of other rules. "
        "In that case, it is case sensitive.",
    )
    slip_id = fields.Many2one(
        comodel_name="hr.payslip",
        string="Pay Slip",
        index=True,
        required=True,
        ondelete="cascade",
    )
    struct_id = fields.Many2one(
        related="slip_id.struct_id",
        string="Salary Structure",
        readonly=True,
    )
    salary_rule_id = fields.Many2one(
        comodel_name="hr.salary.rule",
        string="Rule",
        required=True,
    )
    version_id = fields.Many2one(
        comodel_name="hr.version",
        string="Contract",
        index=True,
        required=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        required=True,
    )
    rate = fields.Float(
        string="Rate (%)",
        digits="Payroll Rate",
        default=100.0,
    )
    amount = fields.Monetary()
    quantity = fields.Float(
        digits="Payroll",
        default=1.0,
    )
    total = fields.Monetary()
    ytd = fields.Monetary(string="YTD")

    amount_select = fields.Selection(
        related="salary_rule_id.amount_select",
        readonly=True,
    )
    amount_fix = fields.Float(
        related="salary_rule_id.amount_fix",
        readonly=True,
    )
    amount_percentage = fields.Float(
        related="salary_rule_id.amount_percentage",
        readonly=True,
    )
    appears_on_payslip = fields.Boolean(
        related="salary_rule_id.appears_on_payslip",
        readonly=True,
    )
    category_id = fields.Many2one(
        related="salary_rule_id.category_id",
        readonly=True,
    )
    partner_id = fields.Many2one(
        related="salary_rule_id.partner_id",
        readonly=True,
    )

    date_from = fields.Date(
        related="slip_id.date_from",
        string="From",
    )
    date_to = fields.Date(
        related="slip_id.date_to",
        string="To",
    )
    company_id = fields.Many2one(related="slip_id.company_id")
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="slip_id.currency_id",
    )

    _slip_id_code = models.Index("(slip_id, code)")

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if "employee_id" not in values or "version_id" not in values:
                payslip = self.env["hr.payslip"].browse(values.get("slip_id"))
                values["employee_id"] = (
                    values.get("employee_id") or payslip.employee_id.id
                )
                values["version_id"] = values.get("version_id") or (
                    payslip.version_id and payslip.version_id.id
                )
                if not values["version_id"]:
                    raise UserError(
                        self.env._("You must set a contract to create a payslip line.")
                    )
        return super().create(vals_list)

    def get_payslip_styling_dict(self) -> dict:
        self.check_singleton()
        rule = self.salary_rule_id
        classes = []
        if rule.bold:
            classes.append("fw-bold")
        if rule.italic:
            classes.append("fst-italic")
        if rule.underline:
            classes.append("text-decoration-underline")
        if rule.space_above:
            classes.append("pt-4")
        if rule.indented:
            classes.append("ps-4")
        return {
            "line_style": f"color:{rule.color};",
            "line_class": " ".join(classes),
            "o_title": "d-none" if rule.title else "",
        }
