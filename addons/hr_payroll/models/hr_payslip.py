import logging
import math
import random
from collections import defaultdict
from datetime import date
from functools import reduce

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.datetime import get_quarter, get_quarter_number
from odoo.libs.debug_log import DebugLog
from odoo.libs.numbers import float_compare
from odoo.tools import convert_file, float_round, format_amount
from odoo.tools.misc import format_date
from odoo.tools.safe_eval import datetime as safe_eval_datetime
from odoo.tools.safe_eval import dateutil as safe_eval_dateutil
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class DefaultDictPayroll(defaultdict):
    def get(self, key, default=None):
        if key not in self and default is not None:
            self[key] = default
        return self[key]


class HrPayslip(models.Model):
    _name = "hr.payslip"
    _description = "Pay Slip"
    _inherit = [
        "mixin.mail.thread.cc",
        "mixin.mail.thread.main.attachment",
        "mixin.mail.activity",
    ]
    _order = "date_to desc"

    struct_id = fields.Many2one(
        comodel_name="hr.payroll.structure",
        string="Structure",
        compute="_compute_struct_id",
        precompute=True,
        store=True,
        readonly=False,
        tracking=True,
        help="Defines the rules that have to be applied to this payslip, according "
        "to the contract chosen. If the contract is empty, this field isn't "
        "mandatory anymore and all the valid rules of the structures "
        "of the employee's contracts will be applied.",
    )
    structure_code = fields.Char(related="struct_id.code")
    struct_type_id = fields.Many2one(
        comodel_name="hr.payroll.structure.type",
        related="struct_id.type_id",
    )
    wage_type = fields.Selection(related="version_id.wage_type")
    name = fields.Char(
        string="Payslip Name",
        compute="_compute_name",
        store=True,
        readonly=False,
        required=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        index=True,
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), '|', ('active', '=', True), ('active', '=', False)]",
    )
    employee_reference = fields.Char(related="employee_id.registration_number")
    image_128 = fields.Image(related="employee_id.image_128")
    image_1920 = fields.Image(related="employee_id.image_1920")
    avatar_128 = fields.Image(related="employee_id.avatar_128")
    avatar_1920 = fields.Image(related="employee_id.avatar_1920")
    department_id = fields.Many2one(
        comodel_name="hr.department",
        related="employee_id.department_id",
        string="Department",
        readonly=True,
    )
    job_id = fields.Many2one(
        comodel_name="hr.job",
        related="employee_id.job_id",
        string="Job Position",
        readonly=True,
    )
    date_from = fields.Date(
        string="From",
        default=lambda self: date.today().replace(day=1),
        readonly=False,
        required=True,
        tracking=True,
    )
    date_to = fields.Date(
        string="To",
        compute="_compute_date_to",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("validated", "Validated"),
            ("paid", "Paid"),
            ("cancel", "Canceled"),
        ],
        default="draft",
        index=True,
        copy=False,
        readonly=True,
        tracking=True,
        help="""* When the payslip is created the status is \'Draft\'
                \n* If the payslip is confirmed then status is set to \'Validated\'.
                \n* When the user cancels a payslip, the status is \'Canceled\'.""",
    )
    state_display = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("validated", "Done"),
            ("paid", "Paid"),
            ("cancel", "Canceled"),
            ("warning", "Warning"),
            ("error", "Error"),
        ],
        string="Status",
        compute="_compute_state_display",
        store=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        comodel_name="hr.payslip.line",
        inverse_name="slip_id",
        string="Payslip Lines",
        compute="_compute_line_ids",
        store=True,
        copy=True,
        readonly=False,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        default=lambda self: self.env.company,
        store=True,
        copy=False,
        readonly=True,
        required=True,
    )
    country_id = fields.Many2one(
        comodel_name="res.country",
        related="company_id.country_id",
        string="Country",
        search="_search_country_id",
        readonly=True,
    )
    country_code = fields.Char(
        related="country_id.code",
        depends=["country_id"],
        readonly=True,
    )
    worked_days_line_ids = fields.One2many(
        comodel_name="hr.payslip.worked_days",
        inverse_name="payslip_id",
        string="Payslip Worked Days",
        compute="_compute_worked_days_line_ids",
        store=True,
        copy=True,
        readonly=False,
    )
    input_line_ids = fields.One2many(
        comodel_name="hr.payslip.input",
        inverse_name="payslip_id",
        string="Payslip Inputs",
        compute="_compute_input_line_ids",
        store=True,
        readonly=False,
    )
    paid = fields.Boolean(
        string="Made Payment Order? ",
        copy=False,
    )
    done_date = fields.Datetime(string="payslip confirmation Date")
    paid_date = fields.Date(string="Payment Date")
    note = fields.Text(string="Internal Note")
    version_id = fields.Many2one(
        comodel_name="hr.version",
        string="Employee Record",
        compute="_compute_version_id",
        precompute=True,
        store=True,
        index=True,
        readonly=False,
        domain="""[
            ('contract_date_start', '<=', date_end),
            '|', ('contract_date_end', '=', False), ('contract_date_end', '>=', date_from)
        ]""",
        tracking=True,
    )
    credit_note = fields.Boolean(help="Indicates this payslip has a refund of another")
    payslip_run_id = fields.Many2one(
        comodel_name="hr.payslip.run",
        string="Pay Run",
        index="btree_not_null",
        copy=False,
        domain="[('company_id', '=', company_id)]",
        ondelete="cascade",
        tracking=True,
    )
    sum_worked_hours = fields.Float(
        compute="_compute_worked_hours",
        store=True,
        help="Total hours of attendance and time off (paid or not)",
    )
    compute_date = fields.Date(string="Computed On")
    basic_wage = fields.Monetary(
        compute="_compute_basic_net",
        store=True,
    )
    gross_wage = fields.Monetary(
        compute="_compute_basic_net",
        store=True,
    )
    net_wage = fields.Monetary(
        compute="_compute_basic_net",
        store=True,
    )
    currency_id = fields.Many2one(related="version_id.currency_id")
    is_regular = fields.Boolean(compute="_compute_is_regular")
    is_wrong_version = fields.Boolean(
        compute="_compute_is_wrong_version",
        store=True,
    )
    has_wrong_data = fields.Boolean(
        compute="_compute_is_wrong_version",
        store=True,
    )
    keep_wrong_version = fields.Boolean(default=False)
    has_negative_net_to_report = fields.Boolean()
    is_superuser = fields.Boolean(compute="_compute_is_superuser")
    edited = fields.Boolean()
    queued_for_pdf = fields.Boolean(default=False)

    issues = fields.Json(
        compute="_compute_issues",
        store=True,
        readonly=True,
    )
    warning_count = fields.Integer(
        compute="_compute_issues",
        store=True,
        readonly=True,
    )
    error_count = fields.Integer(
        compute="_compute_issues",
        store=True,
        readonly=True,
    )
    is_wrong_duration = fields.Boolean(
        compute="_compute_is_wrong_duration",
        compute_sudo=True,
    )
    negative_net_to_report_message = fields.Char(
        compute="_compute_negative_net_to_report_display"
    )
    negative_net_to_report_amount = fields.Float(
        compute="_compute_negative_net_to_report_display"
    )
    negative_net_to_report_display = fields.Boolean(
        compute="_compute_negative_net_to_report_display"
    )

    salary_attachment_ids = fields.Many2many(
        comodel_name="hr.salary.attachment",
        relation="hr_payslip_hr_salary_attachment_rel",
        string="Salary Adjustments",
        compute="_compute_salary_attachment_ids",
        store=True,
        readonly=False,
    )
    salary_attachment_count = fields.Count(
        count_of="salary_attachment_ids",
        string="Salary Adjustment count",
    )
    employee_version_ids_count = fields.Integer(
        compute="_compute_employee_version_ids_count",
        help="How many employee records the employee has; the selector only has "
        "something to choose from once there are two.",
    )
    use_worked_day_lines = fields.Boolean(related="struct_id.use_worked_day_lines")
    payment_report = fields.Binary(
        readonly=True,
        help="Export .csv file related to this payslip",
    )
    payment_report_filename = fields.Char(readonly=True)
    payment_report_date = fields.Date(readonly=True)
    ytd_computation = fields.Boolean(related="struct_id.ytd_computation")
    employer_cost = fields.Monetary(
        compute="_compute_basic_net",
        store=True,
    )
    is_refund_payslip = fields.Boolean(
        string="Is Refund payslip",
        default=False,
    )
    is_refunded = fields.Boolean(default=False)
    is_corrected = fields.Boolean(default=False)
    origin_payslip_id = fields.Many2one(
        comodel_name="hr.payslip",
        index="btree_not_null",
    )
    related_payslip_ids = fields.One2many(
        comodel_name="hr.payslip",
        inverse_name="origin_payslip_id",
        string="Related Payslips",
    )
    related_payslip_count = fields.Count(
        count_of="related_payslip_ids",
        string="Related payslip count",
    )
    payslip_properties = fields.Properties(
        definition="struct_id.payslip_properties_definition",
        string="Payroll Properties",
    )

    def _get_salary_advance_balances(self):
        return defaultdict(float)

    @api.model
    def _schedule_period_start(self, schedule, today, country_code=False):
        week_start = self.env["res.lang"]._get_data(code=self.env.user.lang).week_start
        if schedule == "quarterly":
            date_from = get_quarter(today)[0]
        elif schedule == "semi-annually":
            is_second_half = math.floor((today.month - 1) / 6)
            date_from = (
                today.replace(day=1, month=7)
                if is_second_half
                else today.replace(day=1, month=1)
            )
        elif schedule == "annually":
            date_from = today.replace(day=1, month=1)
        elif schedule == "weekly":
            # `week_start` is already read above and every other branch that
            # cares about it uses it. Anchoring to `weekday()` alone pinned
            # the period to a Monday even for a language whose week begins on
            # Sunday. res.lang numbers the days 1=Monday..7=Sunday, Python
            # 0=Monday..6=Sunday, hence the -1.
            week_day = (today.weekday() - (int(week_start) - 1)) % 7
            date_from = today + relativedelta(days=-week_day)
        elif schedule == "bi-weekly":
            week = int(
                today.strftime("%U") if week_start == "7" else today.strftime("%W")
            )
            week_day = today.weekday()
            is_second_week = week % 2 == 0
            date_from = today + relativedelta(days=-week_day - 7 * int(is_second_week))
        elif schedule == "semi-monthly":
            # The halves are 1..15 and 16..end-of-month. Starting the second
            # one on the 15th put that day inside both payslips, since
            # `_schedule_timedelta` ends the first half on it.
            date_from = today.replace(day=1 if today.day < 16 else 16)
        elif schedule == "bi-monthly":
            current_year_slice = math.ceil(today.month / 2)
            date_from = today.replace(day=1, month=(current_year_slice - 1) * 2 + 1)
        elif schedule == "daily":
            date_from = today
        else:  # if not handled, put the monthly behaviour
            date_from = today.replace(day=1)
        return date_from

    @api.model_create_multi
    def create(self, vals_list):
        payslips = super().create(vals_list)
        _debug.lifecycle("create", payslips=payslips, count=len(vals_list))
        payslips._update_payslip_properties()
        return payslips

    def _update_payslip_properties(self) -> None:
        properties_definition_per_structure = defaultdict(list)
        for struct in self.mapped("struct_id"):
            properties_definition_per_structure[struct] = (
                struct._get_common_payroll_properties()
            )

        for payslip in self:
            payslip_properties = dict(payslip.payslip_properties) or {}
            if payslip.state in ["paid", "validated"]:
                continue
            version_properties = dict(payslip.version_id.payroll_properties)
            payslip_properties.update(
                {
                    key: version_properties.get(key, 0)
                    for key in properties_definition_per_structure[payslip.struct_id]
                }
            )
            payslip.update({"payslip_properties": payslip_properties})

    @api.depends("error_count", "warning_count", "state")
    def _compute_state_display(self) -> None:
        for payslip in self:
            if payslip.error_count:
                payslip.state_display = "error"
            elif payslip.warning_count:
                payslip.state_display = "warning"
            else:
                payslip.state_display = payslip.state

    @api.model
    def _schedule_timedelta(self, schedule, date_from, country_code=False):
        if schedule == "quarterly":
            timedelta = relativedelta(months=3, days=-1)
        elif schedule == "semi-annually":
            timedelta = relativedelta(months=6, days=-1)
        elif schedule == "annually":
            timedelta = relativedelta(years=1, days=-1)
        elif schedule == "weekly":
            timedelta = relativedelta(days=6)
        elif schedule == "bi-weekly":
            timedelta = relativedelta(days=13)
        elif schedule == "semi-monthly":
            timedelta = relativedelta(day=15 if date_from.day < 16 else 31)
        elif schedule == "bi-monthly":
            timedelta = relativedelta(months=2, days=-1)
        elif schedule == "daily":
            timedelta = relativedelta(days=0)
        else:  # if not handled, put the monthly behaviour
            timedelta = relativedelta(months=1, days=-1)
        return timedelta

    def _get_schedule_timedelta(self):
        self.check_singleton()
        schedule = (
            self.version_id.schedule_pay
            or self.version_id.structure_type_id.default_schedule_pay
        )
        return self._schedule_timedelta(schedule, self.date_from)

    @api.depends("date_from", "version_id", "struct_id")
    def _compute_date_to(self) -> None:
        for payslip in self:
            if self.env.context.get("default_date_to"):
                payslip.date_to = self.env.context.get("default_date_to")
            else:
                payslip.date_to = (
                    payslip.date_from
                    and payslip.date_from + payslip._get_schedule_timedelta()
                )

    @api.depends(
        "employee_id", "version_id", "struct_id", "date_from", "date_to", "struct_id"
    )
    def _compute_input_line_ids(self):
        attachment_type_ids = (
            self.env["hr.payslip.input.type"]
            .search([("available_in_attachments", "=", True)])
            .ids
        )
        for slip in self:
            if (
                not slip.employee_id
                or not slip.employee_id.salary_attachment_ids
                or not slip.struct_id
            ):
                lines_to_remove = slip.input_line_ids.filtered(
                    lambda x: x.input_type_id.id in attachment_type_ids
                )
                slip.update(
                    {
                        "input_line_ids": [
                            Command.unlink(line.id) for line in lines_to_remove
                        ]
                    }
                )
            elif slip.employee_id.salary_attachment_ids and slip.date_to:
                lines_to_remove = slip.input_line_ids.filtered(
                    lambda x: x.input_type_id.id in attachment_type_ids
                )
                input_line_vals = [Command.unlink(line.id) for line in lines_to_remove]

                valid_attachments = slip._get_applicable_salary_attachments()
                # Only take deduction types present in structure
                for input_type_id, attachments in valid_attachments.grouped(
                    "other_input_type_id"
                ).items():
                    amount = attachments._get_active_amount()
                    name = ", ".join(
                        description
                        for description in attachments.mapped("description")
                        if description
                    )
                    input_line_vals.append(
                        Command.create(
                            {
                                "name": name,
                                "amount": amount if not slip.credit_note else -amount,
                                "input_type_id": input_type_id.id,
                            }
                        )
                    )
                slip.update({"input_line_ids": input_line_vals})

    def _get_applicable_salary_attachments(self):
        self.check_singleton()
        return self.employee_id.salary_attachment_ids.filtered(
            lambda a: (
                a.state == "open"
                and a.date_start <= self.date_to
                and (not a.date_end or a.date_end >= self.date_from)
                and (
                    not a.other_input_type_id.struct_ids
                    or self.struct_id in a.other_input_type_id.struct_ids
                )
            )
        )

    @api.depends("employee_id.version_ids")
    def _compute_employee_version_ids_count(self) -> None:
        for payslip in self:
            payslip.employee_version_ids_count = len(payslip.employee_id.version_ids)

    @api.depends("input_line_ids.input_type_id", "input_line_ids")
    def _compute_salary_attachment_ids(self) -> None:
        for slip in self:
            if not slip.input_line_ids and not slip.salary_attachment_ids:
                continue
            attachments = self.env["hr.salary.attachment"]
            if slip.employee_id and slip.input_line_ids and slip.date_to:
                deduction_types = slip.input_line_ids.input_type_id.filtered(
                    "available_in_attachments"
                ).ids
                attachments = slip.employee_id.salary_attachment_ids.filtered_domain(
                    [
                        ("state", "=", "open"),
                        ("other_input_type_id", "in", deduction_types),
                        ("date_start", "<=", slip.date_to),
                    ]
                )
            slip.salary_attachment_ids = attachments

    @api.depends("employee_id", "state")
    def _compute_negative_net_to_report_display(self) -> None:
        activity_type = (
            self.env.ref(
                "hr_payroll.mail_activity_data_hr_payslip_negative_net",
                raise_if_not_found=False,
            )
            or self.env["mail.activity.type"]
        )
        draft_payslips = self.filtered(lambda p: p.state == "draft")
        payslips_to_report_by_employee = defaultdict(lambda: self.env["hr.payslip"])
        if draft_payslips:
            for slip in self.env["hr.payslip"].search(
                [
                    ("has_negative_net_to_report", "=", True),
                    ("employee_id", "in", draft_payslips.employee_id.ids),
                    ("credit_note", "=", False),
                ]
            ):
                payslips_to_report_by_employee[slip.employee_id.id] |= slip

        for payslip in self:
            if payslip.state == "draft":
                payslips_to_report = payslips_to_report_by_employee[
                    payslip.employee_id.id
                ]
                payslip.negative_net_to_report_display = payslips_to_report
                payslip.negative_net_to_report_amount = (
                    payslips_to_report._get_line_values(["NET"], compute_sum=True)[
                        "NET"
                    ]["sum"]["total"]
                )
                payslip.negative_net_to_report_message = self.env._(
                    "There are previous payslips with a negative amount for a total of %s to report.",
                    round(payslip.negative_net_to_report_amount, 2),
                )
                if (
                    payslips_to_report
                    and payslip.state == "draft"
                    and payslip.line_ids
                    and payslip.version_id
                    and (
                        not payslip.activity_ids.filtered(
                            lambda a: a.activity_type_id == activity_type
                        )
                    )
                ):
                    payslip.activity_schedule(
                        "hr_payroll.mail_activity_data_hr_payslip_negative_net",
                        summary=self.env._("Previous Negative Payslip to Report"),
                        note=self.env._(
                            "At least one previous negative net could be reported on this payslip for %s",
                            payslip.employee_id._get_html_link(),
                        ),
                        user_id=payslip.version_id.hr_responsible_id.id
                        or self.env.ref("base.user_admin").id,
                    )
            else:
                payslip.negative_net_to_report_display = False
                payslip.negative_net_to_report_amount = False
                payslip.negative_net_to_report_message = False

    def _get_negative_net_input_type(self):
        self.check_singleton()
        return self.env.ref("hr_payroll.input_deduction")

    def action_report_negative_amount(self) -> None:
        self.check_singleton()
        deduction_input_type = self._get_negative_net_input_type()
        deduction_input_line = self.input_line_ids.filtered(
            lambda l: l.input_type_id == deduction_input_type
        )
        if deduction_input_line:
            deduction_input_line.amount += abs(self.negative_net_to_report_amount)
        else:
            self.write(
                {
                    "input_line_ids": [
                        Command.create(
                            {
                                "input_type_id": deduction_input_type.id,
                                "amount": abs(self.negative_net_to_report_amount),
                            }
                        )
                    ]
                }
            )
        self.compute_sheet()
        self.env["hr.payslip"].search(
            [
                ("has_negative_net_to_report", "=", True),
                ("employee_id", "=", self.employee_id.id),
                ("credit_note", "=", False),
            ]
        ).write({"has_negative_net_to_report": False})
        self.activity_feedback(
            ["hr_payroll.mail_activity_data_hr_payslip_negative_net"]
        )

    def _compute_is_regular(self) -> None:
        for payslip in self:
            payslip.is_regular = (
                payslip.struct_id.type_id.default_struct_id == payslip.struct_id
            )

    @api.depends(
        "employee_id.current_version_id",
        "version_id.last_modified_date",
        "date_from",
        "state",
    )
    def _compute_is_wrong_version(self) -> None:
        self.is_wrong_version = False
        self.has_wrong_data = False
        for payslip in self.filtered(lambda slip: slip.state in ("validated", "paid")):
            payslip.is_wrong_version = (
                payslip.employee_id
                and payslip.version_id
                and payslip.version_id
                != payslip.employee_id._get_version(date=payslip.date_from)
            )
            payslip.has_wrong_data = bool(
                payslip.done_date
                and payslip.version_id.last_modified_date > payslip.done_date
            )

    def _get_invalid_warning(self) -> str:
        self.check_singleton()
        if self.state not in ["validated", "paid"]:
            return self.env._(
                "This payslip is not validated. This is not a legal document."
            )
        return ""

    @api.depends(lambda self: self._get_fields_recomputing())
    def _compute_line_ids(self) -> None:
        if not self.env.context.get("payslip_no_recompute"):
            return
        payslips = self.filtered(lambda p: p.line_ids and p.state == "draft")
        for payslip in payslips:
            lines_vals = []
            if (
                payslip.employee_id
                and payslip.version_id
                and payslip.date_from
                and payslip.date_to
                and payslip.struct_id
            ):
                lines_vals = [
                    Command.create(line_vals)
                    for line_vals in payslip._get_payslip_lines()
                ]
            payslip.line_ids = [Command.clear()] + lines_vals

    def _get_fields_recomputing(self) -> list:
        return [
            "employee_id",
            "version_id",
            "struct_id",
            "date_from",
            "date_to",
            "worked_days_line_ids",
            "input_line_ids",
        ]

    @api.depends(
        "line_ids.total", "struct_id.rule_ids.appears_on_employee_cost_dashboard"
    )
    def _compute_basic_net(self):
        line_values = (self._origin)._get_line_values(["BASIC", "GROSS", "NET"])
        employer_cost_codes = set(
            self.env["hr.salary.rule"]
            .search([("appears_on_employee_cost_dashboard", "=", True)])
            .mapped("code")
        )
        employer_cost_values = {}
        if employer_cost_codes:
            employer_cost_values = (self._origin)._get_line_values(employer_cost_codes)
        for payslip in self:
            employer_cost_total = 0.0
            payslip_employer_codes = payslip.struct_id.rule_ids.filtered(
                "appears_on_employee_cost_dashboard"
            ).mapped("code")
            for code in payslip_employer_codes:
                employer_cost_total += employer_cost_values[code][payslip._origin.id][
                    "total"
                ]
            payslip.basic_wage = line_values["BASIC"][payslip._origin.id]["total"]
            payslip.gross_wage = line_values["GROSS"][payslip._origin.id]["total"]
            payslip.net_wage = line_values["NET"][payslip._origin.id]["total"]
            payslip.employer_cost = employer_cost_total

    @api.depends("worked_days_line_ids.number_of_hours", "worked_days_line_ids.is_paid")
    def _compute_worked_hours(self) -> None:
        for payslip in self:
            payslip.sum_worked_hours = sum(
                line.number_of_hours for line in payslip.worked_days_line_ids
            )

    def _get_regular_worked_hours(self):
        # To be overridden by localization modules. Used for the amount computation for each worked days type.
        self.check_singleton()
        return self.sum_worked_hours

    def _compute_is_superuser(self) -> None:
        self.is_superuser = self.env.user._is_superuser() and self.env.user.has_group(
            "base.group_no_one"
        )

    @api.constrains("date_from", "date_to")
    def _check_dates(self) -> None:
        if any(payslip.date_from > payslip.date_to for payslip in self):
            raise ValidationError(
                self.env._("Payslip 'Date From' must be earlier than 'Date To'.")
            )

    def _record_attachment_payment(self, attachments, slip_lines) -> None:
        self.check_singleton()
        sign = -1 if self.credit_note else 1
        amount = (
            sum(sl.total for sl in slip_lines)
            if not all(attachments.other_input_type_id.mapped("is_quantity"))
            else sum(sl.quantity for sl in slip_lines)
        )
        attachments.record_payment(sign * abs(amount))

    def write(self, vals):
        _debug.lifecycle("write", payslips=self, fields=list(vals))
        # Snapshot which payslips are actually transitioning INTO 'paid'
        # before super().write() changes their state -- record_payment is not
        # idempotent, so re-writing state='paid' on an already-paid payslip
        # (e.g. a batch write mixing paid and not-yet-paid slips) must not
        # deduct salary attachments a second time.
        slips_becoming_paid = self.env["hr.payslip"]
        if vals.get("state") == "paid":
            slips_becoming_paid = self.filtered(lambda r: r.state != "paid")

        res = super().write(vals)

        if vals.get("input_line_ids") or vals.get("payslip_properties"):
            # A draft sheet that was already computed has to follow its inputs,
            # otherwise the Salary Computation tab silently disagrees with the
            # Salary Inputs one. Hand-edited payslips are left alone here for
            # the same reason action_refresh_from_work_entries leaves them
            # alone: their lines were typed by a user, not computed.
            self.filtered(
                lambda p: p.state == "draft" and p.line_ids and not p.edited
            ).compute_sheet()
        if "state" in vals and vals["state"] == "paid":
            # Register payment in Salary Attachments
            # NOTE: Since we combine multiple attachments on one input line, it's not possible to compute
            #  how much per attachment needs to be taken record_payment will consume monthly payments (child_support) before other attachments
            for slip in slips_becoming_paid.filtered(lambda r: r.salary_attachment_ids):
                salary_lines_by_code = slip.line_ids.grouped("code")
                for deduction_code, attachments in slip.salary_attachment_ids.grouped(
                    lambda x: x.other_input_type_id.code
                ).items():
                    # Use the amount from the computed value in the payslip lines not the input
                    salary_lines = salary_lines_by_code.get(deduction_code)
                    if not attachments or not salary_lines:
                        continue
                    _debug.lifecycle(
                        "attachment_payment",
                        payslip=slip,
                        attachments=attachments,
                        codes=deduction_code,
                    )
                    slip._record_attachment_payment(attachments, salary_lines)
        return res

    def action_draft_linked_entries(self) -> None:
        if not self:
            return
        work_entries = self.env["hr.work.entry"].search(
            Domain("employee_id", "=", self.employee_id.ids)
            & Domain("date", ">=", min(self.mapped("date_from")))
            & Domain("date", "<=", max(self.mapped("date_to")))
            & Domain("state", "=", "validated")
        )
        work_entries_by_employee = work_entries.grouped("employee_id")
        linked_entries = self.env["hr.work.entry"]
        similar_payslips = self._get_similar_payslips()
        for regular_payslip in self:
            payslip_start = regular_payslip.date_from
            payslip_end = regular_payslip.date_to
            key = (
                regular_payslip.employee_id.id,
                regular_payslip.struct_id.id,
                payslip_start,
                payslip_end,
            )
            if similar_payslips[key] - regular_payslip:
                continue
            employee_entries = work_entries_by_employee.get(
                regular_payslip.employee_id, work_entries.browse()
            )
            linked_entries |= employee_entries.filtered_domain(
                [
                    ("date", ">=", payslip_start),
                    ("date", "<=", payslip_end),
                    ("has_payslip", "=", False),
                ]
            )

        if linked_entries:
            linked_entries.action_set_to_draft()

    def action_payslip_draft(self):
        self.env["ir.attachment"].sudo().search(
            [
                ("res_model", "=", "hr.payslip"),
                ("res_id", "in", self.ids),
                ("res_field", "=", "payment_report"),
            ]
        ).unlink()
        self.write(
            {
                "payment_report": False,
                "payment_report_filename": False,
                "payment_report_date": False,
                "state": "draft",
            }
        )
        self.action_draft_linked_entries()
        return True

    def _get_pdf_reports(self):
        default_report = self.env.ref("hr_payroll.action_report_payslip")
        result = defaultdict(lambda: self.env["hr.payslip"])
        for payslip in self:
            if not payslip.struct_id or not payslip.struct_id.report_id:
                result[default_report] |= payslip
            else:
                result[payslip.struct_id.report_id] |= payslip
        return result

    def _get_email_template(self):
        return self.env.ref(
            "hr_payroll.mail_template_new_payslip", raise_if_not_found=False
        )

    def _check_send_payslip_mail(self):
        self.check_singleton()
        return True

    def _create_pdf_attachments(self) -> None:
        mapped_reports = self._get_pdf_reports()
        attachments_vals_list = []
        generic_name = self.env._("Payslip")
        for report, payslips in mapped_reports.items():
            for payslip in payslips:
                pdf_content, dummy = (  # noqa: RUF059  `dummy` is the fork throwaway-name convention
                    self.env["ir.actions.report"]
                    .sudo()
                    .with_context(lang=payslip.employee_id.lang or self.env.lang)
                    ._render_qweb_pdf(report, payslip.id)
                )
                if report.print_report_name:
                    pdf_name = safe_eval(report.print_report_name, {"object": payslip})
                else:
                    pdf_name = generic_name
                attachments_vals_list.append(
                    {
                        "name": pdf_name,
                        "type": "binary",
                        "raw": pdf_content,
                        "res_model": payslip._name,
                        "res_id": payslip.id,
                    }
                )

        self.env["ir.attachment"].sudo().create(attachments_vals_list)
        # Send email to employees (after attachment is created to include it in the mail by other bridge module)
        for payslips in mapped_reports.values():
            for payslip in payslips:
                template = payslip._get_email_template()
                if template and payslip._check_send_payslip_mail():
                    template.send_mail(
                        payslip.id, email_layout_xmlid="mail.mail_notification_light"
                    )

    def _filtered_payslips_outside_contract(self):
        return self.filtered(
            lambda p: (
                not p.is_refund_payslip
                and p.version_id
                and p.date_from
                and p.date_to
                and (
                    not p.version_id.contract_date_start
                    or p.version_id.contract_date_start > p.date_to
                    or (
                        p.version_id.contract_date_end
                        and p.version_id.contract_date_end < p.date_from
                    )
                )
            )
        )

    def _get_send_trigger(self):
        """Return when payslips are handed to the PDF cron: the moment employees
        receive them, since `_generate_pdf` mails each one right after building it.

        One of `on_confirmed`, `on_paid` or `never`. The setting lives in
        `ir.config_parameter` rather than on `res.company` so that enabling it needs
        no migration, and an absent parameter reads as `on_confirmed` -- what the
        module did before the setting existed.
        """
        return self.env.registry.settings.get(
            self.env, "hr_payroll.payslip_generate_and_send_trigger", "on_confirmed"
        )

    def _queue_for_pdf(self) -> None:
        """Hand these payslips to the PDF cron and wake it up."""
        self.write({"queued_for_pdf": True})
        self.env["ir.cron"]._trigger_ref("hr_payroll.ir_cron_generate_payslip_pdfs")

    def action_payslip_done(self):
        if any(slip.state == "cancel" for slip in self):
            _debug.logic("done_refused", reason="cancelled", payslips=self)
            raise ValidationError(self.env._("You can't confirm cancelled payslips."))
        if self.filtered("error_count"):
            _debug.logic(
                "done_refused", reason="errors", payslips=self.filtered("error_count")
            )
            raise ValidationError(self._get_error_message())
        _debug.lifecycle("done", payslips=self)
        self.write(
            {
                "state": "validated",
                "done_date": fields.Datetime.now(),
            }
        )

        line_values = self._get_line_values(["NET"])

        if _debug.logic.enabled:
            _debug.logic(
                "negative_net_flagged",
                payslips=self.filtered(
                    lambda p: (
                        not p.credit_note and line_values["NET"][p.id]["total"] < 0
                    )
                ),
            )
        self.filtered(
            lambda p: not p.credit_note and line_values["NET"][p.id]["total"] < 0
        ).write({"has_negative_net_to_report": True})
        # Validate work entries for regular payslips (exclude end of year bonus, ...)
        regular_payslips = self.filtered(
            lambda p: p.struct_id.type_id.default_struct_id == p.struct_id
        )
        work_entries_domain = Domain.OR(
            [
                [
                    ("date", "<=", regular_payslip.date_to),
                    ("date", ">=", regular_payslip.date_from),
                    ("employee_id", "=", regular_payslip.employee_id.id),
                ]
                for regular_payslip in regular_payslips
            ]
        )
        work_entries = self.env["hr.work.entry"].search(work_entries_domain)
        _debug.pipeline(
            "work_entries_validated",
            payslips=regular_payslips,
            entries=work_entries,
        )
        if work_entries:
            work_entries.action_validate()

        if self.env.context.get("payslip_generate_pdf"):
            if self.env.context.get("payslip_generate_pdf_direct"):
                self._create_pdf_attachments()
            elif self._get_send_trigger() == "on_confirmed":
                self._queue_for_pdf()

    def action_validate(self):
        self.filtered(
            lambda slip: slip.state == "draft" and not slip.line_ids
        ).compute_sheet()
        self.filtered(lambda slip: slip.state == "draft").action_payslip_done()

    def action_payslip_cancel(self):
        if not self.env.user.has_group(
            "hr_payroll.group_hr_payroll_manager"
        ) and self.filtered(lambda slip: slip.state == "validated"):
            raise UserError(self.env._("Cannot cancel a payslip that is validated."))
        self.write({"state": "cancel"})
        self.action_draft_linked_entries()

    def action_payslip_paid(self) -> None:
        if any(slip.state not in ["validated", "paid"] for slip in self):
            raise UserError(self.env._("Cannot mark payslip as paid if not confirmed."))
        if self.filtered("error_count"):
            raise ValidationError(self._get_error_message())
        newly_paid = self.filtered(lambda p: p.state != "paid")
        newly_paid.write(
            {
                "state": "paid",
                "paid_date": fields.Date.today(),
            }
        )
        # Only what actually changed state: re-running the action over a batch that
        # is already paid must not mail every employee a second copy.
        if newly_paid and self._get_send_trigger() == "on_paid":
            newly_paid._queue_for_pdf()

    def action_payslip_payment_report(self, export_format="csv"):
        self.check_singleton()
        if len(self.payslip_run_id) > 1:
            raise UserError(
                self.env._("The selected payslips should be linked to the same batch")
            )
        return {
            "name": self.env._("Generate a Payment Report"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.hr.payslip.export.payment.file",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_payslip_ids": self.ids,
                "default_payslip_run_id": self.payslip_run_id.id,
                "default_export_format": export_format,
            },
        }

    def action_payslip_unpaid(self) -> None:
        if any(slip.state != "paid" for slip in self):
            raise UserError(
                self.env._(
                    "You cannot cancel the payment if the payslip has not been paid."
                )
            )
        self.write({"state": "validated"})
        self.payslip_run_id.write({"state": "02_close"})

    def action_view_work_entries(self):
        self.check_singleton()
        return self.employee_id.action_view_work_entries(initial_date=self.date_from)

    def action_view_salary_attachments(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Salary Adjustments"),
            "res_model": "hr.salary.attachment",
            "view_mode": "list,form",
            "domain": [("id", "in", self.salary_attachment_ids.ids)],
        }

    def action_keep_wrong_version(self) -> None:
        self.keep_wrong_version = True

    def action_adjust_payslip(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Payslip Correction"),
            "res_model": "wizard.hr.payslip.correct",
            "view_mode": "form",
            "view_id": "hr_payslip_correction_wizard_form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_employee_id": self.employee_id.id,
                "default_payslip_id": self.id,
            },
        }

    def action_view_related_payslips(self) -> dict:
        return {
            "name": self.env._("Related Payslip"),
            "res_model": "hr.payslip",
            "type": "ir.actions.act_window",
            "target": "current",
            "view_mode": "list, form",
            "views": [(False, "list"), (False, "form")],
            "domain": [("id", "in", self.related_payslip_ids.ids)],
        }

    def _get_payslips_action(self) -> dict:
        formview_ref = self.env.ref("hr_payroll.view_hr_payslip_form", False)
        listview_ref = self.env.ref("hr_payroll.view_hr_payslip_tree", False)
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Refund Payslip"),
            "res_model": "hr.payslip",
            "target": "current",
            "view_mode": "list,form",
            "views": [(listview_ref.id, "list"), (formview_ref.id, "form")],
            "domain": [("id", "in", self.ids)],
        }

    def _action_refund_payslips(self):
        reverted_payslips = self.env["hr.payslip"]
        for payslip in self:
            reverted_payslip = payslip.copy(
                {
                    "credit_note": True,
                    "name": self.env._("Refund: %(payslip)s", payslip=payslip.name),
                    "edited": True,
                    "state": "draft",
                    "origin_payslip_id": payslip.id,
                    "is_refund_payslip": True,
                }
            )
            for wd in reverted_payslip.worked_days_line_ids:
                wd.number_of_hours = -wd.number_of_hours
                wd.number_of_days = -wd.number_of_days
                wd.amount = -wd.amount
            for line in reverted_payslip.line_ids:
                line.amount = -line.amount
                line.total = -line.total
            reverted_payslips |= reverted_payslip
            payslip.message_post(
                body=self.env._(
                    "This is a refunded payslip.\nFind the refund under this name: %(payslip)s",
                    payslip=reverted_payslip.name,
                )
            )
            payslip.is_refunded = True
        return reverted_payslips

    def _action_correct_payslips(self):
        corrected_payslips_values = []
        for payslip in self:
            corrected_name = self.env._("Correction: %(payslip)s", payslip=payslip.name)
            corrected_payslips_values.append(
                {
                    "name": corrected_name,
                    "origin_payslip_id": payslip.id,
                    "employee_id": payslip.employee_id.id,
                    "version_id": payslip.employee_id._get_version(
                        date=payslip.date_from
                    ).id,
                    "date_from": payslip.date_from,
                    "date_to": payslip.date_to,
                }
            )
            payslip.message_post(
                body=self.env._(
                    "This is a corrected payslip.\nFind the correction under this name: %(payslip)s",
                    payslip=corrected_name,
                )
            )
            payslip.is_corrected = True
        corrected_payslips = self.env["hr.payslip"].create(corrected_payslips_values)
        corrected_payslips.compute_sheet()
        return corrected_payslips

    def refund_sheet(self):
        reverted_payslips = self._action_refund_payslips()
        return (self | reverted_payslips)._get_payslips_action()

    def correct_sheet(self):
        reverted_payslips = self._action_refund_payslips()
        corrected_payslips = self._action_correct_payslips()
        return (self | corrected_payslips | reverted_payslips)._get_payslips_action()

    @api.ondelete(at_uninstall=False)
    def _unlink_if_draft_or_cancel(self) -> None:
        if any(payslip.state not in ("draft", "cancel") for payslip in self):
            raise UserError(
                self.env._(
                    "Oops! Only draft and cancelled payslips can be deleted without causing any chaos. We can't "
                    "take back our dedicated employees' hard-earned cash!"
                )
            )
        self.action_draft_linked_entries()

    def compute_sheet(self):
        payslips = self.filtered(lambda slip: slip.state == "draft")
        payslips.employee_id._apply_pending_version_vals()
        _debug.pipeline(
            "compute_sheet", requested=self, draft=payslips, skipped=self - payslips
        )
        if payslips.filtered("error_count"):
            _debug.logic(
                "compute_refused",
                reason="errors",
                payslips=payslips.filtered("error_count"),
            )
            raise ValidationError(self._get_error_message())
        # delete old payslip lines
        payslips.line_ids.unlink()
        # this guarantees consistent results
        self.env.flush_all()
        today = fields.Date.today()
        for payslip in payslips:
            payslip.write({"state": "draft", "compute_date": today})
        self.env["hr.payslip.line"].create(payslips._get_payslip_lines())
        if any(payslips.mapped("ytd_computation")):
            self._update_worked_days_ytd()
        return True

    def action_refresh_from_work_entries(self):
        # Refresh the whole payslip in case the HR has modified some work entries
        # after the payslip generation
        if any(p.state != "draft" for p in self):
            _debug.logic("refresh_refused", reason="not_draft", payslips=self)
            raise UserError(
                self.env._("The payslips should be in Draft or Waiting state.")
            )
        payslips = self.filtered(lambda p: not p.edited)
        _debug.pipeline(
            "refresh_from_work_entries",
            payslips=self,
            refreshed=payslips,
            edited_kept=self - payslips,
        )
        payslips._update_payslip_properties()
        payslips.mapped("worked_days_line_ids").unlink()
        payslips.mapped("line_ids").unlink()
        payslips._compute_worked_days_line_ids()
        payslips.compute_sheet()

    def action_move_to_off_cycle(self) -> None:
        self.payslip_run_id = False

    def _round_days(self, work_entry_type, days):
        if work_entry_type.round_days != "NO":
            precision_rounding = 0.5 if work_entry_type.round_days == "HALF" else 1
            return float_round(
                days,
                precision_rounding=precision_rounding,
                rounding_method=work_entry_type.round_days_type,
            )
        return days

    @api.model
    def _get_attachment_types(self) -> dict:
        input_types = self.env["hr.payslip.input.type"].search(
            [("available_in_attachments", "=", True)]
        )
        return {input_type.code: input_type for input_type in input_types}

    def _get_worked_day_lines_hours_per_day(self):
        self.check_singleton()
        calendar = (
            self.version_id.resource_calendar_id
            or self.employee_id.resource_calendar_id
            or self.company_id.resource_calendar_id
        )
        return calendar.hours_per_day

    def _get_worked_day_lines_hours_per_week(self):
        self.check_singleton()
        calendar = (
            self.version_id.resource_calendar_id
            or self.employee_id._get_calendars()[self.employee_id.id]
        )
        return calendar.hours_per_week

    def _get_out_of_contract_calendar(self):
        self.check_singleton()
        return (
            self.version_id.resource_calendar_id
            or self.employee_id.resource_calendar_id
            or self.company_id.resource_calendar_id
        )

    def _prepare_worked_day_attendance_vals(self, domain=None):
        self.check_singleton()
        res = []
        hours_per_day = self._get_worked_day_lines_hours_per_day()
        with _debug.perf(
            "work_hours", cr=self.env.cr, payslip=self, hours_per_day=hours_per_day
        ) as span:
            work_hours = self.version_id.get_work_hours(
                self.date_from, self.date_to, domain=domain
            )
            span.set(types=len(work_hours))
        work_hours_ordered = sorted(work_hours.items(), key=lambda x: x[1])
        biggest_work = work_hours_ordered[-1][0] if work_hours_ordered else 0
        add_days_rounding = 0
        for work_entry_type_id, hours in work_hours_ordered:
            work_entry_type = self.env["hr.work.entry.type"].browse(work_entry_type_id)
            days = round(hours / hours_per_day, 5) if hours_per_day else 0
            if work_entry_type_id == biggest_work:
                days += add_days_rounding
            day_rounded = self._round_days(work_entry_type, days)
            add_days_rounding += days - day_rounded
            attendance_line = {
                "sequence": work_entry_type.sequence,
                "work_entry_type_id": work_entry_type_id,
                "number_of_days": day_rounded,
                "number_of_hours": hours,
            }
            res.append(attendance_line)

        # Sort by Work Entry Type sequence
        work_entry_type = self.env["hr.work.entry.type"]
        return sorted(
            res, key=lambda d: work_entry_type.browse(d["work_entry_type_id"]).sequence
        )

    def _prepare_worked_day_vals(self, domain=None, check_out_of_version=True):
        """
        :returns: a list of dict containing the worked days values that should be applied for the given payslip
        """
        res = []
        self.check_singleton()
        version = self.version_id
        res = self._prepare_worked_day_attendance_vals(domain=domain)
        if not check_out_of_version:
            return res

        # If the version doesn't cover the whole month, create
        # worked_days lines to adapt the wage accordingly
        out_days, out_hours = 0, 0
        reference_calendar = self._get_out_of_contract_calendar()
        if self.date_from < version.date_start:
            start = fields.Datetime.to_datetime(self.date_from)
            stop = min(
                fields.Datetime.to_datetime(version.date_start)
                + relativedelta(days=-1, hour=23, minute=59),
                fields.Datetime.to_datetime(self.date_to)
                + relativedelta(hour=23, minute=59),
            )
            out_time = reference_calendar.get_attendance_duration_data(
                start,
                stop,
                domain=[
                    "|",
                    ("work_entry_type_id", "=", False),
                    ("work_entry_type_id.is_leave", "=", False),
                ],
            )
            out_days += out_time["days"]
            out_hours += out_time["hours"]
        if version.date_end and version.date_end < self.date_to:
            start = max(
                fields.Datetime.to_datetime(version.date_end) + relativedelta(days=1),
                fields.Datetime.to_datetime(self.date_from),
            )
            stop = fields.Datetime.to_datetime(self.date_to) + relativedelta(
                hour=23, minute=59
            )
            out_time = reference_calendar.get_attendance_duration_data(
                start,
                stop,
                domain=[
                    "|",
                    ("work_entry_type_id", "=", False),
                    ("work_entry_type_id.is_leave", "=", False),
                ],
            )
            out_days += out_time["days"]
            out_hours += out_time["hours"]

        work_entry_type = self.env.ref(
            "hr_work_entry.hr_work_entry_type_out_of_contract", raise_if_not_found=False
        )
        if work_entry_type and (out_days or out_hours):
            res.append(
                {
                    "sequence": work_entry_type.sequence,
                    "work_entry_type_id": work_entry_type.id,
                    "number_of_days": out_days,
                    "number_of_hours": out_hours,
                }
            )
        return res

    @property
    def paid_amount(self):
        self.check_singleton()
        return self._get_paid_amount()

    @property
    def is_outside_contract(self) -> bool:
        self.check_singleton()
        if self.env.context.get("salary_simulation"):
            return False
        return bool(self._is_outside_contract_dates())

    def _rule_parameter(self, code, reference_date=False):
        self.check_singleton()
        if reference_date:
            return self.env["hr.rule.parameter"]._get_parameter_from_code(
                code, reference_date
            )
        else:
            return self.env["hr.rule.parameter"]._get_parameter_from_code(
                code, self.date_to
            )

    def _sum(self, code, from_date, to_date=None):
        if to_date is None:
            to_date = fields.Date.today()

        self.env["hr.payslip"].flush_model(
            ["employee_id", "state", "date_from", "date_to"]
        )
        self.env["hr.payslip.line"].flush_model(["total", "slip_id", "code"])

        self.env.cr.execute(
            """
            SELECT sum(pl.total)
            FROM hr_payslip as hp, hr_payslip_line as pl
            WHERE hp.employee_id = %s
            AND hp.state in ('validated', 'paid')
            AND hp.date_from >= %s
            AND hp.date_to <= %s
            AND hp.id = pl.slip_id
            AND pl.code = %s""",
            (self.employee_id.id, from_date, to_date, code),
        )
        res = self.env.cr.fetchone()
        return (res and res[0]) or 0.0

    def _get_category_sum(self, code, from_date, to_date=None):
        self.check_singleton()
        if to_date is None:
            to_date = fields.Date.today()

        self.env["hr.payslip"].flush_model(
            ["employee_id", "state", "date_from", "date_to"]
        )
        self.env["hr.payslip.line"].flush_model(["total", "slip_id", "salary_rule_id"])
        self.env["hr.salary.rule.category"].flush_model(["code"])

        self.env.cr.execute(
            """
            SELECT sum(pl.total)
            FROM
                hr_payslip as hp,
                hr_payslip_line as pl,
                hr_salary_rule_category as rc,
                hr_salary_rule as sr
            WHERE hp.employee_id = %s
            AND hp.state in ('validated', 'paid')
            AND hp.date_from >= %s
            AND hp.date_to <= %s
            AND hp.id = pl.slip_id
            AND sr.id = pl.salary_rule_id
            AND rc.id = sr.category_id
            AND rc.code = %s""",
            (self.employee_id.id, from_date, to_date, code),
        )
        res = self.env.cr.fetchone()
        return (res and res[0]) or 0.0

    def _get_worked_days_sum(self, code, from_date, to_date=None):
        self.check_singleton()
        if to_date is None:
            to_date = fields.Date.today()

        self.env["hr.payslip"].flush_model(
            ["employee_id", "state", "date_from", "date_to"]
        )
        self.env["hr.payslip.worked_days"].flush_model(
            ["amount", "payslip_id", "work_entry_type_id"]
        )
        self.env["hr.work.entry.type"].flush_model(["code"])

        query = """
            SELECT sum(hwd.amount)
            FROM hr_payslip hp, hr_payslip_worked_days hwd, hr_work_entry_type hwet
            WHERE hp.state in ('validated', 'paid')
            AND hp.id = hwd.payslip_id
            AND hwet.id = hwd.work_entry_type_id
            AND hp.employee_id = %(employee)s
            AND hp.date_to <= %(stop)s
            AND hwet.code = %(code)s
            AND hp.date_from >= %(start)s"""

        self.env.cr.execute(
            query,
            {
                "employee": self.employee_id.id,
                "code": code,
                "start": from_date,
                "stop": to_date,
            },
        )
        res = self.env.cr.fetchone()
        # SUM() over no rows still returns one row holding NULL, so `res` is
        # truthy and `res[0]` is None. The two sibling helpers above both
        # guard that with `or 0.0`; this one returned None to salary rules
        # that then did arithmetic on it.
        return (res and res[0]) or 0.0

    def _prepare_salary_rule_base_context(self):
        return {
            "float_round": float_round,
            "float_compare": float_compare,
            "relativedelta": safe_eval_dateutil.relativedelta.relativedelta,
            "ceil": math.ceil,
            "floor": math.floor,
            "UserError": UserError,
            "date": safe_eval_datetime.date,
            "datetime": safe_eval_datetime.datetime,
            "defaultdict": defaultdict,
        }

    def _prepare_salary_rule_context(self):
        self.check_singleton()
        # Check for multiple inputs of the same type and keep a copy of
        # them because otherwise they are lost when building the dict
        same_type_input_lines = defaultdict(lambda: self.env["hr.payslip.input"])
        input_line_ids_by_code = self.input_line_ids.grouped("code")
        for code, input_lines in input_line_ids_by_code.items():
            if len(input_lines) > 1:
                same_type_input_lines[code] = input_lines

        employee_properties = dict(self.version_id.payroll_properties)
        payslip_properties = dict(self.payslip_properties)
        employee_properties.update(payslip_properties)
        # Only the salary-rule entries are inputs. A group separator is keyed
        # `separator_<section id>`, and the properties widget writes its fold
        # state there as a value, so it reaches us like any other entry.
        property_inputs = {
            int(rule_id): float(value)
            for rule_id, value in employee_properties.items()
            if rule_id.isdigit()
        }

        localdict = {
            **self._prepare_salary_rule_base_context(),
            "categories": DefaultDictPayroll(lambda: 0),
            "rules": DefaultDictPayroll(
                lambda: {"total": 0, "amount": 0, "quantity": 0}
            ),
            "payslip": self,
            "worked_days": {
                line.code: line for line in self.worked_days_line_ids if line.code
            },
            "property_inputs": property_inputs,
            "inputs": {line.code: line for line in self.input_line_ids if line.code},
            "employee": self.employee_id,
            "version": self.version_id,
            "result_rules": DefaultDictPayroll(
                lambda: {"total": 0, "amount": 0, "quantity": 0, "rate": 0, "ytd": 0}
            ),
            "same_type_input_lines": same_type_input_lines,
        }
        for code, input_lines in same_type_input_lines.items():
            input_line_ids = input_lines.ids
            localdict["inputs"][code] = self.__get_aggregator_hr_payslip_input_model()(
                env=self.env,
                ids=tuple(input_line_ids),
                prefetch_ids=tuple(input_line_ids),
            )
        return localdict

    def _get_payslip_line_total(self, amount, quantity, rate, rule):
        self.check_singleton()
        return amount * quantity * rate / 100.0

    def _get_last_ytd_payslips(self):
        if not self:
            # Both callers index this and call `.values()` on it, so the
            # empty case has to be the same kind of thing as the full one.
            # Returning the empty recordset made `_update_worked_days_ytd()`
            # raise AttributeError instead of doing nothing.
            return defaultdict(lambda: self.env["hr.payslip"])

        earliest_date_to = min(self.mapped("date_to"))
        earliest_ytd_date_to = min(
            company.get_last_ytd_reset_date(earliest_date_to)
            for company in self.mapped("company_id")
        )
        ytd_payslips_grouped = self.env["hr.payslip"]._read_group(
            domain=[
                ("employee_id", "in", self.employee_id.ids),
                ("struct_id", "in", self.struct_id.ids),
                ("ytd_computation", "=", True),
                ("date_to", ">=", earliest_ytd_date_to),
                ("date_to", "<=", max(self.mapped("date_to"))),
                ("state", "in", ["validated", "paid"]),
            ],
            groupby=["employee_id", "struct_id"],
            aggregates=["id:recordset"],
        )

        ytd_payslips_sorted = defaultdict(lambda: self.env["hr.payslip"])
        for employee_id, struct_id, payslips in ytd_payslips_grouped:
            ytd_payslips_sorted[(employee_id, struct_id)] = payslips.sorted(
                key=lambda p: p.date_to, reverse=True
            )

        last_ytd_payslips = defaultdict(lambda: self.env["hr.payslip"])
        for payslip in self:
            last_payslip = ytd_payslips_sorted[
                (payslip.employee_id, payslip.struct_id)
            ].filtered_domain([("date_to", "<=", payslip.date_to)])[:1]
            if last_payslip and (
                last_payslip.date_to
                >= payslip.company_id.get_last_ytd_reset_date(payslip.date_to)
            ):
                last_ytd_payslips[payslip] = last_payslip

        return last_ytd_payslips

    def _get_payslip_lines(self, forced_localdict=None, blacklisted_rule_ids=()):
        def get_rule_name(localdict, rule):
            if localdict["result_name"]:
                return localdict["result_name"]
            if (
                rule.amount_select == "input"
                and rule.amount_other_input_id.code in localdict["inputs"]
                and (name := localdict["inputs"][rule.amount_other_input_id.code].name)
            ):
                return name
            return rule.name

        line_vals = []

        if any(self.mapped("ytd_computation")):
            last_ytd_payslips = self._get_last_ytd_payslips()
            code_set = set(self.struct_id.rule_ids.mapped("code"))
        else:
            last_ytd_payslips = defaultdict(lambda: self.env["hr.payslip"])
            code_set = set()
        ytd_payslips = reduce(
            lambda ytd_payslips, payslip: ytd_payslips | payslip,
            last_ytd_payslips.values(),
            self.env["hr.payslip"],
        )

        line_values = ytd_payslips._get_line_values(code_set, ["ytd"])
        _debug.pipeline(
            "rule_engine_start",
            payslips=self,
            ytd_codes=len(code_set),
            ytd_payslips=ytd_payslips,
            blacklisted=len(blacklisted_rule_ids),
        )

        for payslip in self:
            if lang := payslip.employee_id.lang:
                # /!\ Don't remove /!\ ensure that the employee will receive their payslip in their language.
                payslip = payslip.with_context(lang=lang)

            localdict = (
                forced_localdict
                if forced_localdict is not None
                else payslip._prepare_salary_rule_context()
            )
            result_rules_dict = localdict["result_rules"]

            result = {}
            payslip_line_vals = []
            try:
                for rule in sorted(
                    payslip.struct_id.rule_ids, key=lambda x: x.sequence
                ):
                    if rule.id in blacklisted_rule_ids:
                        continue
                    localdict.update(
                        {
                            "result": None,
                            "result_qty": 1.0,
                            "result_rate": 100,
                            "result_name": False,
                        }
                    )
                    if rule._satisfy_condition(localdict):
                        if rule.code in localdict["same_type_input_lines"]:
                            for multi_line_rule in localdict["same_type_input_lines"][
                                rule.code
                            ]:
                                localdict["inputs"][rule.code] = multi_line_rule
                                amount, qty, rate = rule._compute_rule(localdict)
                                tot_rule = payslip._get_payslip_line_total(
                                    amount, qty, rate, rule
                                )
                                ytd = (
                                    line_values[rule.code][
                                        last_ytd_payslips[payslip].id
                                    ]["ytd"]
                                    + tot_rule
                                )

                                result_rules_dict[rule.code]["total"] += tot_rule
                                result_rules_dict[rule.code]["amount"] += tot_rule
                                result_rules_dict[rule.code]["quantity"] = 1
                                result_rules_dict[rule.code]["rate"] = 100
                                result_rules_dict[rule.code]["ytd"] = ytd

                                if rule.category_id:
                                    localdict = (
                                        rule.category_id._get_salary_rule_category_sum(
                                            localdict, tot_rule
                                        )
                                    )
                                payslip_line_vals.append(
                                    {
                                        "sequence": rule.sequence,
                                        "code": rule.code,
                                        "name": get_rule_name(localdict, rule),
                                        "salary_rule_id": rule.id,
                                        "version_id": localdict["version"].id,
                                        "employee_id": localdict["employee"].id,
                                        "amount": amount,
                                        "quantity": qty,
                                        "rate": rate,
                                        "total": tot_rule,
                                        "slip_id": payslip.id,
                                        "ytd": ytd,
                                    }
                                )
                            input_line_ids = localdict["same_type_input_lines"][
                                rule.code
                            ].ids
                            localdict["inputs"][rule.code] = (
                                self.__get_aggregator_hr_payslip_input_model()(
                                    env=self.env,
                                    ids=tuple(input_line_ids),
                                    prefetch_ids=tuple(input_line_ids),
                                )
                            )
                        else:
                            amount, qty, rate = rule._compute_rule(localdict)
                            # check if there is already a rule computed with that code
                            previous_amount = localdict.get(rule.code, 0.0)
                            # set/overwrite the amount computed for this rule in the localdict
                            tot_rule = payslip._get_payslip_line_total(
                                amount, qty, rate, rule
                            )
                            ytd = (
                                line_values[rule.code][last_ytd_payslips[payslip].id][
                                    "ytd"
                                ]
                                + tot_rule
                            )
                            localdict[rule.code] = tot_rule
                            result_rules_dict[rule.code] = {
                                "total": tot_rule,
                                "amount": amount,
                                "quantity": qty,
                                "rate": rate,
                                "ytd": ytd,
                            }
                            # sum the amount for its salary category, if it has one
                            if rule.category_id:
                                localdict = (
                                    rule.category_id._get_salary_rule_category_sum(
                                        localdict, tot_rule - previous_amount
                                    )
                                )
                            # create/overwrite the rule in the temporary results
                            result[rule.code] = {
                                "sequence": rule.sequence,
                                "code": rule.code,
                                "name": get_rule_name(localdict, rule),
                                "salary_rule_id": rule.id,
                                "version_id": localdict["version"].id,
                                "employee_id": localdict["employee"].id,
                                "amount": amount,
                                "quantity": qty,
                                "rate": rate,
                                "total": tot_rule,
                                "slip_id": payslip.id,
                                "ytd": ytd,
                            }
            except UserError as error:
                # A malformed salary rule (bad python code/condition/quantity)
                # on ONE employee must not abort compute_sheet() for the whole
                # batch: report it and keep computing the other payslips. A
                # single payslip has nobody else to protect, so it tells the user.
                if len(self) == 1:
                    _debug.logic(
                        "rule_error_raised", payslip=payslip, error=type(error).__name__
                    )
                    raise
                _debug.logic(
                    "rule_error_skipped",
                    payslip=payslip,
                    employee=payslip.employee_id,
                    batch=len(self),
                )
                _logger.warning(
                    "Payslip %s (%s) could not be computed: %s",
                    payslip.id,
                    payslip.employee_id.name,
                    error,
                )
                continue
            _debug.perf.count(
                "rules_evaluated",
                payslip=payslip,
                rules=len(payslip.struct_id.rule_ids),
                lines=len(payslip_line_vals) + len(result),
            )
            line_vals += payslip_line_vals
            line_vals += list(result.values())
        _debug.pipeline("rule_engine_done", payslips=self, lines=len(line_vals))
        return line_vals

    def _update_worked_days_ytd(self) -> None:
        last_ytd_payslips = self._get_last_ytd_payslips()
        ytd_payslips = reduce(
            lambda ytd_payslips, payslip: ytd_payslips | payslip,
            last_ytd_payslips.values(),
            self.env["hr.payslip"],
        )

        code_set = set(self.worked_days_line_ids.mapped("code"))
        worked_days_line_values = ytd_payslips._get_worked_days_line_values(
            code_set, ["ytd"]
        )

        for payslip in self:
            for worked_days in payslip.worked_days_line_ids:
                worked_days.ytd = (
                    worked_days_line_values[worked_days.code][
                        last_ytd_payslips[payslip].id
                    ]["ytd"]
                    + worked_days.amount
                )

    @api.depends("employee_id")
    def _compute_company_id(self):
        for slip in self.filtered(lambda p: p.employee_id):
            slip.company_id = slip.employee_id.company_id

    @api.depends("employee_id", "date_from")
    def _compute_version_id(self) -> None:
        for slip in self:
            slip.version_id = (
                slip.employee_id._get_version(slip.date_from)
                if slip.employee_id
                else False
            )

    @api.depends("version_id")
    def _compute_struct_id(self) -> None:
        for slip in self.filtered(lambda p: not p.struct_id):
            slip.struct_id = (
                slip.version_id.structure_type_id.default_struct_id
                or slip.employee_id.version_id.structure_type_id.default_struct_id
            )

    def _search_country_id(self, operator, value) -> list:
        return [("company_id.partner_id.country_id", operator, value)]

    def _get_period_name(self, cache):
        self.check_singleton()
        period_name = "%s - %s" % (
            self._format_date_cached(cache, self.date_from),
            self._format_date_cached(cache, self.date_to),
        )
        if self.is_wrong_duration:
            return period_name

        start_date = self.date_from
        end_date = self.date_to
        lang = self.employee_id.lang or self.env.user.lang
        week_start = self.env["res.lang"]._get_data(code=lang).week_start
        schedule = (
            self.version_id.schedule_pay
            or self.version_id.structure_type_id.default_schedule_pay
        )
        if schedule == "monthly":
            # "y" is the calendar year. Capital "Y" is the WEEK-numbering
            # year, which disagrees with it whenever the date sits in the
            # first or last days of a year -- enough to name a January
            # payslip after the previous year.
            period_name = self._format_date_cached(cache, start_date, "MMMM y")
        elif schedule == "quarterly":
            current_year_quarter = get_quarter_number(start_date)
            period_name = self.env._(
                "Quarter %(quarter)s of %(year)s",
                quarter=current_year_quarter,
                year=start_date.year,
            )
        elif schedule == "semi-annually":
            year_half = start_date.replace(day=1, month=6)
            is_first_half = start_date < year_half
            period_name = (
                self.env._("1st semester of %s", start_date.year)
                if is_first_half
                else self.env._("2nd semester of %s", start_date.year)
            )
        elif schedule == "annually":
            period_name = start_date.year
        elif schedule == "weekly":
            wk_num = (
                start_date.strftime("%U")
                if week_start == "7"
                else start_date.strftime("%W")
            )
            period_name = self.env._(
                "Week %(week_number)s of %(year)s",
                week_number=wk_num,
                year=start_date.year,
            )
        elif schedule == "bi-weekly":
            week = int(
                start_date.strftime("%U")
                if week_start == "7"
                else start_date.strftime("%W")
            )
            first_week = week - 1 + week % 2
            period_name = self.env._(
                "Weeks %(week)s and %(week1)s of %(year)s",
                week=first_week,
                week1=first_week + 1,
                year=start_date.year,
            )
        elif schedule == "bi-monthly":
            start_date_string = self._format_date_cached(cache, start_date, "MMMM y")
            end_date_string = self._format_date_cached(cache, end_date, "MMMM y")
            period_name = self.env._(
                "%(start_date_string)s and %(end_date_string)s",
                start_date_string=start_date_string,
                end_date_string=end_date_string,
            )
        return period_name

    def _format_date_cached(self, cache, date, date_format=False):
        lang = self.employee_id.lang or self.env.user.lang
        key = (date, date_format, lang)
        if key not in cache:
            cache[key] = format_date(
                env=self.env, value=date, lang_code=lang, date_format=date_format
            )
        return cache[key]

    @api.depends(
        "employee_id.legal_name",
        "employee_id.lang",
        "struct_id",
        "struct_id.payslip_name",
        "date_from",
        "date_to",
        # `_get_period_name` below branches on the schedule, so the name has
        # to follow the version too, not only the fields of the payslip.
        "version_id",
        "version_id.schedule_pay",
        "version_id.structure_type_id.default_schedule_pay",
    )
    def _compute_name(self):
        formated_date_cache = {}
        for slip in self.filtered(
            lambda p: p.employee_id and p.date_from and p.date_to
        ):
            lang = slip.employee_id.lang or self.env.user.lang
            payslip_name = slip.struct_id.payslip_name or self.with_context(
                lang=lang
            ).env._("Salary Slip")

            slip.name = "%(payslip_name)s - %(employee_name)s - %(dates)s" % {
                "payslip_name": payslip_name,
                "employee_name": slip.employee_id.legal_name,
                "dates": slip._get_period_name(formated_date_cache),
            }

    @api.model
    def _issues_dependencies(self):
        return [
            "state",
            "date_to",
            "date_from",
            "employee_id",
            "version_id",
            "version_id.contract_date_start",
            "version_id.contract_date_end",
            "version_id.schedule_pay",
            "version_id.active",
            "struct_id",
            "version_id.structure_type_id.default_schedule_pay",
            "company_id",
            "payslip_run_id.company_id",
            "payslip_run_id.date_start",
            "payslip_run_id.date_end",
            "employee_id.salary_bank_account_ids",
            "employee_id.salary_bank_account_ids.allow_out_payment",
            "salary_attachment_ids.state",
        ]

    def _get_errors_by_slip(self):
        by_state = self.grouped("state")
        draft_slips = by_state.get("draft", self.env["hr.payslip"])
        errors_by_slip = {slip: [] for slip in self}
        for slip in draft_slips._filtered_payslips_outside_contract():
            errors_by_slip[slip].append(
                {
                    "message": self.env._("No running contract over payslip period"),
                    "action_text": self.env._("Contract"),
                    "action": slip.employee_id._get_records_action(
                        name=self.env._("Employee"),
                        target="new",
                        context={**self.env.context, "version_id": slip.version_id.id},
                    ),
                    "level": "danger",
                }
            )
        for slip in draft_slips.filtered(
            lambda slip: (
                slip.payslip_run_id
                and slip.company_id != slip.payslip_run_id.company_id
            )
        ):
            errors_by_slip[slip].append(
                {
                    "message": self.env._(
                        "The payslip's company doesn't match the batch's"
                    ),
                    "action_text": self.env._("Batch"),
                    "action": slip.payslip_run_id._get_records_action(),
                    "level": "danger",
                }
            )
        # A salary simulation computes on a throwaway archived copy of the version.
        pinned_slips = (
            draft_slips.browse()
            if self.env.context.get("salary_simulation")
            else draft_slips
        )
        for slip in pinned_slips.filtered(
            lambda slip: slip.version_id and not slip.version_id.active
        ):
            errors_by_slip[slip].append(
                {
                    "message": self.env._(
                        "The employee record of this payslip is archived"
                    ),
                    "action_text": self.env._("Employee Record"),
                    "action": slip.version_id._get_records_action(),
                    "level": "danger",
                }
            )
        return errors_by_slip

    def _get_warnings_by_slip(self):
        similar_payslips = self._get_similar_payslips()
        warnings_by_slip = {slip: [] for slip in self}

        for slip in self.filtered(
            lambda s: s.state in ["draft", "validated"] and s.date_from and s.date_to
        ):
            warnings = []
            if (
                slip.struct_id.use_worked_day_lines
                and (
                    slip.version_id.schedule_pay
                    or slip.version_id.structure_type_id.default_schedule_pay
                )
                and slip.date_from
                and slip.date_from + slip._get_schedule_timedelta() != slip.date_to
            ):
                warnings.append(
                    {
                        "message": self.env._(
                            "The duration of the payslip is not accurate according to the structure type."
                        ),
                        "level": "warning",
                    }
                )

            if slip.employee_id and slip.struct_id and slip.date_from and slip.date_to:
                key = (
                    slip.employee_id.id,
                    slip.struct_id.id,
                    slip.date_from,
                    slip.date_to,
                )
                duplicates = similar_payslips[key] - slip
                # Ignore duplicate warning if this slip is a refund of the original
                if duplicates:
                    related_payslips = self.env["hr.payslip"]
                    if slip.origin_payslip_id:
                        related_payslips |= (
                            slip.origin_payslip_id
                            | slip.origin_payslip_id.related_payslip_ids
                        )
                    if slip.related_payslip_ids:
                        related_payslips |= slip.related_payslip_ids
                    duplicates -= related_payslips

                if duplicates:
                    warnings.append(
                        {
                            "message": self.env._("Similar payslips found"),
                            "action_text": self.env._("Duplicate(s)"),
                            "action": duplicates._get_records_action(),
                            "level": "warning",
                        }
                    )
            run = slip.payslip_run_id
            if run and (
                run.date_start != slip.date_from or run.date_end != slip.date_to
            ):
                warnings.append(
                    {
                        "message": self.env._(
                            "The payslip period does not match the pay run"
                        ),
                        "action_text": self.env._("Pay Run"),
                        "action": run._get_records_action(),
                        "level": "warning",
                    }
                )
            warnings.extend(
                {
                    "message": self.env._(
                        "Related salary adjustment has been closed since the "
                        "creation of this payslip"
                    ),
                    "action_text": self.env._("Adjustment"),
                    "action": attachment._get_records_action(),
                    "level": "warning",
                }
                for attachment in slip.salary_attachment_ids.filtered(
                    lambda a: a.state == "close"
                )
            )
            warnings_by_slip[slip] = warnings

        # Payment report related errors
        for employee_banks, slips in (
            self.filtered(lambda ps: ps.state == "validated")
            .grouped(lambda ps: ps.employee_id.salary_bank_account_ids)
            .items()
        ):
            if not employee_banks:
                for slip in slips:
                    warnings_by_slip[slip].append(
                        {
                            "message": self.env._("Missing bank account on employee"),
                            "action_text": self.env._("Employee"),
                            "action": slip.employee_id._get_records_action(),
                            "level": "warning",
                        }
                    )
            elif any(not b.allow_out_payment for b in employee_banks):
                warning = {
                    "message": self.env._("Untrusted bank accounts"),
                    "action_text": self.env._("Bank Accounts"),
                    "action": employee_banks._get_records_action(),
                    "level": "warning",
                }
                for slip in slips:
                    warnings_by_slip[slip].append(warning)
        return warnings_by_slip

    @api.depends(lambda self: self._issues_dependencies())
    def _compute_issues(self) -> None:
        with _debug.perf("issues", cr=self.env.cr, payslips=self) as span:
            errors_by_slip = self._get_errors_by_slip()
            warnings_by_slip = self._get_warnings_by_slip()
            span.set(
                with_errors=len(errors_by_slip), with_warnings=len(warnings_by_slip)
            )

        for slip in self:
            warnings = warnings_by_slip[slip]
            errors = errors_by_slip[slip]
            slip.warning_count = len(warnings)
            slip.error_count = len(errors)
            if not errors and not warnings:
                slip.issues = {}
            else:
                slip.issues = dict(enumerate(errors + warnings))

    def _get_error_message(self):
        if len(self) == 1:
            return "\n".join(
                [
                    f" • {issue['message']}"
                    for issue in self.issues.values()
                    if issue["level"] == "danger"
                ]
            )
        return "\n".join(
            [
                f" • {slip.name}: {issue['message']}"
                for slip in self
                for issue in (slip.issues or {}).values()
                if issue["level"] == "danger"
            ]
        )

    @api.depends("date_from", "date_to", "struct_id")
    def _compute_is_wrong_duration(self) -> None:
        for slip in self:
            slip.is_wrong_duration = (
                slip.date_to
                and (
                    slip.version_id.schedule_pay
                    or slip.version_id.structure_type_id.default_schedule_pay
                )
                and (slip.date_from + slip._get_schedule_timedelta() != slip.date_to)
            )

    @api.depends("employee_id", "version_id", "struct_id", "date_from", "date_to")
    def _compute_worked_days_line_ids(self) -> None:
        if not self or self.env.context.get("salary_simulation"):
            return
        valid_slips = self.filtered(
            lambda p: (
                p.employee_id
                and p.date_from
                and p.date_to
                and p.version_id
                and p.struct_id
                and p.struct_id.use_worked_day_lines
            )
        )
        if not valid_slips:
            return
        # Make sure to reset invalid payslip's worked days line
        self.update({"worked_days_line_ids": [Command.clear()]})
        # Ensure work entries are generated for all contracts
        generate_from = min(p.date_from for p in valid_slips) + relativedelta(days=-1)
        generate_to = max(p.date_to for p in valid_slips) + relativedelta(days=1)
        self.version_id.filtered(
            lambda version: (
                version.resource_calendar_id.schedule_type != "fully_flexible"
            )
        ).generate_work_entries(generate_from, generate_to)
        work_entries = self.env["hr.work.entry"].search(
            [
                ("date", "<=", generate_to),
                ("date", ">=", generate_from),
                ("version_id", "in", self.version_id.ids),
            ]
        )
        work_entries_by_version = defaultdict(lambda: self.env["hr.work.entry"])
        for work_entry in work_entries:
            work_entries_by_version[work_entry.version_id.id] += work_entry

        for slip in valid_slips:
            if not slip.struct_id.use_worked_day_lines:
                continue

            payslip_work_entries = work_entries_by_version[
                slip.version_id
            ].filtered_domain(
                [
                    ("date", "<=", slip.date_to),
                    ("date", ">=", slip.date_from),
                ]
            )
            payslip_work_entries._check_undefined_slots(slip.date_from, slip.date_to)
            # We can't use a batched create here as the payslip may not exist yet
            slip.update(
                {"worked_days_line_ids": slip._prepare_worked_days_line_commands()}
            )

    def _get_similar_payslips(self):
        done_payslips = self.filtered(
            lambda p: p.employee_id and p.struct_id and p.date_from and p.date_to
        )
        search_domain = [
            ("employee_id", "in", done_payslips.employee_id.ids),
            ("struct_id", "in", done_payslips.struct_id.ids),
            ("date_from", "in", done_payslips.mapped("date_from")),
            ("date_to", "in", done_payslips.mapped("date_to")),
            ("state", "in", ["validated", "paid"]),
        ]
        all_existing_payslips = self.env["hr.payslip"].search(search_domain)

        # Group existing slips for easy lookup
        existing_payslip_map = defaultdict(lambda: self.env["hr.payslip"])
        for slip in all_existing_payslips:
            key = (slip.employee_id.id, slip.struct_id.id, slip.date_from, slip.date_to)
            existing_payslip_map[key] |= slip

        return existing_payslip_map

    def _prepare_worked_days_line_commands(self) -> list:
        if self.struct_id.use_worked_day_lines:
            return [Command.create(vals) for vals in self._prepare_worked_day_vals()]
        return []

    def _get_salary_line_total(self, code):
        _logger.warning(
            "The method _get_salary_line_total is deprecated in favor of _get_line_values"
        )
        lines = self.line_ids.filtered(lambda line: line.code == code)
        return sum(line.total for line in lines)

    def _get_salary_line_quantity(self, code):
        _logger.warning(
            "The method _get_salary_line_quantity is deprecated in favor of _get_line_values"
        )
        lines = self.line_ids.filtered(lambda line: line.code == code)
        return sum(line.quantity for line in lines)

    def _get_line_values(self, code_list, vals_list=None, compute_sum=False):
        if vals_list is None:
            vals_list = ["total"]
        valid_values = {"quantity", "amount", "total", "ytd"}
        if set(vals_list) - valid_values:
            raise UserError(
                self.env._(
                    "The following values are not valid:\n%s",
                    "\n".join(list(set(vals_list) - valid_values)),
                )
            )
        result = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(vals_list, 0.0)))
        if not self or not code_list:
            return result
        payslip_line_read_group = self.env["hr.payslip.line"]._read_group(
            [
                ("slip_id", "in", self.ids),
                ("code", "in", code_list),
            ],
            ["slip_id", "code"],
            [f"{f_name}:sum" for f_name in vals_list],
        )
        # result = {
        #     'IP': {
        #         'sum': {'quantity': 2, 'total': 300},
        #         1: {'quantity': 1, 'total': 100},
        #         2: {'quantity': 1, 'total': 200},
        #     },
        #     'IP.DED': {
        #         'sum': {'quantity': 2, 'total': -5},
        #         1: {'quantity': 1, 'total': -2},
        #         2: {'quantity': 1, 'total': -3},
        #     },
        # }
        for payslip, code, *sum_vals_list in payslip_line_read_group:
            for vals, vals_value in zip(vals_list, sum_vals_list, strict=False):
                if compute_sum:
                    result[code]["sum"][vals] += vals_value or 0.0
                result[code][payslip.id][vals] += vals_value or 0.0
        return result

    def _get_worked_days_line_values_orm(self, code, field_name=None):
        """
        Use this method only if self is not yet created.
        Otherwise, use '_get_worked_days_line_values' that leads to better performances.
        """
        if field_name is None:
            field_name = "amount"
        valid_values = {"number_of_hours", "number_of_days", "amount", "ytd"}
        if field_name not in valid_values:
            raise UserError(self.env._("The field is not valid:%s", field_name))

        wds = self.worked_days_line_ids.filtered(lambda wd: wd.code == code)
        return sum(wd[field_name] for wd in wds)

    def _get_worked_days_line_values(
        self, code_list, vals_list=None, compute_sum=False, exclude_codes=False
    ):
        if vals_list is None:
            vals_list = ["amount"]
        valid_values = {"number_of_hours", "number_of_days", "amount", "ytd"}
        if set(vals_list) - valid_values:
            raise UserError(
                self.env._(
                    "The following values are not valid:\n%s",
                    "\n".join(list(set(vals_list) - valid_values)),
                )
            )
        result = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(vals_list, 0.0)))
        if not self or (not code_list and not exclude_codes):
            return result

        self.env.flush_all()
        selected_fields = ",".join("SUM(%s) AS %s" % (vals, vals) for vals in vals_list)
        operation = "= ANY(%s)" if not exclude_codes else "!= ALL(%s)"
        self.env.cr.execute(
            """
            SELECT
                p.id,
                wet.code,
                %s
            FROM hr_payslip_worked_days wd
            JOIN hr_work_entry_type wet ON wet.id = wd.work_entry_type_id
            JOIN hr_payslip p ON p.id = ANY(%s)
            AND wd.payslip_id = p.id
            AND wet.code %s
            GROUP BY p.id, wet.code
        """
            % (selected_fields, "%s", operation),
            (list(self.ids), list(code_list)),
        )
        # self = hr.payslip(1, 2)
        # request_rows = [
        #     {'id': 1, 'code': 'WORK100', 'amount': 100, 'number_of_days': 1},
        #     {'id': 1, 'code': 'LEAVE100', 'amount': 200, 'number_of_days': 1},
        #     {'id': 2, 'code': 'WORK100', 'amount': -2, 'number_of_days': 1},
        #     {'id': 2, 'code': 'LEAVE100', 'amount': -3, 'number_of_days': 1}
        # ]
        request_rows = self.env.cr.dictfetchall()
        # result = {
        #     'WORK100': {
        #         'sum': {'number_of_days': 2, 'amount': 98},
        #         1: {'number_of_days': 1, 'amount': 100},
        #         2: {'number_of_days': 1, 'amount': -2},
        #     },
        #     'LEAVE100': {
        #         'sum': {'number_of_days': 2, 'amount': 197},
        #         1: {'number_of_days': 1, 'amount': 200},
        #         2: {'number_of_days': 1, 'amount': -3},
        #     },
        # }
        for row in request_rows:
            code = row["code"]
            payslip_id = row["id"]
            for vals in vals_list:
                if compute_sum:
                    result[code]["sum"][vals] += row[vals] or 0.0
                result[code][payslip_id][vals] += row[vals] or 0.0
        return result

    # TODO: convert to a single SQL request + handle children
    def _get_category_data(self, category_code):
        category_data = {"quantity": 0.0, "total": 0.0}
        for line in self.line_ids:
            if line.category_id.code == category_code:
                category_data["quantity"] += line.quantity
                category_data["total"] += line.total
        return category_data

    def _get_input_line_amount(self, code):
        lines = self.input_line_ids.filtered(lambda line: line.code == code)
        return sum(line.amount for line in lines)

    def _check_printable(self) -> None:
        if self.filtered("error_count"):
            raise ValidationError(self._get_error_message())

    def _get_report_base_filename(self):
        self.check_singleton()
        structure_report = self.struct_id.report_id
        default_report = self.env.ref("hr_payroll.action_report_payslip")
        if structure_report != default_report and structure_report.print_report_name:
            return safe_eval(structure_report.print_report_name, {"object": self})
        return "Payslip - %s" % self.name

    def action_export_payslip(self):
        pass

    def _get_contract_wage(self):
        self.check_singleton()
        return self.version_id._get_contract_wage()

    def _get_paid_amount(self):
        self.check_singleton()
        if self.env.context.get("no_paid_amount"):
            return 0.0
        if (
            self.env.context.get("salary_simulation")
            or not self.struct_id.use_worked_day_lines
        ):
            return self._get_contract_wage()
        total_amount = 0
        for line in self.worked_days_line_ids:
            total_amount += line.amount
        return total_amount

    def _get_unpaid_amount(self):
        self.check_singleton()
        return self._get_contract_wage() - self._get_paid_amount()

    def _is_outside_contract_dates(self) -> bool:
        self.check_singleton()
        payslip = self
        contract = self.version_id
        return bool(
            contract.date_start > payslip.date_to
            or (contract.date_end and contract.date_end < payslip.date_from)
        )

    def _get_data_files_to_update(self):
        # Note: Use lists as modules/files order should be maintained
        return []

    def _update_payroll_data(self) -> None:
        data_to_update = self._get_data_files_to_update()
        _logger.info("Update payroll static data")
        idref = {}
        for module_name, files_to_update in data_to_update:
            for file_to_update in files_to_update:
                convert_file(self.env, module_name, file_to_update, idref)

    def action_edit_payslip_lines(self) -> dict:
        self.check_singleton()
        if not self.env.user.has_group("hr_payroll.group_hr_payroll_user"):
            raise UserError(
                self.env._("This action is restricted to payroll officers only.")
            )
        if self.state != "draft":
            raise UserError(
                self.env._("This action is only allowed on draft payslips.")
            )
        wizard = self.env["wizard.hr.payslip.update.line"].create(
            {
                "payslip_id": self.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": line.sequence,
                            "code": line.code,
                            "name": line.name,
                            "salary_rule_id": line.salary_rule_id.id,
                            "version_id": line.version_id.id,
                            "employee_id": line.employee_id.id,
                            "amount": line.amount,
                            "quantity": line.quantity,
                            "rate": line.rate,
                            "ytd": line.ytd,
                            "slip_id": self.id,
                        }
                    )
                    for line in self.line_ids
                ],
                "worked_days_line_ids": [
                    Command.create(
                        {
                            "name": line.name,
                            "sequence": line.sequence,
                            "code": line.code,
                            "work_entry_type_id": line.work_entry_type_id.id,
                            "number_of_days": line.number_of_days,
                            "number_of_hours": line.number_of_hours,
                            "amount": line.amount,
                            "ytd": line.ytd,
                            "slip_id": self.id,
                        }
                    )
                    for line in self.worked_days_line_ids
                ],
            }
        )

        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Edit Payslip Lines"),
            "res_model": "wizard.hr.payslip.update.line",
            "view_mode": "form",
            "target": "new",
            "binding_model_id": self.env["ir.model.data"]._xmlid_to_res_id(
                "hr_payroll.model_hr_payslip"
            ),
            "binding_view_types": "form",
            "res_id": wizard.id,
        }

    @api.model
    def _cron_generate_pdf(self, batch_size=False):
        payslips = self.search(
            [
                ("state", "in", ["validated", "paid"]),
                ("queued_for_pdf", "=", True),
            ]
        )
        if payslips:
            BATCH_SIZE = batch_size or 30
            payslips_batch = payslips[:BATCH_SIZE]
            payslips_batch._create_pdf_attachments()
            payslips_batch.write({"queued_for_pdf": False})
            # if necessary, retrigger the cron to generate more pdfs
            if len(payslips) > BATCH_SIZE:
                self.env["ir.cron"]._trigger_ref(
                    "hr_payroll.ir_cron_generate_payslip_pdfs"
                )
                return True

        lines = self.env["hr.payroll.employee.declaration"].search(
            [("pdf_to_generate", "=", True)]
        )
        if lines:
            BATCH_SIZE = batch_size or 30
            lines_batch = lines[:BATCH_SIZE]
            lines_batch._update_pdf()
            lines_batch.write({"pdf_to_generate": False})
            # if necessary, retrigger the cron to generate more pdfs
            if len(lines) > BATCH_SIZE:
                self.env["ir.cron"]._trigger_ref(
                    "hr_payroll.ir_cron_generate_payslip_pdfs"
                )
                return True
        return False

    @api.model
    def __get_aggregator_hr_payslip_input_model(self):
        """this method return an aggregator version of hr.payslip.input Model.
        this method is also meant to be overriden in case other modules adds new fields
        to hr.payslip.input model. In case it can be extended as such:
        ```py
        def __get_aggregator_hr_payslip_input_model(self):
            class ProxyHrPayslipInput(
                super().__get_aggregator_hr_payslip_input_model()
            ): ...  # your modifications


        return ProxyHrPayslipInput
        ```

        Note: -this method use the normal python class inheritance instead of odoo's
              -the aggregation assumes that the code are the same for all the inputs
        Warning: Do not reproduce elsewhere it's quite a specific case here
        :return: Aggregator version of hr.payslip.input model
        """

        class ProxyHrPayslipInput(self.env["hr.payslip.input"].__class__):
            _name = self.env["hr.payslip.input"]._name
            _register = False  # invisible to the ORM

            # All the fields that are not overridden are considered as equal to
            # self[0]['field']

            def __getitem__(self, key_or_slice):
                if not self or len(self) == 1:
                    return super().__getitem__(key_or_slice)
                if key_or_slice == "name":
                    return self.name
                if key_or_slice == "sequence":
                    return self.sequence
                if key_or_slice == "amount":
                    return self.amount
                return super().__getitem__(key_or_slice)

            @property
            def name(self):
                if not self or len(self) == 1:
                    return super().name
                if len(set(self.mapped("name"))) == 1:
                    return super(ProxyHrPayslipInput, self[0]).name
                return ", ".join(self.mapped("name"))

            @property
            def sequence(self):
                if not self or len(self) == 1:
                    return super().sequence
                return min(self.mapped("sequence"))

            @property
            def amount(self):
                if not self or len(self) == 1:
                    return super().amount
                return sum(payslip_input.amount for payslip_input in self)

        return ProxyHrPayslipInput

    # Payroll Dashboard
    @api.model
    def _dashboard_default_action(
        self, name, res_model, res_ids, additional_context=None
    ) -> dict:
        if additional_context is None:
            additional_context = {}
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": res_model,
            "context": {**self.env.context, **additional_context},
            "domain": [("id", "in", res_ids)],
            "views": [[False, "list"], [False, "kanban"], [False, "form"]],
            "view_mode": "list,kanban,form",
        }

    @api.model
    def _get_domain_dashboard_warnings(self):
        return []

    @api.model
    def get_dashboard_warnings(self):
        # Retrieve the different warnings to display on the actions section (box on the left)
        result = []

        # Retrieves last batches (this month, or last month)
        batch_limit_date = fields.Date.today() - relativedelta(months=1, day=1)
        batch_group_read = (
            self.env["hr.payslip.run"]
            .with_context(lang="en_US")
            ._read_group(
                [
                    (
                        "date_start",
                        ">=",
                        fields.Date.today() - relativedelta(months=1, day=1),
                    )
                ],
                groupby=["date_start:month"],
                order="date_start:month desc",
            )
        )
        # Keep only the last month
        batch_group_read = batch_group_read[:1]
        if batch_group_read:
            min_date = batch_group_read[-1][0] or batch_limit_date
            last_batches = self.env["hr.payslip.run"].search(
                [("date_start", ">=", min_date)]
            )
        else:
            last_batches = self.env["hr.payslip.run"]

        for warning in self.env["hr.payroll.dashboard.warning"].search(
            self._get_domain_dashboard_warnings()
        ):
            context = {
                "date": safe_eval_datetime.date,
                "datetime": safe_eval_datetime.datetime,
                "relativedelta": safe_eval_dateutil.relativedelta.relativedelta,
                "warning_count": 0,
                "warning_records": self.env["base"],
                "warning_action": False,
                "additional_context": {},
                "self": self.env["hr.payslip"],
                "last_batches": last_batches,
                "defaultdict": defaultdict,
            }
            try:
                safe_eval(warning.evaluation_code, context, mode="exec")
            except Exception as e:
                raise UserError(
                    self.env._(
                        "Wrong warning computation code defined for:\n- Warning: %(warning)s\n- Error: %(error)s",
                        warning=warning.name,
                        error=e,
                    )
                ) from e
            if context["warning_count"]:
                result.append(
                    {
                        "string": warning.name,
                        "color": warning.color,
                        "count": context["warning_count"],
                        "action": context["warning_action"]
                        or self._dashboard_default_action(
                            warning.name,
                            context["warning_records"]._name,
                            context["warning_records"].ids,
                            additional_context=context["additional_context"],
                        ),
                    }
                )
        return result

    def _get_employee_stats_actions(self):
        result = []
        today = fields.Date.today()
        HrVersion = self.env["hr.version"]
        new_versions = HrVersion.search(
            [("contract_date_start", ">=", today + relativedelta(months=-3, day=1))]
        )
        past_versions_grouped_by_employee_id = {
            employee.id
            for [employee] in HrVersion._read_group(
                [
                    ("employee_id", "in", new_versions.employee_id.ids),
                    # ('date_end', '<', today),  # TODO: filter after
                    ("id", "not in", new_versions.ids),
                ],
                groupby=["employee_id"],
            )
        }

        new_versions_without_past_version = HrVersion
        for new_version in new_versions:
            if new_version.employee_id.id not in past_versions_grouped_by_employee_id:
                new_versions_without_past_version |= new_version

        if new_versions_without_past_version:
            new_versions_str = self.env._("New Employees")
            employees_from_new_versions = new_versions_without_past_version.mapped(
                "employee_id"
            )
            new_employees = {
                "string": new_versions_str,
                "count": len(employees_from_new_versions),
                "action": self._dashboard_default_action(
                    new_versions_str, "hr.employee", employees_from_new_versions.ids
                ),
            }
            new_employees["action"]["views"][0] = [
                self.env.ref(
                    "hr_payroll.payroll_hr_employee_view_tree_employee_trends"
                ).id,
                "list",
            ]
            result.append(new_employees)

        gone_employees = (
            self.env["hr.employee"]
            .with_context(active_test=False)
            .search(
                [
                    ("departure_date", ">=", today + relativedelta(months=-1, day=1)),
                    ("company_id", "in", self.env.companies.ids),
                ]
            )
        )
        if gone_employees:
            gone_employees_str = self.env._("Last Departures")
            result.append(
                {
                    "string": gone_employees_str,
                    "count": len(gone_employees),
                    "action": self.with_context(
                        active_test=False
                    )._dashboard_default_action(
                        gone_employees_str, "hr.employee", gone_employees.ids
                    ),
                }
            )
        return result

    @api.model
    def _get_dashboard_stat_employer_cost_codes(self):
        costs = self.env["hr.salary.rule"].search_read(
            [("appears_on_employee_cost_dashboard", "=", True)], fields=["code", "name"]
        )
        cost_codes = {}

        for cost in costs:
            cost_codes[cost["code"]] = cost["name"]
        return cost_codes

    @api.model
    def _get_dashboard_stats_employer_cost(self):
        today = fields.Date.context_today(self)
        date_formats = {
            "monthly": "MMMM y",
            "yearly": "y",
        }
        employer_cost = {
            "type": "stacked_bar",
            "title": self.env._("Employer Cost"),
            "label": self.env._("Employer Cost"),
            "id": "employer_cost",
            "is_sample": False,
            "actions": [],
            "data": {
                "monthly": defaultdict(lambda: [{}, {}, {}]),
                "yearly": defaultdict(lambda: [{}, {}, {}]),
            },
        }
        # Retrieve employer costs over the last 3 months.
        # The bounds have to come from the same clock as `today` below: the
        # bucket index is derived from `today`, and a domain built on a
        # different calendar date can admit a payslip whose index falls
        # outside the three slots allocated above.
        monthly_payslips = self.env["hr.payslip"].search(
            [
                ("state", "!=", "cancel"),
                ("date_from", ">=", today + relativedelta(months=-2, day=1)),
                ("date_to", "<=", today + relativedelta(day=31)),
            ]
        )
        cost_codes = self._get_dashboard_stat_employer_cost_codes()
        line_values = monthly_payslips._get_line_values(cost_codes.keys())
        for slip in monthly_payslips:
            for code, code_desc in cost_codes.items():
                start = slip.date_from
                end = today
                idx = -((end.year - start.year) * 12 + (end.month - start.month) - 2)
                if not 0 <= idx <= 2:
                    continue
                amount = employer_cost["data"]["monthly"][code_desc][idx].get(
                    "value", 0.0
                )
                amount += line_values[code][slip.id]["total"]
                employer_cost["data"]["monthly"][code_desc][idx]["value"] = amount
                if not employer_cost["data"]["monthly"][code_desc][idx].get("label"):
                    period_str = format_date(
                        self.env, start, date_format=date_formats["monthly"]
                    )
                    employer_cost["data"]["monthly"][code_desc][idx]["label"] = (
                        period_str
                    )
        # Retrieve employer costs over the last 3 years
        yearly_payslips = self.env["hr.payslip"].search(
            [
                ("state", "!=", "cancel"),
                ("date_from", ">=", today + relativedelta(years=-2, day=1)),
                ("date_to", "<=", today + relativedelta(month=12, day=31)),
            ]
        )
        # Sample-ness is a property of the whole widget, and the fill below
        # uses it for BOTH series. Deciding it from the monthly search alone
        # padded the yearly series with generated numbers while it held real
        # aggregates, in the same bars, indistinguishable.
        employer_cost["is_sample"] = not monthly_payslips and not yearly_payslips
        line_values = yearly_payslips._get_line_values(cost_codes.keys())
        for slip in yearly_payslips:
            for code, code_desc in cost_codes.items():
                start = slip.date_from
                end = today
                idx = -(end.year - start.year - 2)
                if not 0 <= idx <= 2:
                    continue
                amount = employer_cost["data"]["yearly"][code_desc][idx].get(
                    "value", 0.0
                )
                amount += line_values[code][slip.id]["total"]
                employer_cost["data"]["yearly"][code_desc][idx]["value"] = amount
                if not employer_cost["data"]["yearly"][code_desc][idx].get("label"):
                    period_str = format_date(
                        self.env, start, date_format=date_formats["yearly"]
                    )
                    employer_cost["data"]["yearly"][code_desc][idx]["label"] = (
                        period_str
                    )
        # Nullify empty sections
        for i in range(3):
            for code_desc in cost_codes.values():
                if not employer_cost["data"]["monthly"][code_desc][i]:
                    value = (
                        0
                        if not employer_cost["is_sample"]
                        else random.randint(1000, 1500)
                    )
                    employer_cost["data"]["monthly"][code_desc][i]["value"] = value
                    if not employer_cost["data"]["monthly"][code_desc][i].get("label"):
                        label = format_date(
                            self.env,
                            today + relativedelta(months=i - 2),
                            date_format=date_formats["monthly"],
                        )
                        employer_cost["data"]["monthly"][code_desc][i]["label"] = label
                if not employer_cost["data"]["yearly"][code_desc][i]:
                    value = (
                        0
                        if not employer_cost["is_sample"]
                        else random.randint(10000, 15000)
                    )
                    employer_cost["data"]["yearly"][code_desc][i]["value"] = value
                    if not employer_cost["data"]["yearly"][code_desc][i].get("label"):
                        label = format_date(
                            self.env,
                            today + relativedelta(years=i - 2),
                            date_format=date_formats["yearly"],
                        )
                        employer_cost["data"]["yearly"][code_desc][i]["label"] = label
        # Format/Round at the end as the method cost is heavy
        for data_by_code in employer_cost["data"].values():
            for data_by_type in data_by_code.values():
                for data_dict in data_by_type:
                    value = round(data_dict["value"], 2)
                    data_dict["value"] = value
                    data_dict["formatted_value"] = format_amount(
                        self.env, value, self.env.company.currency_id
                    )
        return employer_cost

    @api.model
    def _get_dashboard_stat_employee_trends(self):
        today = fields.Date.context_today(self)
        employees_trends = {
            "type": "bar",
            "title": self.env._("Employee Count"),
            "label": self.env._("Employee Count"),
            "id": "employees",
            "is_sample": False,
            "actions": self._get_employee_stats_actions(),
            "data": {
                "monthly": [{}, {}, {}],
                "yearly": [{}, {}, {}],
            },
        }
        # These are all the periods for which we need data
        periods = [
            # Last month
            (
                today - relativedelta(months=1, day=1),
                today - relativedelta(day=1, days=1),
                "monthly,past",
            ),
            # This month
            (
                today - relativedelta(day=1),
                today + relativedelta(months=1, day=1, days=-1),
                "monthly,present",
            ),
            # Next month
            (
                today + relativedelta(months=1, day=1),
                today + relativedelta(months=2, day=1, days=-1),
                "monthly,future",
            ),
            # Last year
            (
                today - relativedelta(years=1, month=1, day=1),
                today - relativedelta(years=1, month=12, day=31),
                "yearly,past",
            ),
            # This year
            (
                today - relativedelta(month=1, day=1),
                today + relativedelta(month=12, day=31),
                "yearly,present",
            ),
            # Next year
            (
                today + relativedelta(years=1, month=1, day=1),
                today + relativedelta(years=1, month=12, day=31),
                "yearly,future",
            ),
        ]
        periods_str = ", ".join(
            "(DATE '%(date_from)s', DATE '%(date_to)s', '%(date_type)s')"
            % {
                "date_from": p[0].strftime("%Y-%m-%d"),
                "date_to": p[1].strftime("%Y-%m-%d"),
                "date_type": p[2],
            }
            for p in periods
        )
        # Fetch our statistics
        # Contracts are joined by our period using the usual state/date conditions
        # and aggregates are used to collect data directly from our database
        # avoiding unnecessary orm overhead
        # TODO: should filter with date_start, date_end via orm or is it already good ? will this stay at all ?
        self.env.cr.execute(
            """
        WITH periods AS (
            SELECT *
              FROM (VALUES %s
              ) x(start, _end, _type)
        )
        -- fetch all contracts matching periods from `periods`
        -- `active` has to be spelled out: raw SQL gets no `active_test`, and
        -- without it this counts archived employees while the employee count
        -- rendered beside it, which goes through the ORM, does not.
        SELECT p.start, p._end, p._type,
               COUNT (DISTINCT v.employee_id) as employee_count
          FROM periods p
          JOIN hr_version v
            ON (v.contract_date_end >= p.start OR v.contract_date_end IS NULL)
           AND v.contract_date_start <= p._end
           AND v.active
          JOIN hr_employee e
            ON e.id = v.employee_id
           AND e.company_id = ANY(%%s)
           AND e.active
      GROUP BY p.start, p._end, p._type
        """
            % (periods_str),
            (list(self.env.companies.ids),),
        )
        period_indexes = {
            "past": 0,
            "present": 1,
            "future": 2,
        }
        date_formats = {
            "monthly": "MMMM y",
            "yearly": "y",
        }
        # Collect data in our result
        for res in self.env.cr.dictfetchall():
            period_type, _type = res["_type"].split(",")  # Ex: yearly,past
            start = res["start"]
            period_idx = period_indexes[_type]
            period_str = format_date(
                self.env, start, date_format=date_formats[period_type]
            )
            # The data is formatted for the chart module
            employees_trends["data"][period_type][period_idx] = {
                "label": period_str,
                "value": res["employee_count"],
                "name": period_str,
            }

        # Generates a point as sample data
        def prepare_sample_data(period_str, period_type, chart_type):
            if chart_type == "line":
                return {
                    "x": period_str,
                    "name": period_str,
                    "y": random.randint(1000, 1500),
                }
            return {
                "value": random.randint(1000, 1500),
                "label": period_str,
                "type": period_type,
            }

        # Generates empty data in case a column is missing
        def prepare_null_data(period_str, period_type, chart_type):
            if chart_type == "line":
                return {"x": period_str, "name": period_str, "y": 0}
            return {"value": 0, "label": period_str, "type": period_type}

        make_data = prepare_null_data
        period_types = ["monthly", "yearly"]

        if all(not data for data in employees_trends["data"]["monthly"]):
            employees_trends["is_sample"] = True
            make_data = prepare_sample_data

        # Go through all the data and create null or sample values where necessary
        for start, _dummy, p_types in periods:
            _type, _time = p_types.split(",")
            i = period_indexes[_time]
            for period in period_types:
                period_str = format_date(
                    self.env, start, date_format=date_formats[period]
                )
                if not employees_trends["data"][_type][i]:
                    employees_trends["data"][_type][i] = make_data(
                        period_str, _type, employees_trends["type"]
                    )
        return employees_trends

    @api.model
    def _get_dashboard_stats(self) -> list:
        # Retrieve the different stats to display on the stats sections
        # This function fills in employees and employer costs statistics
        # Default data, replaced by sample data if empty after query
        employees_trends = self._get_dashboard_stat_employee_trends()
        employer_cost = self._get_dashboard_stats_employer_cost()

        return [employer_cost, employees_trends]

    @api.model
    def _get_dashboard_employee_count(self):
        admin_employee = self.env.ref("hr.employee_admin", raise_if_not_found=False)
        domain = [("company_id", "in", self.env.companies.ids)]
        if admin_employee:
            domain += [("id", "!=", admin_employee.id)]
        return self.env["hr.employee"].search_count(domain, limit=1)

    @api.model
    def _get_dashboard_default_sections(self) -> list:
        return ["batches", "stats", "employee_count"]

    @api.model
    def _get_fields_dashboard_batch(self) -> list:
        return ["id", "date_start", "name", "state", "payslip_count"]

    @api.model
    def get_payroll_dashboard_data(self, sections=None):
        # Entry point for getting the dashboard data
        # `sections` defines which part of the data we want to include/exclude
        if sections is None:
            sections = self._get_dashboard_default_sections()
        result = {}
        if "batches" in sections:
            # Batches are loaded for the last 3 months with batches, for example if there are no batches for
            # the summer and september is loaded, we want to get september, june, may.
            # Limit to max - 1 year
            batch_limit_date = fields.Date.today() - relativedelta(years=1, day=1)
            batch_group_read = (
                self.env["hr.payslip.run"]
                .with_context(lang="en_US")
                ._read_group(
                    [("date_start", ">=", batch_limit_date)],
                    groupby=["date_start:month"],
                    limit=20,
                    order="date_start:month desc",
                )
            )
            # Keep only the last 3 months
            batch_group_read = batch_group_read[:3]
            if batch_group_read:
                min_date = batch_group_read[-1][
                    0
                ] or fields.Date.today() - relativedelta(months=1, day=1)
                batches_read_result = self.env["hr.payslip.run"].search_read(
                    [("date_start", ">=", min_date)],
                    fields=self._get_fields_dashboard_batch(),
                )
            else:
                batches_read_result = []
            translated_states = dict(
                self.env["hr.payslip.run"]
                ._fields["state"]
                ._description_selection(self.env)
            )
            for batch_read in batches_read_result:
                batch_read.update(
                    {
                        "name": f"{batch_read['name']} ({format_date(self.env, batch_read['date_start'], date_format='MM/y')})",
                        "payslip_count": self.env._(
                            "(%s Payslips)", batch_read["payslip_count"]
                        ),
                        "state_code": batch_read["state"],
                        "state": translated_states.get(
                            batch_read["state"], self.env._("Unknown State")
                        ),
                    }
                )
            result["batches"] = batches_read_result
        if "stats" in sections:
            result["stats"] = self._get_dashboard_stats()
        if "employee_count" in sections:
            result["employee_count"] = self._get_dashboard_employee_count()
        return result

    def action_configure_payslip_inputs(self):
        self.check_singleton()
        action = self.struct_id.action_get_structure_inputs()
        action["domain"].append(("input_usage_payslip", "=", True))
        return action

    def compute_salary_allocations(self, total_amount=None):
        self.check_singleton()
        if total_amount is None:
            remaining = self.currency_id.round(self.net_wage)
        else:
            remaining = self.currency_id.round(total_amount)

        res = {}
        if remaining == 0 or not self.employee_id.salary_bank_account_ids:
            return res
        if not self.employee_id.has_multiple_bank_accounts:
            res[str(self.employee_id.primary_bank_account_id.id)] = remaining
            return res

        fixed_bank_account_ids = self.employee_id._get_accounts_with_fixed_allocations()
        for ba in fixed_bank_account_ids:
            amount, _ = self.employee_id.get_bank_account_salary_allocation(ba.id)
            # Money, so ask the currency rather than the float operators:
            # 3.3 - 1.1 is 2.1999999999999997, which made a following
            # allocation of 2.2 look larger than what is left and rejected a
            # split that adds up exactly. Rounding the remainder each time
            # keeps that error from accumulating across allocations too.
            if self.currency_id.is_zero(amount):
                # Allocating nothing is not an error. The percentage loop
                # below already records a zero share and moves on; this
                # branch used to answer it with "surpasses the net salary",
                # which is not what a zero does.
                res[str(ba.id)] = 0
                continue
            if amount < 0:
                raise ValidationError(
                    self.env._("A salary allocation cannot be negative.")
                )
            if self.currency_id.compare_amounts(amount, remaining) > 0:
                raise ValidationError(
                    self.env._("Allocated amounts surpass the net salary.")
                )
            amount = self.currency_id.round(amount)
            res[str(ba.id)] = amount
            remaining = self.currency_id.round(remaining - amount)

        percentage_bank_account_ids = (
            self.employee_id.salary_bank_account_ids - fixed_bank_account_ids
        )
        if not percentage_bank_account_ids and remaining > 0:
            raise ValidationError(
                self.env._("Allocated amounts are less than the net salary.")
            )

        total_percentage_account_amounts = 0
        for i, ba in enumerate(percentage_bank_account_ids):
            percentage, _ = self.employee_id.get_bank_account_salary_allocation(ba.id)
            if percentage > 0:
                if i == len(percentage_bank_account_ids) - 1:
                    amount = self.currency_id.round(
                        remaining - total_percentage_account_amounts
                    )
                else:
                    amount = self.currency_id.round((percentage / 100.0) * remaining)
                    total_percentage_account_amounts += amount
                if amount > 0:
                    res[str(ba.id)] = amount
            else:
                res[str(ba.id)] = 0
        return res

    def safe_compute_salary_allocations(self, total_amount=None):
        try:
            return self.compute_salary_allocations(total_amount)
        except ValidationError as e:
            return {"__error__": str(e)}
