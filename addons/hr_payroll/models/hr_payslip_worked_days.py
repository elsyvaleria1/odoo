from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import float_round


class HrPayslipWorkedDays(models.Model):
    _name = "hr.payslip.worked_days"
    _description = "Payslip Worked Days"
    _order = "payslip_id, sequence"

    name = fields.Char(
        string="Description",
        compute="_compute_name",
        store=True,
        readonly=False,
    )
    payslip_id = fields.Many2one(
        comodel_name="hr.payslip",
        string="Pay Slip",
        index=True,
        required=True,
        ondelete="cascade",
    )
    date_from = fields.Date(
        related="payslip_id.date_from",
        string="From",
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        related="payslip_id.employee_id",
        string="Employee",
    )
    sequence = fields.Integer(
        default=10,
        index=True,
        required=True,
    )
    code = fields.Char(
        related="work_entry_type_id.code",
        string="Code",
    )
    work_entry_type_id = fields.Many2one(
        comodel_name="hr.work.entry.type",
        string="Type",
        required=True,
        help="The code that can be used in the salary rules",
    )
    number_of_days = fields.Float(string="Number of Days")
    number_of_hours = fields.Float(string="Number of Hours")
    is_paid = fields.Boolean(
        compute="_compute_is_paid",
        store=True,
    )
    amount = fields.Monetary(
        compute="_compute_amount",
        store=True,
        copy=True,
    )
    version_id = fields.Many2one(
        related="payslip_id.version_id",
        string="Contract",
        help="The contract this worked days should be applied to",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="payslip_id.currency_id",
    )
    ytd = fields.Monetary(string="YTD")

    @api.depends(
        "work_entry_type_id",
        "payslip_id",
        "payslip_id.struct_id",
        "payslip_id.employee_id",
        "payslip_id.version_id",
        "payslip_id.struct_id",
        "payslip_id.date_from",
        "payslip_id.date_to",
    )
    def _compute_is_paid(self) -> None:
        detached = self.filtered(lambda wd: not wd.payslip_id)
        for worked_days in detached:
            worked_days.is_paid = False
        payslip_lines = self - detached
        unpaid = {
            struct.id: struct.unpaid_work_entry_type_ids.ids
            for struct in payslip_lines.mapped("payslip_id.struct_id")
        }
        for worked_days in payslip_lines:
            worked_days.is_paid = (
                (
                    worked_days.work_entry_type_id.id
                    not in unpaid[worked_days.payslip_id.struct_id.id]
                )
                if worked_days.payslip_id.struct_id.id in unpaid
                else False
            )

    @api.depends(
        "is_paid",
        "number_of_hours",
        "payslip_id",
        "version_id.wage",
        "version_id.hourly_wage",
        "payslip_id.sum_worked_hours",
        "work_entry_type_id.amount_rate",
        "work_entry_type_id.is_extra_hours",
    )
    def _compute_amount(self):
        for worked_days in self:
            if worked_days.payslip_id.edited or worked_days.payslip_id.state != "draft":
                continue
            if not worked_days.version_id or worked_days.code == "OUT":
                worked_days.amount = 0
                continue
            version = worked_days.payslip_id.version_id
            amount_rate = worked_days.work_entry_type_id.amount_rate
            if worked_days.payslip_id.wage_type == "hourly":
                hourly_rate = version.hourly_wage
            else:
                attendance_hours = (
                    sum(
                        wd.number_of_hours
                        for wd in worked_days.payslip_id.worked_days_line_ids
                        if not wd.work_entry_type_id.is_extra_hours
                    )
                    or 1
                )
                hourly_rate = version.contract_wage / attendance_hours
            worked_days.amount = (
                hourly_rate * worked_days.number_of_hours * amount_rate
                if worked_days.is_paid
                else 0
            )

    def _is_half_day(self) -> bool:
        self.check_singleton()
        work_hours = self.payslip_id._get_worked_day_lines_hours_per_day()
        return (
            abs(self.number_of_days) < 1
            or float_round(self.number_of_hours / self.number_of_days, 2) < work_hours
        )

    @api.depends(
        "work_entry_type_id", "number_of_days", "number_of_hours", "payslip_id"
    )
    def _compute_name(self):
        detached = self.filtered(lambda wd: not wd.payslip_id)
        for worked_days in detached:
            worked_days.name = worked_days.work_entry_type_id.name or ""
        payslip_lines = self - detached
        if not payslip_lines:
            return

        to_check_public_holiday = dict(
            self.env["resource.schedule.exception"]._read_group(
                self.env["resource.schedule.exception"]._get_domain_public_holidays(
                    min(payslip_lines.payslip_id.mapped("date_from")),
                    max(payslip_lines.payslip_id.mapped("date_to")),
                )
                & Domain(
                    "work_entry_type_id",
                    "in",
                    payslip_lines.mapped("work_entry_type_id").ids,
                ),
                ["work_entry_type_id"],
                ["id:recordset"],
            )
        )
        work_entries = {
            (employee, date): we
            for employee, date, we in self.env["hr.work.entry"]._read_group(
                domain=[
                    ("date", "<=", max(payslip_lines.payslip_id.mapped("date_to"))),
                    ("date", ">=", min(payslip_lines.payslip_id.mapped("date_from"))),
                    ("employee_id", "in", payslip_lines.payslip_id.employee_id.ids),
                ],
                groupby=["employee_id", "date:day"],
                aggregates=["id:recordset"],
            )
        }

        for worked_days in payslip_lines:
            public_holidays = to_check_public_holiday.get(
                worked_days.work_entry_type_id, ""
            )
            holidays = public_holidays and worked_days._get_applicable_public_holidays(
                public_holidays
            )
            actual_holidays = self.env["resource.schedule.exception"]
            if holidays:
                for holiday in holidays:
                    work_entry_list = work_entries.get(
                        (worked_days.payslip_id.employee_id, holiday.local_date_from),
                        self.env["hr.work.entry"],
                    )
                    if any(
                        we.code == holiday.work_entry_type_id.code
                        for we in work_entry_list
                    ):
                        actual_holidays |= holiday
            if actual_holidays:
                name = ", ".join(actual_holidays.mapped("name"))
            else:
                name = worked_days.work_entry_type_id.name or ""
            half_day = worked_days._is_half_day()
            worked_days.name = name + (self.env._(" (Half-Day)") if half_day else "")

    def _get_applicable_public_holidays(self, public_holidays):
        self.check_singleton()
        payslip = self.payslip_id
        calendar = payslip.version_id.resource_calendar_id
        return public_holidays.filtered(
            lambda p: (
                (p.calendar_id.id == calendar.id or not p.calendar_id.id)
                and p.local_date_from <= payslip.date_to
                and p.local_date_to >= payslip.date_from
                and (not p.company_id or p.company_id == payslip.company_id)
            )
        )
