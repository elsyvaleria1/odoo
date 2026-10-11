import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    next_appraisal_date = fields.Date(
        compute="_compute_next_appraisal_date",
        store=True,
        copy=False,
        readonly=False,
        groups="hr.group_hr_user",
        help="The date of the next appraisal is computed by the appraisal plan's dates (first appraisal + periodicity).",
    )
    accessible_next_appraisal_date = fields.Date(
        compute="_compute_accessible_next_appraisal_date",
        search="_search_accessible_next_appraisal_date",
    )
    last_ongoing_appraisal_date = fields.Date(
        compute="_compute_last_ongoing_appraisal_date",
        groups="hr.group_hr_user",
    )
    is_last_appraisal_late = fields.Boolean(
        compute="_compute_last_ongoing_appraisal_date",
        groups="hr.group_hr_user",
    )
    related_partner_id = fields.Many2one(
        comodel_name="res.partner",
        compute="_compute_related_partner",
        groups="hr.group_hr_user",
    )
    ongoing_appraisal_count = fields.Integer(
        compute="_compute_ongoing_appraisal_count",
        store=True,
    )
    appraisal_count = fields.Integer(
        compute="_compute_appraisal_count",
        store=True,
        groups="hr.group_hr_user",
    )
    uncomplete_goals_count = fields.Integer(
        compute="_compute_uncomplete_goals_count",
        groups="hr.group_hr_user",
    )
    goals_count = fields.Integer(
        compute="_compute_goals_count",
        groups="hr.group_hr_user",
    )
    appraisal_ids = fields.One2many(
        comodel_name="hr.appraisal",
        inverse_name="employee_id",
        groups="hr.group_hr_user",
    )
    can_request_appraisal = fields.Boolean(compute="_compute_can_request_appraisal")
    goals_ids = fields.Many2many(
        comodel_name="hr.appraisal.goal",
        relation="hr_appraisal_goal_hr_employee_rel",
        column1="hr_employee_id",
        groups="hr.group_hr_user",
    )
    parent_user_id = fields.Many2one(
        related="parent_id.user_id",
        string="Parent User",
    )
    last_appraisal_id = fields.Many2one(comodel_name="hr.appraisal")
    last_appraisal_state = fields.Selection(
        related="last_appraisal_id.state",
        string="Last Appraisal Status",
    )

    def _get_appraisal_plan_starting_date(self):
        self.check_singleton()
        return self.contract_date_start or self.date_version

    def action_send_appraisal_request(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "hr.appraisal",
            "name": self.env._("Appraisal Request"),
            "context": self.env.context,
        }

    def action_view_last_appraisal(self) -> dict:
        self.check_singleton()
        employee_appraisals = self.with_context(active_test=False).appraisal_ids
        opened_appraisals = employee_appraisals.filtered(
            lambda a: a.state in ["1_new", "2_pending"]
        )
        done_appraisals = employee_appraisals.filtered(lambda a: a.state == "3_done")
        relevant_appraisals = employee_appraisals
        if opened_appraisals:
            relevant_appraisals = opened_appraisals
        elif done_appraisals:
            relevant_appraisals = done_appraisals[0]
        if len(relevant_appraisals) == 1:
            return {
                "view_mode": "form",
                "res_model": "hr.appraisal",
                "type": "ir.actions.act_window",
                "target": "current",
                "res_id": relevant_appraisals.id,
            }
        else:
            return {
                "view_mode": "list",
                "name": self.env._("New and Pending Appraisals"),
                "res_model": "hr.appraisal",
                "views": [
                    [self.env.ref("hr_appraisal.view_hr_appraisal_tree").id, "list"],
                    [False, "form"],
                ],
                "type": "ir.actions.act_window",
                "target": "current",
                "domain": [("id", "in", relevant_appraisals.ids)],
            }

    @api.depends_context("uid")
    def _compute_can_request_appraisal(self) -> None:
        children_ids = self.env.user.get_employee_autocomplete_ids().ids
        for employee in self:
            employee.can_request_appraisal = employee.id in children_ids

    @api.constrains("next_appraisal_date")
    def _check_next_appraisal_date(self) -> None:
        today = fields.Date.today()
        if not self.env.context.get("install_mode") and any(
            employee.next_appraisal_date and employee.next_appraisal_date < today
            for employee in self
        ):
            raise ValidationError(
                self.env._("You cannot set 'Next Appraisal Date' in the past.")
            )

    @api.depends("user_id", "partner_id")
    def _compute_related_partner(self) -> None:
        for rec in self:
            rec.related_partner_id = rec.user_id.partner_id or rec.partner_id

    @api.depends("appraisal_ids")
    def _compute_appraisal_count(self) -> None:
        read_group_result = (
            self.env["hr.appraisal"]
            .with_context(active_test=False)
            ._read_group(
                [("employee_id", "in", self.ids)], ["employee_id"], ["__count"]
            )
        )
        result = {employee.id: count for employee, count in read_group_result}
        for employee in self:
            employee.appraisal_count = result.get(employee.id, 0)

    @api.depends("appraisal_ids.state")
    def _compute_ongoing_appraisal_count(self) -> None:
        read_group_result = (
            self.env["hr.appraisal"]
            .with_context(active_test=False)
            ._read_group(
                [
                    ("employee_id", "in", self.ids),
                    ("state", "in", ["1_new", "2_pending"]),
                ],
                ["employee_id"],
                ["__count"],
            )
        )
        result = {employee.id: count for employee, count in read_group_result}
        for employee in self:
            employee.ongoing_appraisal_count = result.get(employee.id, 0)

    @api.depends("goals_ids.progression", "goals_ids.child_ids")
    def _compute_uncomplete_goals_count(self) -> None:
        read_group_result = self.env["hr.appraisal.goal"]._read_group(
            [
                ("employee_ids", "in", self.ids),
                ("progression", "!=", "100"),
                ("child_ids", "=", False),
            ],
            ["employee_ids"],
            ["__count"],
        )
        result = {employee.id: count for employee, count in read_group_result}
        for employee in self:
            employee.uncomplete_goals_count = result.get(employee.id, 0)

    @api.depends("goals_ids.child_ids")
    def _compute_goals_count(self) -> None:
        read_group_result = self.env["hr.appraisal.goal"]._read_group(
            [("employee_ids", "in", self.ids), ("child_ids", "=", False)],
            ["employee_ids"],
            ["__count"],
        )
        result = {employee.id: count for employee, count in read_group_result}
        for employee in self:
            employee.goals_count = result.get(employee.id, 0)

    @api.depends(
        "ongoing_appraisal_count",
        "company_id.appraisal_plan",
        "company_id.duration_after_recruitment",
        "company_id.duration_first_appraisal",
        "company_id.duration_next_appraisal",
    )
    def _compute_next_appraisal_date(self) -> None:
        self.filtered("ongoing_appraisal_count").next_appraisal_date = False
        employees_without_appraisal = self.filtered(
            lambda e: e.ongoing_appraisal_count == 0 and e.company_id.appraisal_plan
        )
        dates = employees_without_appraisal._upcoming_appraisal_creation_date()
        for employee in employees_without_appraisal:
            employee.next_appraisal_date = dates[employee.id]

    @api.depends("appraisal_ids.state", "appraisal_ids.date_close")
    def _compute_last_ongoing_appraisal_date(self) -> None:
        for employee in self:
            ongoing_appraisals = employee.appraisal_ids.filtered(
                lambda appraisal: appraisal.state in ["1_new", "2_pending"]
            )
            if ongoing_appraisals:
                employee.last_ongoing_appraisal_date = max(
                    ongoing_appraisals.mapped("date_close")
                )
                employee.is_last_appraisal_late = (
                    employee.last_ongoing_appraisal_date < fields.Date.today()
                )
            else:
                employee.last_ongoing_appraisal_date = False
                employee.is_last_appraisal_late = False

    def _upcoming_appraisal_creation_date(self):
        today = fields.Date.today()
        dates = {}
        for employee in self:
            if employee.appraisal_count == 0:
                months = employee.company_id.duration_after_recruitment
                starting_date = employee._get_appraisal_plan_starting_date() or today
            else:
                months = (
                    employee.company_id.duration_first_appraisal
                    if employee.appraisal_count == 1
                    else employee.company_id.duration_next_appraisal
                )
                starting_date = employee.last_appraisal_id.date_close

            if starting_date:
                starting_date = (
                    starting_date.date()
                    if isinstance(starting_date, datetime.datetime)
                    else starting_date
                )
                original_next_appraisal_date = starting_date + relativedelta(
                    months=months
                )
                dates[employee.id] = (
                    original_next_appraisal_date
                    if original_next_appraisal_date >= today
                    else today + relativedelta(months=months)
                )
            else:
                dates[employee.id] = today + relativedelta(months=months)
        return dates

    def action_view_goals(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_appraisal.action_hr_appraisal_goal"
        )
        action.update(
            {
                "domain": [("employee_ids", "=", self.id), ("child_ids", "=", False)],
                "context": {"default_employee_ids": self.ids},
            }
        )
        return action

    def action_view_employee_appraisals(self):
        self.check_singleton()
        if len(self.appraisal_ids) == 1:
            return {
                "res_model": "hr.appraisal",
                "view_mode": "form",
                "type": "ir.actions.act_window",
                "target": "current",
                "res_id": self.appraisal_ids[0].id,
            }
        return self.appraisal_ids[:1].action_view_employee_appraisals()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_goal_manager(self) -> None:
        is_goal_manager = self.env["hr.appraisal.goal"].search_count(
            [("manager_ids", "in", self.ids)], limit=1
        )
        if is_goal_manager:
            raise UserError(
                self.env._(
                    "You cannot delete an employee who is a goal's manager, archive it instead."
                )
            )

    def _appraisal_manager_scope(self):
        if self.env.su or self.env.user.has_group("hr.group_hr_user"):
            return None
        user_employee = self.env.user.employee_id
        if not user_employee:
            return set()
        return set(
            self.env["hr.employee"]
            .sudo()
            .search([("id", "child_of", user_employee.id)])
            .ids
        )

    @api.depends("next_appraisal_date")
    @api.depends_context("uid")
    def _compute_accessible_next_appraisal_date(self) -> None:
        scope = self._appraisal_manager_scope()
        for employee in self:
            visible = scope is None or employee.id in scope
            employee.accessible_next_appraisal_date = (
                employee.sudo().next_appraisal_date if visible else False
            )

    def _search_accessible_next_appraisal_date(self, operator, value) -> list:
        employee_ids = set(
            self.sudo().search([("next_appraisal_date", operator, value)]).ids
        )
        scope = self._appraisal_manager_scope()
        if scope is not None:
            employee_ids &= scope
        return [("id", "in", list(employee_ids))]
