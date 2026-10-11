import logging
from datetime import date, datetime, time, timedelta

from dateutil import rrule
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import get_lang

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    timesheet_mail_employee_allow = fields.Boolean(
        string="Employee Reminder",
        export_string_translation=False,
        default=True,
    )
    timesheet_mail_employee_delay = fields.Integer(
        string="Employee Reminder Days",
        export_string_translation=False,
        default=1,
    )
    timesheet_mail_employee_interval = fields.Selection(
        selection=[
            ("weeks", "after the end of the week"),
            ("months", "after the end of the month"),
        ],
        string="Employee Frequency",
        export_string_translation=False,
        default="weeks",
        required=True,
    )
    timesheet_mail_employee_nextdate = fields.Datetime(
        string="Next scheduled date for employee reminder",
        export_string_translation=False,
        readonly=True,
    )

    timesheet_mail_allow = fields.Boolean(
        string="Approver Reminder",
        export_string_translation=False,
        default=True,
    )
    timesheet_mail_delay = fields.Integer(
        string="Approver Reminder Days",
        export_string_translation=False,
        default=3,
    )
    timesheet_mail_interval = fields.Selection(
        selection=[
            ("weeks", "after the end of the week"),
            ("months", "after the end of the month"),
        ],
        string="Approver Reminder Frequency",
        export_string_translation=False,
        default="weeks",
        required=True,
    )
    timesheet_mail_nextdate = fields.Datetime(
        string="Next scheduled date for approver reminder",
        export_string_translation=False,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company, values in zip(companies, vals_list, strict=False):
            company.with_context(
                force_nextdates_calculation=True
            )._timesheet_postprocess(values)
        return companies

    def write(self, vals):
        result = super().write(vals)
        self.with_context(force_nextdates_calculation=False)._timesheet_postprocess(
            vals
        )
        return result

    def _timesheet_postprocess(self, values):
        if (
            values.get("timesheet_mail_employee_allow")
            or self.env.context.get("force_nextdates_calculation")
            or any(
                field_name in values
                for field_name in [
                    "timesheet_mail_employee_delay",
                    "timesheet_mail_employee_interval",
                ]
            )
        ):
            self._update_timesheet_mail_employee_nextdate()
        if (
            values.get("timesheet_mail_allow")
            or self.env.context.get("force_nextdates_calculation")
            or any(
                field_name in values
                for field_name in ["timesheet_mail_delay", "timesheet_mail_interval"]
            )
        ):
            self._update_timesheet_mail_nextdate()

    def _get_next_week_date(self, delay):
        now = fields.Datetime.now()
        nextdate = now + relativedelta(weeks=1, days=-now.weekday() + delay - 1)
        if nextdate < now or nextdate.date() == now.date():
            nextdate = now + relativedelta(weeks=2, days=-now.weekday() + delay - 1)
        return nextdate

    def _get_next_month_date(self, delay):
        now = fields.Datetime.now()
        nextdate = now + relativedelta(day=1, months=1, days=delay - 1)
        if nextdate < now or nextdate.date() == now.date():
            nextdate = now + relativedelta(day=1, months=2, days=delay - 1)
        return nextdate

    def _update_timesheet_mail_employee_nextdate(self) -> None:
        for company in self:
            delay = company.timesheet_mail_employee_delay
            if company.timesheet_mail_employee_interval == "weeks":
                nextdate = self._get_next_week_date(delay)
            else:
                nextdate = self._get_next_month_date(delay)
            company.timesheet_mail_employee_nextdate = fields.Datetime.to_string(
                nextdate
            )

    def _update_timesheet_mail_nextdate(self) -> None:
        for company in self:
            delay = company.timesheet_mail_delay
            if company.timesheet_mail_interval == "weeks":
                nextdate = self._get_next_week_date(delay)
            else:
                nextdate = self._get_next_month_date(delay)
            company.timesheet_mail_nextdate = fields.Datetime.to_string(nextdate)

    @api.model
    def _get_domain_timesheet_reminder(self):
        return [
            (
                "date",
                ">=",
                fields.Date.to_string(date.today() - relativedelta(months=3)),
            ),
            ("date", "<=", fields.Date.today()),
            ("project_id", "!=", False),
        ]

    @api.model
    def _cron_timesheet_reminder_employee(self) -> None:
        today_max = fields.Datetime.to_string(datetime.combine(date.today(), time.max))
        companies = self.search(
            [
                ("timesheet_mail_employee_allow", "=", True),
                ("timesheet_mail_employee_nextdate", "<", today_max),
            ]
        )
        timesheet_domain = self._get_domain_timesheet_reminder()
        for company in companies:
            if company.timesheet_mail_employee_nextdate < fields.Datetime.today():
                _logger.warning(
                    'The cron "Timesheet: Employees Email Reminder" should have run on %s',
                    company.timesheet_mail_employee_nextdate,
                )

            users = (
                self.env["account.analytic.line"]
                .search(
                    Domain.AND(
                        [
                            [("company_id", "=", company.id)],
                            timesheet_domain,
                        ]
                    )
                )
                .mapped("user_id")
                .filtered("active")
            )

            if company.timesheet_mail_employee_interval == "months":
                date_start = (
                    date.today()
                    - timedelta(days=company.timesheet_mail_employee_delay + 1)
                ) + relativedelta(day=1)
                date_stop = date_start + relativedelta(months=1, days=-1)
            else:
                week_start = int(get_lang(self.env).week_start)
                date_start = (
                    date.today()
                    - timedelta(days=company.timesheet_mail_employee_delay + 1)
                    + relativedelta(weekday=rrule.weekday(week_start - 1)(-1))
                )
                date_stop = date_start + timedelta(days=6)

            date_start = fields.Date.to_string(date_start)
            date_stop = fields.Date.to_string(date_stop)

            employees = self.env["hr.employee"].search(
                [("company_id", "=", company.id), ("user_id", "in", users.ids)]
            )
            work_hours_struct = employees.get_timesheet_and_working_hours(
                date_start, date_stop
            )

            for employee in employees:
                if (
                    employee.user_id
                    and work_hours_struct[employee.id]["timesheet_hours"]
                    < work_hours_struct[employee.id]["working_hours"]
                ):
                    self._cron_timesheet_send_reminder(
                        employee,
                        "timesheet_grid.mail_template_timesheet_reminder_user",
                        "hr_timesheet.act_hr_timesheet_line",
                        additionnal_values=work_hours_struct[employee.id],
                    )

        companies._update_timesheet_mail_employee_nextdate()

    @api.model
    def _cron_timesheet_reminder(self) -> None:
        today_max = fields.Datetime.to_string(datetime.combine(date.today(), time.max))
        companies = self.search(
            [
                ("timesheet_mail_allow", "=", True),
                ("timesheet_mail_nextdate", "<", today_max),
            ]
        )
        users = self.env["res.users"]
        if companies:
            users = users.search(
                [
                    (
                        "all_group_ids",
                        "in",
                        [self.env.ref("hr_timesheet.group_hr_timesheet_approver").id],
                    )
                ]
            )
        for company in companies:
            if company.timesheet_mail_nextdate < fields.Datetime.today():
                _logger.warning(
                    'The cron "Timesheet: Approver Email Reminder" should have run on %s',
                    company.timesheet_mail_nextdate,
                )
            if company.timesheet_mail_interval == "months":
                date_start = (
                    date.today() - timedelta(days=company.timesheet_mail_delay + 1)
                ) + relativedelta(day=1)
                date_stop = date_start + relativedelta(months=1, days=-1)

                action_xmlid = "timesheet_grid.action_timesheet_previous_month"
            else:
                week_start = int(get_lang(self.env).week_start)
                date_start = (
                    date.today()
                    - timedelta(days=company.timesheet_mail_delay + 1)
                    + relativedelta(weekday=rrule.weekday(week_start - 1)(-1))
                )
                date_stop = date_start + timedelta(days=6)

                action_xmlid = "timesheet_grid.action_timesheet_previous_week"

            date_start = fields.Date.to_string(date_start)
            date_stop = fields.Date.to_string(date_stop)

            values = {
                "date_start": date_start,
                "date_stop": date_stop,
            }
            for user in users:
                validation_domain = (
                    self.env["account.analytic.line"]
                    .with_user(user)
                    ._get_domain_for_validation_timesheets()
                )
                timesheets_to_validate = (
                    self.env["account.analytic.line"]
                    .with_user(user)
                    .search(
                        Domain.AND(
                            [
                                validation_domain,
                                [
                                    ("employee_id.timesheet_manager_id", "=", user.id),
                                    "&",
                                    ("date", ">=", date_start),
                                    ("date", "<=", date_stop),
                                ],
                            ]
                        )
                    )
                )
                if timesheets_to_validate:
                    self._cron_timesheet_send_reminder(
                        self.env["hr.employee"].search(
                            [("company_id", "=", company.id), ("user_id", "=", user.id)]
                        ),
                        "timesheet_grid.mail_template_timesheet_reminder",
                        action_xmlid,
                        additionnal_values=values,
                    )

        companies._update_timesheet_mail_nextdate()

    @api.model
    def _cron_timesheet_send_reminder(
        self, employees, template_xmlid, action_xmlid, additionnal_values=None
    ) -> None:
        action_url = (
            f"{self.get_base_url()}/odoo/action-{action_xmlid}"
            f"?menu_id={self.env.ref('hr_timesheet.timesheet_menu_root').id}"
        )

        template = self.env.ref(template_xmlid)
        template_ctx = {"action_url": action_url}
        if additionnal_values:
            template_ctx.update(additionnal_values)

        for employee in employees.filtered("user_id"):
            template.with_context(**template_ctx).send_mail(employee.id)
