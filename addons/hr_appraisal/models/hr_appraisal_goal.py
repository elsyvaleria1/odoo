from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import frozendict
from odoo.tools.misc import get_lang


class HrAppraisalGoal(models.Model):
    _name = "hr.appraisal.goal"
    _inherit = ["mixin.hr", "mixin.mail.thread", "mixin.mail.activity"]
    _description = "Appraisal Goal"
    _parent_name = "parent_id"
    _parent_store = True
    _access_anchors = frozendict(
        {
            "employee_parent_user": models.Anchor(
                "employee_ids.parent_id.user_id", kind="owner"
            ),
            "employee_user": models.Anchor("employee_ids.user_id", kind="owner"),
            "manager_user": models.Anchor("manager_ids.user_id", kind="owner"),
            "owner": "employee_ids.last_appraisal_id.manager_ids.user_id",
        }
    )

    name = fields.Char(required=True)
    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="hr_appraisal_goal_hr_employee_rel",
        column1="hr_appraisal_goal_id",
        ondelete="cascade",
        tracking=True,
    )
    employee_autocomplete_ids = fields.Many2many(
        comodel_name="hr.employee",
        compute="_compute_employee_autocomplete",
        compute_sudo=True,
    )
    company_id = fields.Many2one(  # noqa: E8529 -- the path employee_ids.company_id crosses an x2many: no single row to join
        comodel_name="res.company",
        related="employee_ids.company_id",
        store=True,
    )
    manager_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="hr_appraisal_goal_hr_employee_manager_rel",
        column1="hr_appraisal_goal_id",
        compute="_compute_manager_ids",
        store=True,
        readonly=False,
        tracking=True,
    )
    department_ids = fields.Many2many(
        comodel_name="hr.department",
        compute="_compute_department_ids",
        store=True,
    )
    job_ids = fields.Many2many(
        comodel_name="hr.job",
        compute="_compute_job_ids",
        store=True,
        groups="hr.group_hr_user",
    )
    progression = fields.Selection(
        selection=[
            ("000", "0%"),
            ("025", "25%"),
            ("050", "50%"),
            ("075", "75%"),
            ("100", "100%"),
        ],
        string="Progress",
        compute="_compute_progression",
        precompute=True,
        recursive=True,
        store=True,
        copy=False,
        readonly=False,
        required=True,
        tracking=True,
    )
    description = fields.Html()
    deadline = fields.Date(tracking=True)
    is_manager = fields.Boolean(
        compute="_compute_is_manager",
        search="_search_is_manager",
    )
    has_edit_right = fields.Boolean(compute="_compute_has_edit_right")
    tag_ids = fields.Many2many(
        comodel_name="hr.appraisal.goal.tag",
        string="Tags",
    )
    template_goal_id = fields.Many2one(
        comodel_name="hr.appraisal.goal",
        string="Goal Template",
    )
    number_of_sibling_goals = fields.Integer(
        compute="_compute_number_of_sibling_goals",
        store=True,
    )
    number_of_completed_sibling_goals = fields.Integer(
        compute="_compute_number_of_completed_sibling_goals",
        store=True,
    )
    sibling_goals_ratio = fields.Float(
        compute="_compute_sibling_goals_ratio",
        store=True,
    )
    active = fields.Boolean(default=True)
    parent_path = fields.Char(index=True)
    parent_id = fields.Many2one(
        comodel_name="hr.appraisal.goal",
        string="Parent Goal Template",
        index=True,
        domain=[("employee_ids", "=", False)],
    )
    child_ids = fields.One2many(
        comodel_name="hr.appraisal.goal",
        inverse_name="parent_id",
        string="Sub Goal Template",
    )
    usual_duration_month = fields.Integer(
        string="Usual Timing",
        help="The average timing for the goals to be completed. It will populate the estimated end date when assigned",
    )

    @api.depends_context("uid")
    def _compute_has_edit_right(self) -> None:
        for goal in self:
            goal.has_edit_right = goal.has_access("write")

    @api.constrains("employee_ids")
    def _check_employees_single_company(self) -> None:
        for goal in self:
            companies = goal.employee_ids.company_id
            if len(companies) > 1:
                raise ValidationError(
                    self.env._(
                        "A goal cannot be shared by employees of different "
                        "companies (%(companies)s). Create one goal per company.",
                        companies=", ".join(companies.mapped("name")),
                    )
                )

    @api.depends_context("uid")
    def _compute_employee_autocomplete(self) -> None:
        self.employee_autocomplete_ids = self.env.user.get_employee_autocomplete_ids()

    @api.depends_context("uid")
    @api.depends("employee_autocomplete_ids")
    def _compute_is_manager(self) -> None:
        self.is_manager = (
            self.env.user.has_group("hr_appraisal.group_hr_appraisal_user")
            or len(self.employee_autocomplete_ids) > 1
        )

    def _search_is_manager(self, operator, value):
        if operator != "in":
            return NotImplemented
        if self.env.user.has_group("hr_appraisal.group_hr_appraisal_user"):
            return Domain.TRUE
        return Domain(
            "employee_ids", "in", self.env.user.get_employee_autocomplete_ids().ids
        )

    @api.depends("employee_ids")
    def _compute_manager_ids(self) -> None:
        for goal in self:
            goal.manager_ids = goal.employee_ids.parent_id

    @api.depends("parent_id.child_ids")
    def _compute_number_of_sibling_goals(self) -> None:
        for goal in self:
            if not goal.parent_id:
                goal.number_of_sibling_goals = 0
            else:
                goal.number_of_sibling_goals = len(goal.parent_id.child_ids)

    @api.depends("parent_id.child_ids.progression")
    def _compute_number_of_completed_sibling_goals(self) -> None:
        for goal in self:
            if not goal.parent_id:
                goal.number_of_completed_sibling_goals = 0
            else:
                goal.number_of_completed_sibling_goals = len(
                    goal.parent_id.child_ids.filtered(
                        lambda goal: goal.progression == "100"
                    )
                )

    @api.depends("number_of_sibling_goals", "number_of_completed_sibling_goals")
    def _compute_sibling_goals_ratio(self) -> None:
        for goal in self:
            goal.sibling_goals_ratio = (
                100
                * goal.number_of_completed_sibling_goals
                / goal.number_of_sibling_goals
                if goal.number_of_sibling_goals
                else 0
            )

    @api.depends("child_ids.progression")
    def _compute_progression(self) -> None:
        for goal in self:
            if not goal.child_ids:
                goal.progression = goal.progression or "000"
                continue
            if all(goal_child.progression == "100" for goal_child in goal.child_ids):
                goal.progression = "100"
            else:
                goal.progression = "000"

    @api.depends("employee_ids.department_id")
    def _compute_department_ids(self) -> None:
        for goal in self:
            goal.department_ids = goal.employee_ids.department_id

    @api.depends("employee_ids.job_id")
    def _compute_job_ids(self) -> None:
        for goal in self:
            goal.job_ids = goal.employee_ids.job_id

    def _notify_by_email_prepare_rendering_context(
        self,
        message,
        msg_vals=False,
        model_description=False,
        force_email_company=False,
        force_email_lang=False,
        force_record_name=False,
        tracking_values=None,
    ):
        render_context = super()._notify_by_email_prepare_rendering_context(
            message,
            msg_vals=msg_vals,
            model_description=model_description,
            force_email_company=force_email_company,
            force_email_lang=force_email_lang,
            force_record_name=force_record_name,
            tracking_values=tracking_values,
        )
        if self.deadline:
            render_context["subtitles"].append(
                self.env._(
                    "Deadline: %s",
                    self.deadline.strftime(get_lang(self.env).date_format),
                )
            )
        return render_context

    def action_confirm(self):
        self.write({"progression": "100"})

    def create_goals(self, employee_ids=None, employee_goal_dict=None) -> None:
        if employee_goal_dict is None:
            employee_goal_dict = {}
        if employee_ids is None:
            employee_ids = []
        if not employee_ids and "default_employee_id" in self.env.context:
            employee_ids = [self.env.context["default_employee_id"]]
        if not employee_ids:
            return
        allowed = self.env.user.get_employee_autocomplete_ids().ids
        forbidden = [eid for eid in employee_ids if eid not in allowed]
        if forbidden:
            raise AccessError(
                self.env._(
                    "You cannot create goals for employees you do not manage: %s",
                    ", ".join(
                        self.env["hr.employee"].sudo().browse(forbidden).mapped("name")
                    ),
                )
            )
        employee_goals_values = []
        for goal in self:
            for employee_id in employee_ids:
                parent_id = False
                if goal.parent_id and employee_goal_dict.get(
                    (goal.parent_id.id, employee_id), False
                ):
                    parent_id = employee_goal_dict[goal.parent_id.id, employee_id].id
                employee_goals_values.append(
                    goal._prepare_goal_vals(employee_id, parent_id)
                )

        employee_goals = (
            self.env["hr.appraisal.goal"].sudo().create(employee_goals_values)
        )
        if self.child_ids:
            employee_goals_by_parent_template_by_employee = employee_goals.grouped(
                lambda goal: (goal.template_goal_id.id, goal.employee_ids.id)
            )
            self.child_ids.create_goals(
                employee_ids, employee_goals_by_parent_template_by_employee
            )

    def _prepare_goal_vals(self, employee_id, goal_parent_id) -> ValuesType:
        self.check_singleton()
        return {
            "name": self.name,
            "description": self.description,
            "tag_ids": self.tag_ids.ids,
            "deadline": fields.Date.today()
            + relativedelta(months=self.usual_duration_month)
            if self.usual_duration_month
            else False,
            "employee_ids": [employee_id],
            "parent_id": goal_parent_id,
            "template_goal_id": self.id,
        }

    def _get_duration_month(self):
        self.check_singleton()
        if not self.deadline or self.deadline <= self.create_date.date():
            return 0
        delta = relativedelta(self.deadline, self.create_date.date())
        return delta.years * 12 + delta.months

    def action_save_as_template(self):
        if any(goal.template_goal_id for goal in self):
            raise UserError(self.env._("A goal template already exist for this goal."))
        goal_templates = self.env["hr.appraisal.goal"].create(
            [
                {
                    "name": goal.name,
                    "description": goal.description,
                    "usual_duration_month": goal._get_duration_month(),
                    "tag_ids": goal.tag_ids,
                }
                for goal in self
            ]
        )
        for goal_template, goal in zip(goal_templates, self, strict=True):
            goal.template_goal_id = goal_template
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "hr_appraisal.action_hr_appraisal_goal_template"
        )
        if len(goal_templates.ids) == 1:
            action["view_mode"] = "form"
            action["views"] = [
                (
                    self.env.ref(
                        "hr_appraisal.hr_appraisal_goal_template_view_form"
                    ).id,
                    "form",
                )
            ]
            action["res_id"] = goal_templates.id
        action["domain"] = [("id", "in", goal_templates.ids)]
        return action

    def action_view_goal_template(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Goals"),
            "type": "ir.actions.act_window",
            "view_mode": "hierarchy,form",
            "res_model": "hr.appraisal.goal",
            "views": [
                (
                    self.env.ref("hr_appraisal.hr_appraisal_goal_view_hierarchy").id,
                    "hierarchy",
                ),
                (False, "form"),
            ],
            "domain": [("id", "=", self.id)],
        }

    @api.model
    def action_select_employees(self) -> dict:
        return {
            "name": self.env._("Select Employees"),
            "type": "ir.actions.act_window",
            "res_model": "hr.employee",
            "views": [
                [
                    self.env.ref(
                        "hr_appraisal.hr_employee_select_from_goal_view_list"
                    ).id,
                    "list",
                ],
            ],
            "domain": [("id", "in", self.env.user.get_employee_autocomplete_ids().ids)],
            "target": "new",
            "context": {"goals_ids": self.env.context.get("goals_ids")},
        }

    def action_archive(self):
        super().action_archive()
        if self.child_ids:
            self.child_ids.action_archive()

    def action_unarchive(self):
        super().action_unarchive()
        children = self.with_context(active_test=False).child_ids
        if children:
            children.action_unarchive()

    def copy_data(self, default=None):
        vals_list = super().copy_data(default)
        for goal, vals in zip(self, vals_list, strict=True):
            vals["name"] = self.env._("%s (copy)", goal.name)
            if goal.deadline and goal.deadline < fields.Date.today():
                vals["deadline"] = False
        return vals_list

    def copy(self, default=None):
        if not self.child_ids:
            return super().copy(default)
        list_of_goals_domain = [
            Domain.AND([Domain("id", "child_of", goal.id), Domain("id", "!=", goal.id)])
            for goal in self
        ]
        domain = Domain.OR(list_of_goals_domain)

        all_goal_children_ids = self.env["hr.appraisal.goal"].search(domain).ids
        if any(goal.id in all_goal_children_ids for goal in self):
            raise UserError(
                self.env._(
                    "You cannot duplicate at the same time a goal and one of its children.\n"
                    "Duplicating a goal will also duplicate its children."
                )
            )

        new_goal_templates = super().copy(default)
        res = self.child_ids.copy(default).grouped("parent_id")
        for old_goal_template, new_goal_template in zip(
            self, new_goal_templates, strict=True
        ):
            if res.get(old_goal_template):
                res[old_goal_template].parent_id = new_goal_template.id
        return new_goal_templates

    def recursive_unlink(self) -> None:
        children = self.with_context(active_test=False).child_ids
        if children:
            children.recursive_unlink()
        self.exists().unlink()
