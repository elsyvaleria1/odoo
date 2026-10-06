from collections import defaultdict
from datetime import UTC

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

from odoo.addons.resource.models.utils import last_day_of

_debug = DebugLog(__name__)


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    allow_timesheets = fields.Boolean(
        related="project_id.allow_timesheets",
        string="Allow timesheets",
        readonly=True,
        help="Timesheets can be logged on this slot.",
    )
    effective_hours = fields.Float(
        string="Effective Time",
        compute="_compute_effective_hours",
        compute_sudo=True,
        store=True,
        help="Number of time recorded on the employee's Timesheets for this task (and its sub-tasks) during the timeframe of the shift.",
    )
    effective_hours_cost = fields.Float(
        string="Effective Time Cost",
        compute="_compute_effective_hours",
        compute_sudo=True,
        store=True,
        groups="hr.group_hr_user",
        help="What the timesheets recorded in the timeframe of this shift cost.",
    )
    timesheet_ids = fields.Many2many(
        comodel_name="account.analytic.line",
        export_string_translation=False,
        compute="_compute_timesheet_ids",
        compute_sudo=True,
    )
    can_open_timesheets = fields.Boolean(
        export_string_translation=False,
        compute="_compute_can_open_timesheet",
    )
    percentage_hours = fields.Float(
        string="Progress",
        compute="_compute_percentage_hours",
        compute_sudo=True,
        store=True,
    )
    encode_uom_in_days = fields.Boolean(
        export_string_translation=False,
        compute="_compute_encode_uom_in_days",
    )

    def _compute_encode_uom_in_days(self) -> None:
        self.encode_uom_in_days = (
            self.env.company.hr_timesheet_config_id.timesheet_encode_uom_id
            == self.env.ref("uom.product_uom_day")
        )

    @api.depends("allocated_hours", "effective_hours")
    def _compute_percentage_hours(self) -> None:
        for forecast in self:
            if forecast.allocated_hours:
                forecast.percentage_hours = (
                    forecast.effective_hours / forecast.allocated_hours * 100
                )
            else:
                forecast.percentage_hours = 0

    def _get_domain_timesheet(self):
        """
        Returns the domain used to fetch the timesheets, None is returned in case there would be no match
        """
        self.check_singleton()
        if not self.project_id:
            return None
        domain = Domain(
            [
                ("employee_id", "=", self.employee_id.id),
                ("date", ">=", self.start_datetime.date()),
                ("date", "<=", last_day_of(self.start_datetime, self.end_datetime)),
            ]
        )
        if self.project_id:
            domain = Domain("project_id", "=", self.project_id.id) & domain
        return domain

    @api.depends("timesheet_ids")
    def _compute_effective_hours(self) -> None:
        for forecast in self:
            forecast.effective_hours = sum(
                timesheet.unit_amount for timesheet in forecast.timesheet_ids
            )
            forecast.effective_hours_cost = -sum(
                timesheet.amount for timesheet in forecast.timesheet_ids
            )

    @api.depends(
        "employee_id",
        "start_datetime",
        "end_datetime",
        "project_id.timesheet_ids.unit_amount",
        "project_id.timesheet_ids.amount",
        "project_id.timesheet_ids.date",
        "project_id.timesheet_ids.employee_id",
    )
    def _compute_timesheet_ids(self) -> None:
        self.timesheet_ids = False
        _debug.perf.count("forecast_timesheet_link", slots=self)
        datable = self.filtered(
            lambda forecast: (
                forecast.project_id
                and forecast.start_datetime
                and forecast.end_datetime
            )
        )
        if not datable:
            return
        # One search for the whole recordset, bucketed by the pair
        # `_get_domain_timesheet` matches on; searching per slot is a query per
        # slot, and every timesheet written to the project recomputes all of them.
        employee_ids = datable.employee_id.ids
        if not all(forecast.employee_id for forecast in datable):
            employee_ids = [*employee_ids, False]
        timesheets = self.env["account.analytic.line"].search(
            [
                ("project_id", "in", datable.project_id.ids),
                ("employee_id", "in", employee_ids),
                ("date", ">=", min(datable.mapped("start_datetime")).date()),
                ("date", "<=", max(datable.mapped("end_datetime")).date()),
            ]
        )
        by_pair = defaultdict(list)
        for timesheet in timesheets:
            by_pair[(timesheet.project_id.id, timesheet.employee_id.id)].append(
                timesheet
            )
        for forecast in datable:
            start = forecast.start_datetime.date()
            end = last_day_of(forecast.start_datetime, forecast.end_datetime)
            forecast.timesheet_ids = timesheets.browse(
                [
                    timesheet.id
                    for timesheet in by_pair[
                        (forecast.project_id.id, forecast.employee_id.id)
                    ]
                    if start <= timesheet.date <= end
                ]
            )

    def _read_group_fields_nullify(self):
        return super()._read_group_fields_nullify() + [
            "effective_hours:sum",
            "effective_hours_cost:sum",
            "percentage_hours:sum",
        ]

    @api.depends_context("uid")
    @api.depends("user_id", "timesheet_ids")
    def _compute_can_open_timesheet(self) -> None:
        # A timesheet approver will be able to open any slot's timesheets, however
        # a regular employee will need to be a timesheet user AND be assigned to this slot
        # to be able to open them.
        is_approver = self.env.user.has_group(
            "hr_timesheet.group_hr_timesheet_approver"
        )
        is_user = is_approver or self.env.user.has_group(
            "hr_timesheet.group_hr_timesheet_user"
        )
        if not is_user:
            self.can_open_timesheets = False
        else:
            for slot in self:
                if is_approver or (is_user and self.env.user == slot.user_id):
                    slot.can_open_timesheets = True
                else:
                    slot.can_open_timesheets = False

    def _gantt_progress_bar_project_id(self, res_ids, start, stop):
        planning_read_group = self.env["planning.slot"]._read_group(
            [
                ("project_id", "in", res_ids),
                ("start_datetime", "<=", stop.replace(tzinfo=None)),
                ("end_datetime", ">=", start.replace(tzinfo=None)),
            ],
            ["project_id"],
            ["allocated_hours:sum"],
        )
        dict_values_per_project = {
            project.id: {
                "value": allocated_hours_sum,
                "max_value": project.sudo().allocated_hours,
            }
            for project, allocated_hours_sum in planning_read_group
        }
        project_dict = {
            project.id: project.allocated_hours
            for project in self.env["project.project"]
            .sudo()
            .search([("id", "in", res_ids)])
        }
        for project_id, allocated_hours in project_dict.items():
            if project_id not in dict_values_per_project:
                dict_values_per_project[project_id] = {
                    "value": 0.0,
                    "max_value": allocated_hours,
                }
        return dict_values_per_project

    def _gantt_progress_bar(self, field_name, res_ids, start, stop):
        if field_name == "project_id":
            return self._gantt_progress_bar_project_id(
                res_ids, start.replace(tzinfo=UTC), stop.replace(tzinfo=UTC)
            )
        return super()._gantt_progress_bar(field_name, res_ids, start, stop)

    def action_view_timesheets(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "hr_timesheet.timesheet_action_all"
        )
        # Remove all references to the original action, to avoid studio and be able to change the action name
        action.pop("id", None)
        action.pop("xml_id", None)
        action.pop("display_name", None)
        action.update(
            {
                "name": self.env._("Timesheets"),
                "domain": self._get_domain_timesheet(),
                "view_mode": "list,grid,kanban,pivot,graph,form",
                "mobile_view_mode": "grid",
                "views": [
                    [self.env.ref("hr_timesheet.timesheet_view_tree_user").id, "list"],
                    [
                        self.env.ref(
                            "timesheet_grid.timesheet_view_grid_by_employee"
                        ).id,
                        "grid",
                    ],
                    [
                        self.env.ref(
                            "hr_timesheet.view_kanban_account_analytic_line"
                        ).id,
                        "kanban",
                    ],
                    [
                        self.env.ref("hr_timesheet.view_hr_timesheet_line_pivot").id,
                        "pivot",
                    ],
                    [
                        self.env.ref(
                            "hr_timesheet.view_hr_timesheet_line_graph_all"
                        ).id,
                        "graph",
                    ],
                    [self.env.ref("hr_timesheet.hr_timesheet_line_form").id, "form"],
                ],
            }
        )
        action["context"] = {
            "default_date": self.start_datetime.date()
            if self.start_datetime < fields.Datetime.now()
            else fields.Date.today(),
            "default_employee_id": self.employee_id.id,
            "default_project_id": self.project_id.id,
            "grid_anchor": self.start_datetime.date(),
        }
        if self.duration < 24:
            action["context"]["default_unit_amount"] = self.allocated_hours
        return action
