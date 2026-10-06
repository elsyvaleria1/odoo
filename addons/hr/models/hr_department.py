from collections import defaultdict

from odoo import _lt, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrDepartment(models.Model):
    _name = "hr.department"
    _description = "Department"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity", "mixin.hierarchy"]
    _order = "complete_name"
    _rec_name = "complete_name"

    name = fields.Char(
        string="Department Name",
        translate=True,
        required=True,
    )
    complete_name = fields.Char(
        compute="_compute_complete_name",
        recursive=True,
        store=True,
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        precompute=True,
        recursive=True,
        store=True,
        index=True,
        readonly=False,
        tracking=True,
    )
    parent_id = fields.Many2one(
        comodel_name="hr.department",
        string="Parent Department",
        index=True,
        check_company=True,
    )
    child_ids = fields.One2many(
        comodel_name="hr.department",
        inverse_name="parent_id",
        string="Child Departments",
    )
    manager_id = fields.Many2one(
        comodel_name="hr.employee",
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        tracking=True,
    )
    member_ids = fields.One2many(
        comodel_name="hr.employee",
        inverse_name="department_id",
        string="Members",
        readonly=True,
    )
    has_read_access = fields.Boolean(
        export_string_translation=False,
        search="_search_has_read_access",
        store=False,
    )
    total_employee = fields.Integer(
        export_string_translation=False,
        compute="_compute_total_employee",
    )
    jobs_ids = fields.One2many(
        comodel_name="hr.job",
        inverse_name="department_id",
    )
    plan_ids = fields.One2many(
        comodel_name="mail.activity.plan",
        inverse_name="department_id",
    )
    plans_count = fields.Integer(compute="_compute_plans_count")
    note = fields.Text()
    color = fields.Integer(string="Color Index")
    master_department_id = fields.Many2one(
        comodel_name="hr.department",
        compute="_compute_master_department_id",
        store=True,
    )

    @api.depends_context("hierarchical_naming")
    def _compute_display_name(self):
        if self.env.context.get("hierarchical_naming", True):
            return super()._compute_display_name()
        for record in self:
            record.display_name = record.name
        return None

    def _search_has_read_access(self, operator, value):
        if operator != "in":
            return NotImplemented
        if self.env["hr.employee"].has_access("read"):
            _debug.logic("read_access", mode="hr_reader")
            return [(1, "=", 1)]
        departments_ids = (
            self.env["hr.department"]
            .sudo()
            .search([("manager_id", "in", self.env.user.employee_ids.ids)])
            .ids
        )
        _debug.logic(
            "read_access", mode="manager", uid=self.env.uid, departments=departments_ids
        )
        return [("id", "child_of", departments_ids)]

    @api.model
    def name_create(self, name):
        record = self.create({"name": name})
        return record.id, record.display_name

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self) -> None:
        for department in self:
            if department.parent_id:
                department.complete_name = "%s / %s" % (
                    department.parent_id.complete_name,
                    department.name,
                )
            else:
                department.complete_name = department.name

    @api.depends("parent_path")
    def _compute_master_department_id(self) -> None:
        for dept in self:
            dept.master_department_id = dept._get_root()

    @api.depends_context("allowed_company_ids")
    @api.constrains("company_id")
    def _check_members_are_of_this_company(self) -> None:
        scoped = self.filtered("company_id")
        if not scoped:
            return
        # One search for the whole batch, and a search rather than member_ids:
        # the employee writes that put them here may still be pending in the
        # same flush, and the one2many cache would then report none.
        members = (
            self.env["hr.employee"]
            .sudo()
            .search([("department_id", "in", scoped.ids), ("company_id", "!=", False)])
        )
        empty = self.env["hr.employee"].sudo()
        by_department = defaultdict(empty.browse)
        for member in members:
            by_department[member.department_id.id] |= member
        _debug.logic(
            "members_company_checked", departments=scoped, members=len(members)
        )
        for department in scoped:
            stranded = by_department[department.id].filtered_domain(
                [("company_id", "!=", department.company_id.id)]
            )
            if stranded:
                raise ValidationError(
                    self.env._(
                        "%(department)s cannot move to %(company)s while it "
                        "holds %(employees)s of another company.",
                        department=department.display_name,
                        company=department.company_id.display_name,
                        employees=", ".join(stranded.mapped("name")),
                    )
                )

    @_debug.perf.timed
    @api.depends("member_ids")
    def _compute_total_employee(self) -> None:
        emp_data = (
            self.env["hr.employee"]
            .sudo()
            ._read_group(
                [
                    ("department_id", "in", self.ids),
                    ("company_id", "in", self.env.companies.ids),
                ],
                ["department_id"],
                ["__count"],
            )
        )
        result = {department.id: count for department, count in emp_data}
        for department in self:
            department.total_employee = result.get(department.id, 0)

    @api.depends_context("allowed_company_ids")
    @api.depends("plan_ids")
    def _compute_plans_count(self) -> None:
        plans_data = self.env["mail.activity.plan"]._read_group(
            domain=[
                "|",
                ("department_id", "=", False),
                ("department_id", "in", self.ids),
                ("company_id", "in", self.env.companies.ids + [False]),
            ],
            groupby=["department_id"],
            aggregates=["__count"],
        )
        plans_count = {department.id: count for department, count in plans_data}
        for department in self:
            department.plans_count = plans_count.get(
                department.id, 0
            ) + plans_count.get(False, 0)

    _hierarchy_cycle_message = _lt("You cannot create recursive departments.")

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                count=len(vals_list),
                keys=sorted({k for vals in vals_list for k in vals}),
            )
        departments = super(
            HrDepartment, self.with_context(mail_create_nosubscribe=True)
        ).create(vals_list)
        _debug.lifecycle("created", departments=departments)
        return departments

    @api.depends("parent_id", "parent_id.company_id")
    def _compute_company_id(self):
        for dept in self:
            company = dept.parent_id.company_id or dept.company_id
            if not company and not dept._origin:
                company = self.env.company
                _debug.logic("company_defaulted", company=company.id)
            dept.company_id = company

    @_debug.perf.timed
    def write(self, vals):
        _debug.lifecycle("write", departments=self, keys=sorted(vals))
        if "manager_id" in vals:
            new_manager_id = vals.get("manager_id")
            self._update_employee_manager(new_manager_id)
        return super().write(vals)

    @_debug.perf.timed
    def _update_employee_manager(self, new_manager_id) -> None:
        department_employees = self.env["hr.employee"].search(
            [
                ("id", "!=", new_manager_id),
                ("department_id", "in", self.ids),
            ]
        )
        outgoing_manager_per_department = {
            department: department.manager_id for department in self
        }
        employees = department_employees.filtered(
            lambda employee: (
                employee.parent_id
                == outgoing_manager_per_department.get(employee.department_id)
            )
        )
        _debug.pipeline(
            "manager_changed",
            departments=self,
            manager=new_manager_id,
            followers=len(employees),
            members=len(department_employees),
            employees=employees,
        )
        employees.write({"parent_id": new_manager_id})

    def get_formview_action(self, access_uid=None):
        res = super().get_formview_action(access_uid=access_uid)
        if not self.env.user.has_group("hr.group_hr_user") and self.env.context.get(
            "open_employees_kanban", False
        ):
            _debug.logic("form_redirected_to_employees", department=self.id)
            res.update(
                {
                    "name": self.name,
                    "res_model": "hr.employee",
                    "view_mode": "kanban",
                    "views": [(False, "kanban"), (False, "form")],
                    "context": {"searchpanel_default_department_id": self.id},
                    "res_id": False,
                }
            )
        return res

    def action_plan_from_department(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr.mail_activity_plan_action"
        )
        action["context"] = dict(
            self.env["ir.actions.actions"]._eval_action_context(action.get("context")),
            default_department_id=self.id,
        )
        domain = [
            "|",
            ("department_id", "=", False),
            ("department_id", "in", self.ids),
        ]
        if "domain" in action:
            action["domain"] = Domain.AND(
                [
                    self.env["ir.actions.actions"]._eval_action_domain(
                        action["domain"],
                        allowed_company_ids=self.env.context.get(
                            "allowed_company_ids", []
                        ),
                    ),
                    domain,
                ]
            )
        else:
            action["domain"] = domain
        if self.plans_count == 0:
            action["views"] = [(False, "form")]
        _debug.logic(
            "plan_action",
            department=self.id,
            plans=self.plans_count,
            domain=action["domain"],
        )
        return action

    def action_employee_from_department(self) -> dict:
        return {
            "name": self.env._("Employees"),
            "type": "ir.actions.act_window",
            "res_model": "hr.employee",
            "view_mode": "list,kanban,form",
            "views": [(False, "list"), (False, "kanban"), (False, "form")],
            "search_view_id": [self.env.ref("hr.view_employee_filter").id, "search"],
            "context": {
                "searchpanel_default_department_id": self.id,
                "default_department_id": self.id,
                "search_default_group_department": 1,
                "search_default_department_id": self.id,
                "expand": 1,
            },
        }

    def _get_child_departments(self):
        return self.env["hr.department"].search([("id", "child_of", self.ids)])

    def action_view_child_departments(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.department",
            "views": [[False, "kanban"], [False, "list"], [False, "form"]],
            "domain": [["id", "in", self._get_child_departments().ids]],
            "name": self.env._("Child departments"),
        }

    def get_department_hierarchy(self) -> dict:
        if not self:
            return {}
        self.check_singleton()

        return {
            "parent": {
                "id": self.parent_id.id,
                "name": self.parent_id.name,
                "employees": self.parent_id.total_employee,
            }
            if self.parent_id
            else False,
            "self": {
                "id": self.id,
                "name": self.name,
                "employees": self.total_employee,
            },
            "children": [
                {"id": child.id, "name": child.name, "employees": child.total_employee}
                for child in self.child_ids
            ],
        }
