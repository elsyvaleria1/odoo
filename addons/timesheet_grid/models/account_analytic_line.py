from collections import defaultdict
from datetime import timedelta
from typing import Self

from dateutil.relativedelta import relativedelta
from dateutil.rrule import SU

from odoo import api, fields, models
from odoo.exceptions import AccessError, RedirectWarning, UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import format_date
from odoo.tools.date_utils import localized

from odoo.addons.resource.models.utils import split_at_midnight
from odoo.addons.timer.utils.timer_utils import round_time_spent

_debug = DebugLog(__name__)


class AccountAnalyticLine(models.Model):
    _name = "account.analytic.line"
    _inherit = ["account.analytic.line", "mixin.timer"]
    # As this model has his own data merge, avoid to enable the generic data_merge on that model.
    _disable_data_merge = True

    # reset amount on copy
    amount = fields.Monetary(copy=False)
    validated = fields.Boolean(
        string="Validated line",
        store=True,
        copy=False,
        readonly=True,
        aggregator="bool_and",
    )
    validated_status = fields.Selection(
        selection=[("draft", "Draft"), ("validated", "Validated")],
        compute="_compute_validated_status",
        required=True,
    )
    user_can_validate = fields.Boolean(
        compute="_compute_can_validate",
        help="Whether or not the current user can validate/reset to draft the record.",
    )

    display_timer = fields.Boolean(
        string="Technical field used to display the timer if the encoding unit is 'Hours'.",
        export_string_translation=False,
        compute="_compute_display_timer",
    )
    is_hatched = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_hatched",
    )

    @api.constrains("unit_amount")
    def _check_timesheet_unit_amount(self) -> None:
        if any(t.unit_amount > 999999 for t in self if t.project_id):
            raise UserError(
                self.env._("You can't encode numbers with more than six digits.")
            )

    def _is_readonly(self) -> bool:
        return super()._is_readonly() or self.validated

    def _is_timer_hidden(self) -> bool:
        self.check_singleton()
        return bool(
            (self.employee_id not in self.env.user.employee_ids) or self.validated
        )

    @api.depends("encoding_uom_id", "employee_id", "validated")
    def _compute_display_timer(self) -> None:
        uom_hour = self.env.ref("uom.product_uom_hour")
        is_uom_hour = (
            self.env.company.hr_timesheet_config_id.timesheet_encode_uom_id == uom_hour
        )
        for analytic_line in self:
            analytic_line.display_timer = (
                is_uom_hour
                and analytic_line.encoding_uom_id == uom_hour
                and not analytic_line._is_timer_hidden()
            )

    @api.model
    def grid_unavailability(self, start_date, end_date, groupby="", res_ids=()):
        start_datetime = fields.Datetime.from_string(start_date)
        end_datetime = fields.Datetime.from_string(end_date) + relativedelta(
            days=1, hour=0, minute=0, second=0
        )
        unavailability_intervals_per_employee_id = {}
        # naive datetimes are made explicit in UTC
        from_datetime = localized(start_datetime)
        to_datetime = localized(end_datetime)
        # We need to display in grey the unavailable full days
        # We start by getting the availability intervals to avoid false positive with range outside the office hours

        def get_unavailable_dates(intervals):
            # get the dates where some work can be done in the interval. It returns a list of sets.
            availability_date_list = {
                start.date() for start, _stop, _meta in split_at_midnight(intervals)
            }
            unavailable_days = []
            cur_day = from_datetime
            while cur_day < to_datetime:
                if cur_day.date() not in availability_date_list:
                    unavailable_days.append(cur_day.date())
                cur_day += timedelta(days=1)
            return list(set(unavailable_days))

        def get_company_unavailable_dates():
            company_calendar = self.env.company.resource_calendar_id
            if company_calendar.schedule_type == "flexible":
                return []
            return get_unavailable_dates(
                company_calendar._work_intervals_batch(from_datetime, to_datetime)[
                    False
                ]
            )

        if groupby == "employee_id":
            employees = self.env["hr.employee"].browse(set(res_ids))
            availability_intervals_per_resource_id, calendar_work_intervals = (
                employees.resource_id._get_valid_work_intervals(
                    from_datetime, to_datetime
                )
            )
            employee_id_per_resource_id = {
                emp.resource_id.id: emp.id for emp in employees
            }
            if not calendar_work_intervals:
                unavailability_intervals_per_employee_id[False] = (
                    get_company_unavailable_dates()
                )
                return unavailability_intervals_per_employee_id
            if self.env.company.resource_calendar_id.id in calendar_work_intervals:
                company_unavailable_days = (
                    []
                    if self.env.company.resource_calendar_id.schedule_type == "flexible"
                    else get_unavailable_dates(
                        calendar_work_intervals[
                            self.env.company.resource_calendar_id.id
                        ]
                    )
                )
            else:
                company_unavailable_days = get_company_unavailable_dates()
            unavailability_intervals_per_employee_id = {
                employee_id: []
                if self.env["resource.resource"].browse(resource_id)._is_flexible()
                else get_unavailable_dates(
                    availability_intervals_per_resource_id[resource_id]
                )
                if resource_id in availability_intervals_per_resource_id
                else company_unavailable_days
                for resource_id, employee_id in employee_id_per_resource_id.items()
            }
            unavailability_intervals_per_employee_id[False] = company_unavailable_days
        elif self.env.user.resource_calendar_id.schedule_type == "flexible":
            unavailability_intervals_per_employee_id[False] = []
        else:
            unavailability_intervals_per_employee_id[False] = (
                get_company_unavailable_dates()
            )
        return unavailability_intervals_per_employee_id

    def _compute_project_id(self) -> None:
        # override hr_timesheet to allow the check on field validated to only update the project_id on non validated timesheets.
        non_validated_timesheets = self.filtered(
            lambda t: not t.validated and t.task_id.project_id.allow_timesheets
        )
        super(AccountAnalyticLine, non_validated_timesheets)._compute_project_id()

    @api.depends("validated")
    def _compute_validated_status(self) -> None:
        for line in self:
            if line.validated:
                line.validated_status = "validated"
            else:
                line.validated_status = "draft"

    @api.depends_context("uid")
    def _compute_can_validate(self):
        is_manager = self.env.user.has_group("hr_timesheet.group_timesheet_manager")
        is_approver = self.env.user.has_group(
            "hr_timesheet.group_hr_timesheet_approver"
        )
        for line in self:
            if is_manager or (
                is_approver
                and self.env.user.id
                in {
                    line.employee_id.timesheet_manager_id.id,
                    line.employee_id.parent_id.user_id.id,
                    line.project_id.user_id.id,
                    line.user_id.id,
                }
            ):
                line.user_can_validate = True
            else:
                line.user_can_validate = False

    def _update_last_validated_timesheet_date(self) -> None:
        max_date_per_employee = {
            employee: employee.last_validated_timesheet_date
            for employee in self.employee_id.sudo()
        }
        for timesheet in self:
            max_date = max_date_per_employee[timesheet.employee_id]
            if not max_date or max_date < timesheet.date:
                max_date_per_employee[timesheet.employee_id] = timesheet.date

        employee_ids_per_date = defaultdict(list)
        for employee, max_date in max_date_per_employee.items():
            if not employee.last_validated_timesheet_date or (
                max_date and employee.last_validated_timesheet_date < max_date
            ):
                employee_ids_per_date[max_date].append(employee.id)

        for date, employee_ids in employee_ids_per_date.items():
            self.env["hr.employee"].sudo().browse(employee_ids).write(
                {"last_validated_timesheet_date": date}
            )

    @api.model
    def _search_last_validated_timesheet_date(self, employee_ids) -> None:
        EmployeeSudo = self.env["hr.employee"].sudo()
        timesheet_read_group = self.env["account.analytic.line"]._read_group(
            [
                ("validated", "=", True),
                ("project_id", "!=", False),
                ("employee_id", "in", employee_ids),
            ],
            ["employee_id"],
            ["date:max"],
        )

        EmployeeSudo.browse(employee_ids).last_validated_timesheet_date = False
        for employee, date_max in timesheet_read_group:
            employee.sudo().last_validated_timesheet_date = date_max

    @api.depends("validated")
    def _compute_is_hatched(self) -> None:
        for line in self:
            line.is_hatched = not line.validated

    def action_validate_timesheet(self):
        notification = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": None,
                "type": None,  # types: success,warning,danger,info
                "sticky": False,  # True/False will display for few seconds if false
            },
        }
        if not self.env.user.has_group("hr_timesheet.group_hr_timesheet_approver"):
            _debug.logic(
                "validate_refused",
                reason="not_approver",
                user=self.env.user,
                lines=self,
            )
            notification["params"].update(
                {
                    "message": self.env._(
                        "You can only validate the timesheets of employees of whom you are the manager or the timesheet approver."
                    ),
                    "type": "danger",
                }
            )
            return notification

        # filter in sudo to access employee manager (in domain)
        # The rest of the method and calls are anyway sudoing analytic_lines everywhere so no real impact here.
        analytic_lines = self.sudo().filtered_domain(
            self._get_domain_for_validation_timesheets()
        )
        if not analytic_lines:
            _debug.logic(
                "validate_refused",
                reason="no_validatable_lines",
                requested=self,
                user=self.env.user,
            )
            notification["params"].update(
                {
                    "message": self.env._(
                        "You cannot validate the selected timesheets as they either belong to employees who are not part of your team or are not in a state that can be validated. This may be due to the fact that they are dated in the future."
                    ),
                    "type": "danger",
                }
            )
            return notification

        analytic_lines._stop_all_users_timer()

        analytic_lines.sudo().write({"validated": True})
        analytic_lines._update_last_validated_timesheet_date()
        # Interrupt the timesheet with a timer running that is before the last validated date for each employee
        running_analytic_lines = self.env["account.analytic.line"].search(
            [
                ("employee_id", "in", analytic_lines.employee_id.ids),
                (
                    "date",
                    "<",
                    max(
                        analytic_lines.employee_id.sudo().mapped(
                            "last_validated_timesheet_date"
                        )
                    ),
                ),
                ("is_timer_running", "=", True),
            ]
        )
        running_analytic_lines.filtered(
            lambda aal: aal.date < aal.employee_id.sudo().last_validated_timesheet_date
        )._stop_all_users_timer()
        if self.env.context.get("use_notification", True):
            notification["params"].update(
                {
                    "message": self.env._(
                        "The timesheets have successfully been validated."
                    ),
                    "type": "success",
                    "next": {"type": "ir.actions.act_window_close"},
                }
            )
            return notification
        return True

    def action_invalidate_timesheet(self):
        notification = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": None,
                "type": None,
                "sticky": False,
            },
        }
        if not self.env.user.has_group("hr_timesheet.group_hr_timesheet_approver"):
            raise AccessError(
                self.env._(
                    "You can only reset to draft the timesheets of employees of whom you are the manager or the timesheet approver."
                )
            )
        # Use the same domain for validation but change validated = False to validated = True
        domain = self._get_domain_for_validation_timesheets(validated=True)
        analytic_lines = self.sudo().filtered_domain(domain)
        if not analytic_lines:
            notification["params"].update(
                {
                    "message": self.env._(
                        "There are no timesheets to reset to draft or they have already been invoiced."
                    ),
                    "type": "warning",
                }
            )
            return notification

        analytic_lines.sudo().write({"validated": False})
        self.env["account.analytic.line"]._search_last_validated_timesheet_date(
            analytic_lines.employee_id.ids
        )
        if self.env.context.get("use_notification", True):
            notification["params"].update(
                {
                    "message": self.env._(
                        "The timesheets have successfully been reset to draft."
                    ),
                    "type": "success",
                    "next": {"type": "ir.actions.act_window_close"},
                }
            )
            return notification
        return None

    def check_if_allowed(
        self,
        vals=None,
        delete=False,
    ) -> None:
        if (
            not self.env.user.has_group("hr_timesheet.group_timesheet_manager")
            and not self.env.su
        ):
            is_timesheet_approver = self.env.user.has_group(
                "hr_timesheet.group_hr_timesheet_approver"
            )
            employees = (
                self.env["hr.employee"]
                .with_context(active_test=False)
                .search(
                    [
                        ("id", "in", self.employee_id.ids),
                        ("user_id", "!=", self.env.uid),
                        "|",
                        ("parent_id.user_id", "=", self.env.uid),
                        "|",
                        ("timesheet_manager_id", "in", [False, self.env.uid]),
                        "|",
                        ("id", "in", self.env.user.employee_id.subordinate_ids.ids),
                        "&",
                        ("parent_id", "=", False),
                        ("timesheet_manager_id", "=", False),
                    ]
                )
            )

            action = (
                "delete"
                if delete
                else "modify"
                if vals is not None and "date" in vals
                else "create or edit"
            )
            for line in self:
                show_access_error = False
                employee = line.employee_id
                last_validated_timesheet_date = (
                    employee.sudo().last_validated_timesheet_date
                )

                # When an user having this group tries to modify the timesheets of another user in his own team, we shouldn't raise any validation error
                if not is_timesheet_approver or employee not in employees:
                    if line.project_id and last_validated_timesheet_date:
                        if (
                            action == "modify"
                            and self._is_validated_date(
                                fields.Date.to_date(str(vals["date"])),
                                last_validated_timesheet_date,
                            )
                        ) or self._is_validated_date(
                            line.date, last_validated_timesheet_date
                        ):
                            show_access_error = True

                if show_access_error:
                    last_validated_timesheet_date_str = format_date(
                        self.env, last_validated_timesheet_date
                    )
                    if delete:
                        error_message = self.env._(
                            "Timesheets before the %(date)s (included) have been validated, and can no longer be deleted.",
                            date=last_validated_timesheet_date_str,
                        )
                    else:
                        error_message = self.env._(
                            "Timesheets before the %(date)s (included) have been validated, and can no longer be modified.",
                            date=last_validated_timesheet_date_str,
                        )
                    raise AccessError(error_message)

    @api.model
    def _is_validated_date(self, date, validated_until) -> bool:
        return date != fields.Date.today() and date <= validated_until

    def _check_can_create(self):
        # Check if the user has the correct access to create timesheets
        if not (
            self.env.user.has_group("hr_timesheet.group_hr_timesheet_approver")
            or self.env.su
        ) and any(line.project_id and line.user_id != self.env.user for line in self):
            _debug.logic(
                "create_denied", reason="not_own", user=self.env.user, lines=self
            )
            raise AccessError(
                self.env._("You cannot access timesheets that are not yours.")
            )
        self.check_if_allowed()

        return super()._check_can_create()

    def _check_can_write(self, vals):
        if not self.env.user.has_group("hr_timesheet.group_hr_timesheet_approver"):
            if "validated" in vals:
                _debug.logic(
                    "write_denied",
                    reason="validate_needs_approver",
                    user=self.env.user,
                    lines=self,
                )
                raise AccessError(
                    self.env._(
                        "You can only validate the timesheets of employees of whom you are the manager or the timesheet approver."
                    )
                )
            if self.filtered(lambda r: r.project_id and r.validated):
                _debug.logic(
                    "write_denied",
                    reason="entry_validated",
                    user=self.env.user,
                    lines=self.filtered(lambda r: r.project_id and r.validated),
                )
                raise AccessError(
                    self.env._(
                        "Only a Timesheets Approver or Manager is allowed to modify a validated entry."
                    )
                )

        self.check_if_allowed(vals)

        return super()._check_can_write(vals)

    def _get_timesheet_action(self, value) -> dict:
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Open Form"),
            "res_model": "account.analytic.line",
            "views": [
                (
                    self.env.ref("timesheet_grid.timesheet_view_form_user_grid").id,
                    "form",
                )
            ],
            "context": {
                **self.env.context,
                "default_unit_amount": value,
                "is_timesheet": True,
            },
        }

    def _update_existing_timers(self, vals) -> None:
        if "task_id" in vals:
            # Check if there are some running timers linked to the timesheets to also update them.
            timers = self.env["timer.timer"].search([("res_id", "in", self.ids)])
            if timers:
                timers.write(
                    {
                        "parent_res_model": "project.task" if vals["task_id"] else None,
                        "parent_res_id": vals["task_id"],
                    }
                )

    def write(self, vals):
        res = super().write(vals)
        self._update_existing_timers(vals)
        return res

    @api.model
    def _get_timesheet_field_and_model_name(self) -> tuple:
        return "task_id", "project.task"

    @api.model
    def grid_update_cell(self, domain, measure_field_name, value):
        if value == 0:  # nothing to do
            return
        timesheets = self.search(domain, limit=2)

        # sudo in case of timesheeting a task belonging to a private project
        if timesheets.project_id and not all(
            timesheets.project_id.sudo().mapped("allow_timesheets")
        ):
            raise UserError(
                self.env._(
                    "You cannot adjust the time of the timesheet for a project with timesheets disabled."
                )
            )

        non_validated_timesheets = timesheets.filtered(
            lambda timesheet: not timesheet.validated
        )
        if len(non_validated_timesheets) > 1 or (
            len(timesheets) == 1 and timesheets.validated
        ):
            timesheets[0].copy(
                {
                    "name": "/",
                    measure_field_name: value,
                }
            )
        elif len(non_validated_timesheets) == 1:
            non_validated_timesheets[measure_field_name] += value
        else:
            project_id = self.env.context.get("default_project_id", False)
            field_name, model_name = self._get_timesheet_field_and_model_name()
            field_value = self.env.context.get(f"default_{field_name}", False)
            if not project_id and field_value:
                project_id = self.env[model_name].browse(field_value).project_id.id
            if not project_id:
                warning_msg = self.env._(
                    "Your timesheet entry is missing a project. Please either group the Grid view by project or enter your timesheets by adding a line via the Form view."
                )
                action = self._get_timesheet_action(value)
                raise RedirectWarning(warning_msg, action, self.env._("Open Form"))

            if (
                not self.env["project.project"]
                .browse(project_id)
                .sudo()
                .allow_timesheets
            ):
                raise UserError(
                    self.env._(
                        "You cannot adjust the time of the timesheet for a project with timesheets disabled."
                    )
                )

            self.create(
                {
                    "name": "/",
                    "project_id": project_id,
                    field_name: field_value,
                    measure_field_name: value,
                }
            )

    @api.ondelete(at_uninstall=False)
    def _unlink_if_manager(self) -> None:
        if not self.env.user.has_group(
            "hr_timesheet.group_hr_timesheet_approver"
        ) and self.filtered(lambda r: r.project_id and r.validated):
            raise AccessError(
                self.env._(
                    "You cannot delete a validated entry. Please contact your manager or your timesheet approver."
                )
            )

        self.check_if_allowed(delete=True)

    def unlink(self):
        res = super().unlink()
        self.env["timer.timer"].search(
            [("res_model", "=", self._name), ("res_id", "in", self.ids)]
        ).unlink()
        return res

    def _get_project_and_task_ids(self, domain) -> tuple:
        project_id = task_id = False
        for subdomain in domain:
            if subdomain[0] == "project_id" and subdomain[1] == "=":
                project_id = subdomain[2]
            elif subdomain[0] == "task_id" and subdomain[1] == "=":
                task_id = subdomain[2]
        return project_id, task_id

    def _prepare_duplicate_timesheet_line_values(
        self, column_field, day, cell_field, change
    ) -> dict:
        # Prepares all values that should be set/modified when duplicating the current analytic line
        return {
            "name": "/",
            column_field: day,
            cell_field: change,
        }

    def _get_last_week(self) -> tuple:
        today = fields.Date.to_string(fields.Date.today())
        grid_anchor = self.env.context.get("grid_anchor", today)
        last_week = fields.Datetime.from_string(grid_anchor)
        last_week += relativedelta(weekday=SU(-2))
        return grid_anchor, last_week.date()

    # ----------------------------------------------------
    # Timer Methods
    # ----------------------------------------------------

    @api.model
    def action_start_new_timesheet_timer(self, vals):
        project = self.env["project.project"].browse(vals.get("project_id", False))
        if not project:
            task = self.env["project.task"].browse(vals.get("task_id", False))
            project = task.project_id or self.env["project.project"].browse(
                self._get_favorite_project_id()
            )
        result = bool(project) and project.check_can_start_timer()
        if result is True:
            if "default_date" in self.env.context:
                self = self.with_context(default_date=fields.Date.today())
            timesheet = self.create(
                {
                    **vals,
                    "project_id": project.id,
                }
            )
            timesheet.action_timer_start()
            return timesheet._get_timesheet_timer_data()
        return result

    def _prepare_timesheet_timer_vals(self) -> dict:
        return {
            "name": self.name,
            "date": fields.Date.today(),
            "project_id": self.project_id.id,
            "task_id": self.task_id.id,
        }

    def action_timer_start(self):
        """Action start the timer of current timesheet

        * Override method of hr_timesheet module.
        """
        if self.validated:
            raise UserError(
                self.env._("You cannot use the timer on validated timesheets.")
            )
        timesheet = self
        if (
            self.employee_id.sudo().last_validated_timesheet_date
            and self.date < self.employee_id.sudo().last_validated_timesheet_date
        ):
            timesheet = self.create(self._prepare_timesheet_timer_vals())
            timesheet.action_timer_start()
        elif not self.user_timer_id.timer_start and self.display_timer:
            if self.date != fields.Date.context_today(
                self
            ) and not self.env.context.get("_from_action_timer"):
                timesheet = self.create(self._prepare_timesheet_timer_vals())
                timesheet.with_context(_from_action_timer=True).action_timer_start()
            else:
                super().action_timer_start()
        return timesheet._get_timesheet_timer_data()

    def _get_domain_last_timesheet(self):
        self.check_singleton()
        return [
            ("id", "!=", self.id),
            ("user_id", "=", self.env.user.id),
            ("project_id", "=", self.project_id.id),
            ("task_id", "=", self.task_id.id),
            ("date", "=", fields.Date.context_today(self)),
            ("name", "=", "/"),
            ("validated", "=", False),
        ]

    def _add_timesheet_time(self, minutes_spent, try_to_match=False):
        if self.unit_amount == 0 and not minutes_spent:
            # Check if unit_amount equals 0,
            # if yes, then remove the timesheet
            self.unlink()
            return 0
        minutes_spent = self.get_rounded_time(minutes_spent)
        amount = self.unit_amount + minutes_spent
        if not try_to_match or self.name != "/":
            self.write({"unit_amount": amount})
            return minutes_spent

        domain = self._get_domain_last_timesheet()
        last_timesheet_id = self.search(domain, limit=1)
        # If the last timesheet of the day for this project and task has no description,
        # we match both together.
        if last_timesheet_id:
            last_timesheet_id.unit_amount += amount
            self.unlink()
        else:
            self.write({"unit_amount": amount})
        return minutes_spent

    def action_timer_stop(self, try_to_match=False):
        """Action stop the timer of the current timesheet
        try_to_match: if true, we try to match with another timesheet which corresponds to the following criteria:
        1. Neither of them has a description
        2. The last one is not validated
        3. Match user, project task, and must be the same day.

        * Override method of timer module.
        """
        if self.env.user == self.sudo().user_id:
            # sudo as we can have a timesheet related to a company other than the current one.
            self = self.sudo()
        if self.validated:
            raise UserError(
                self.env._("You cannot use the timer on validated timesheets.")
            )
        amount = 0
        if self.user_timer_id.timer_start:
            minutes_spent = super().action_timer_stop()
            amount = self._add_timesheet_time(minutes_spent, try_to_match)
        return amount

    def _stop_all_users_timer(self, try_to_match=False) -> None:
        """Stop ALL the timers of the timesheets (WHOEVER the timer associated user is)
        try_to_match: if true, we try to match with another timesheet which corresponds to the following criteria:
        1. Neither of them has a description
        2. The last one is not validated
        3. Match user, project task, and must be the same day.
        """
        if any(self.sudo().mapped("validated")):
            raise UserError(
                self.env._("Sorry, you cannot use a timer for a validated timesheet")
            )
        timers = (
            self.env["timer.timer"]
            .sudo()
            .search([("res_id", "in", self.ids), ("res_model", "=", self._name)])
        )
        for timer in timers:
            minutes_spent = timer.action_timer_stop()
            self.env["account.analytic.line"].browse(
                timer.res_id
            ).sudo()._add_timesheet_time(minutes_spent, try_to_match)
            timer.unlink()

    def action_timer_unlink(self) -> None:
        """Action unlink the timer of the current timesheet"""
        if self.env.user == self.sudo().user_id:
            # sudo as we can have a timesheet related to a company other than the current one.
            self = self.sudo()
        self.user_timer_id.unlink()
        if not self.unit_amount:
            self.unlink()

    def _action_interrupt_user_timers(self) -> None:
        self.action_timer_stop()

    def _get_timesheet_timer_field_names(self) -> list:
        return [
            "date",
            "name",
            "company_id",
            "project_id",
            "task_id",
            "unit_amount",
            "timer_start",
        ]

    def _coerce_concurrency_value(self, field, value):
        # "/" is how a timer names a timesheet that has no description yet, and
        # `_get_timesheet_timer_data` hands the client "" for it, so the client's
        # first description is checked against a baseline of "" while the row
        # holds "/". The two are one value: no description.
        if field.name == "name" and value == "/":
            value = ""
        return super()._coerce_concurrency_value(field, value)

    def _get_timesheet_timer_data(self):
        """Get timesheet timer data needed to correctly run the timer

        :return Dictionary containing timer data
        :rtype {'field_name': field_value}
        """
        self.check_singleton()
        timesheet_data = {"other_company": True}
        if self.company_id in self.env.companies:
            timesheet_data = self._read_format(self._get_timesheet_timer_field_names())[
                0
            ]
            if timesheet_data["name"] == "/":
                timesheet_data["name"] = ""
        return timesheet_data

    @api.model
    def get_running_timer(self):
        res = {
            "step_timer": int(
                self.env.registry.settings.get(
                    self.env, "timesheet_grid.timesheet_min_duration", 15
                )
            )
        }
        timer = self.env["timer.timer"].search(
            [
                ("user_id", "=", self.env.user.id),
                ("timer_start", "!=", False),
                ("timer_pause", "=", False),
                ("res_model", "=", self._name),
            ],
            limit=1,
        )
        if timer:
            # sudo as we can have a timesheet related to a company other than the current one.
            res.update(self.sudo().browse(timer.res_id)._get_timesheet_timer_data())
        return res

    @api.model
    def get_rounded_time(self, timer):
        minimum_duration = int(
            self.env.registry.settings.get(
                self.env, "timesheet_grid.timesheet_min_duration", 0
            )
        )
        rounding = int(
            self.env.registry.settings.get(
                self.env, "timesheet_grid.timesheet_rounding", 0
            )
        )
        rounded_minutes = round_time_spent(timer, minimum_duration, rounding)
        return rounded_minutes / 60

    @api.model
    def _add_time_to_timesheet_fields(self):
        return ["task_id"]

    def action_add_time_to_timesheet(self, vals):
        minutes = int(
            self.env.registry.settings.get(
                self.env, "timesheet_grid.timesheet_min_duration", 15
            )
        )
        if self:
            for field in self._add_time_to_timesheet_fields():
                val = vals.get(field, False)
                if self[field].id == val and self.project_id.id == vals["project_id"]:
                    self.unit_amount += minutes / 60
                    return self.id
        timesheet = self.create(
            {
                **vals,
                "unit_amount": minutes / 60,
            }
        )
        return timesheet.id

    def action_add_time_to_timer(self, time) -> None:
        if self.validated:
            raise UserError(
                self.env._("You cannot use the timer on validated timesheets.")
            )
        if not self.user_id.employee_ids:
            raise UserError(
                self.env._("An employee must be linked to your user to record time.")
            )
        timer = self.user_timer_id
        if not timer:
            self.action_timer_start()
            timer = self.user_timer_id
        timer.timer_start = min(
            timer.timer_start - timedelta(0, time), fields.Datetime.now()
        )

    def change_description(self, description) -> None:
        if not self.exists():
            return
        if True in self.mapped("validated"):
            raise UserError(
                self.env._("You cannot use the timer on validated timesheets.")
            )
        self.write({"name": description})

    def action_change_project_task(self, new_project_id, new_task_id):
        if self.validated:
            raise UserError(
                self.env._("You cannot use the timer on validated timesheets.")
            )
        if not self.unit_amount:
            self.write(
                {
                    "project_id": new_project_id,
                    "task_id": new_task_id,
                }
            )
            return self.id

        new_timesheet = self.create(
            {
                "name": self.name,
                "project_id": new_project_id,
                "task_id": new_task_id,
            }
        )
        self.user_timer_id.res_id = new_timesheet
        return new_timesheet.id

    def _get_domain_for_validation_timesheets(self, validated=False):
        """Get the domain to check if the user can validate/invalidate which timesheets

        2 access rights give access to validate timesheets:

        1. Approver: in this access right, the user can't validate all timesheets,
        he can validate the timesheets where he is the manager or timesheet responsible of the
        employee who is assigned to this timesheets or the user is the owner of the project.
        The user cannot validate his own timesheets.

        2. Manager (Administrator): with this access right, the user can validate all timesheets.
        """
        domain = Domain("project_id", "!=", False) & Domain("validated", "=", validated)
        if not validated:
            domain &= Domain("date", "<=", fields.Date.today())

        if not self.env.user.has_group("hr_timesheet.group_timesheet_manager"):
            return Domain.AND(
                [
                    domain,
                    Domain("user_id", "!=", self.env.uid),
                    [
                        "|",
                        (
                            "employee_id.timesheet_manager_id",
                            "in",
                            [False, self.env.uid],
                        ),
                        "|",
                        (
                            "employee_id",
                            "in",
                            self.env.user.employee_id.subordinate_ids.ids,
                        ),
                        "|",
                        ("employee_id.parent_id.user_id", "=", self.env.uid),
                        "&",
                        ("employee_id.timesheet_manager_id", "=", False),
                        ("employee_id.parent_id", "=", False),
                    ],
                ]
            )
        return domain

    def _filtered_to_merge(self) -> Self:
        return self.filtered(lambda l: l.project_id and not l.validated)

    def action_merge_timesheets(self) -> dict:
        to_merge = self._filtered_to_merge()

        if len(to_merge) <= 1:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "message": self.env._("There are no timesheets to merge."),
                    "type": "warning",
                    "sticky": False,
                },
            }

        return {
            "name": self.env._("Merge Timesheets"),
            "view_mode": "form",
            "res_model": "wizard.account.analytic.line.merge",
            "views": [
                (
                    self.env.ref("timesheet_grid.timesheet_merge_wizard_view_form").id,
                    "form",
                )
            ],
            "type": "ir.actions.act_window",
            "target": "new",
            "context": dict(self.env.context, active_ids=to_merge.ids),
        }

    def action_timer_increase(self) -> None:
        min_duration = int(
            self.env.registry.settings.get(
                self.env, "timesheet_grid.timesheet_min_duration", 15
            )
        )
        self.update({"unit_amount": self.unit_amount + (min_duration / 60)})

    def action_timer_decrease(self) -> None:
        min_duration = int(
            self.env.registry.settings.get(
                self.env, "timesheet_grid.timesheet_min_duration", 15
            )
        )
        duration = self.unit_amount - (min_duration / 60)
        self.update({"unit_amount": max(0, duration)})

    def _prepare_timer_vals(self):
        vals = super()._prepare_timer_vals()
        if self.task_id:
            vals["parent_res_model"] = "project.task"
            vals["parent_res_id"] = self.task_id.id
        return vals
