from odoo import api, fields, models
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog
from odoo.tools import LazyTranslate

_lt = LazyTranslate(__name__)
_debug = DebugLog(__name__)

ASSIGNEE_FIELDS = frozenset({"employee_ids", "direct_user_ids"})


class ProjectTask(models.Model):
    _name = "project.task"
    _inherit = ["mixin.hr", "project.task"]

    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="project_task_employee_rel",
        column1="task_id",
        column2="employee_id",
        string="Assignees",
        default=lambda self: self._default_employee_ids(),
        falsy_value_label=_lt("👤 Unassigned"),
        context={"active_test": False},
        tracking=True,
    )

    direct_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="project_task_direct_user_rel",
        column1="task_id",
        column2="user_id",
        string="Assignees without Employee",
        context={"active_test": False},
        tracking=True,
    )
    user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="project_task_user_rel",
        column1="task_id",
        column2="user_id",
        string="Assignees (Users)",
        compute="_compute_user_ids",
        default=None,
        store=True,
        readonly=False,
        tracking=False,
    )

    def _get_fields_assignment(self) -> set[str]:
        return super()._get_fields_assignment() | {"employee_ids", "direct_user_ids"}

    def _filter_active_assignees(self, assignees):
        assignees = super()._filter_active_assignees(assignees)
        if assignees._name != "hr.employee":
            return assignees
        return assignees.filtered(
            lambda employee: not employee.user_id or employee.user_id.active
        )

    @api.model
    def _prepare_assignment_vals(self, users):
        return self._assignee_commands_for_users(users, self.env.company)

    def _get_assigned_users(self, values):
        users = super()._get_assigned_users(values)
        for fname, comodel in (
            ("employee_ids", "hr.employee"),
            ("direct_user_ids", "res.users"),
        ):
            if fname not in values:
                continue
            records = self.env[comodel].browse(
                self._fields[fname].convert_to_cache(
                    values[fname], self.env["project.task"], validate=False
                )
            )
            users |= records if comodel == "res.users" else records.exists().user_id
        return users

    @api.model
    def _default_employee_ids(self):
        if any(
            key in self.env.context
            for key in (
                "default_triage_ids",
                "default_triage_id",
            )
        ):
            return self.env["hr.employee"].search(
                [
                    ("user_id", "=", self.env.uid),
                    ("company_id", "=", self.env.company.id),
                ],
                limit=1,
            )
        return self.env["hr.employee"]

    @api.depends("employee_ids.user_id", "direct_user_ids")
    def _compute_user_ids(self) -> None:
        for task in self:
            _debug.logic(
                "task_user_ids_composed",
                task=task,
                employees=task.employee_ids,
                from_employees=task.employee_ids.user_id,
                direct=task.direct_user_ids,
            )
            task.user_ids = task.employee_ids.user_id | task.direct_user_ids

    @api.model
    def _get_user_commands(self, value) -> list:
        if isinstance(value, models.BaseModel):
            return [Command.set(value.ids)]
        if value is False or value is None:
            return [Command.clear()]
        if not value:
            # an empty command list, as the ORM reads it: nothing changes
            return []
        if all(isinstance(item, int) for item in value):
            # a bare id list, as the ORM reads it: a falsy id names nobody
            return [Command.set([item for item in value if item])]
        return list(value)

    @api.model
    def _get_user_commands_against(self, commands, users) -> list:
        # Employees without a user never show in user_ids, so replacing the
        # users must not replace them: a set or a clear becomes the users it
        # removes and adds, which leaves every other assignee where it is.
        current = dict.fromkeys(users.ids)
        result = dict(current)
        for command in commands:
            match command[0]:
                case Command.SET:
                    result = dict.fromkeys(command[2])
                case Command.CLEAR:
                    result = {}
                case Command.LINK:
                    result[command[1]] = None
                case Command.UNLINK:
                    result.pop(command[1], None)
        return [
            *(Command.unlink(user_id) for user_id in current if user_id not in result),
            *(Command.link(user_id) for user_id in result if user_id not in current),
        ]

    def _assignee_commands_for_users(self, value, company) -> dict:
        commands = self._get_user_commands(value)
        user_ids = {
            user_id
            for command in commands
            for user_id in (
                command[2]
                if command[0] == Command.SET
                else [command[1]]
                if command[0] in (Command.LINK, Command.UNLINK)
                else []
            )
        }
        employees_by_user = (
            self.env["hr.employee"]
            .sudo()
            .search([("user_id", "in", list(user_ids))])
            .grouped("user_id")
        )

        def employees_of(user_id):
            return employees_by_user.get(
                self.env["res.users"].browse(user_id), self.env["hr.employee"]
            )

        def assignee(user_id):
            # another company's employee is never borrowed: without one in
            # the task's company the user is assigned directly
            return employees_of(user_id).filtered(
                lambda employee: employee.company_id == company
            )[:1]

        _debug.pipeline(
            "task_assignees_mapped",
            company=company,
            commands=len(commands),
            users=len(user_ids),
            users_with_employee=len(employees_by_user),
        )
        employee_commands = []
        direct_commands = []
        for command in commands:
            match command[0]:
                case Command.SET:
                    employee_commands.append(
                        Command.set(
                            [
                                employee.id
                                for user_id in command[2]
                                for employee in assignee(user_id)
                            ]
                        )
                    )
                    direct_commands.append(
                        Command.set(
                            [user_id for user_id in command[2] if not assignee(user_id)]
                        )
                    )
                case Command.LINK:
                    if employee := assignee(command[1]):
                        employee_commands.append(Command.link(employee.id))
                    else:
                        _debug.logic(
                            "task_assignee_kept_as_user",
                            reason="no_employee_for_user",
                            user_id=command[1],
                            company=company,
                        )
                        direct_commands.append(Command.link(command[1]))
                case Command.UNLINK:
                    employee_commands += [
                        Command.unlink(employee.id)
                        for employee in employees_of(command[1])
                    ]
                    direct_commands.append(Command.unlink(command[1]))
                case Command.CLEAR:
                    employee_commands.append(Command.clear())
                    direct_commands.append(Command.clear())
        _debug.logic(
            "task_assignee_commands_built",
            company=company,
            employee_commands=len(employee_commands),
            direct_commands=len(direct_commands),
        )
        return {"employee_ids": employee_commands, "direct_user_ids": direct_commands}

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        if "user_ids" not in defaults or not ASSIGNEE_FIELDS.issubset(fields):
            return defaults
        user_value = defaults.pop("user_ids")
        _debug.logic("task_default_users_composed", users=user_value)
        for fname, commands in self._assignee_commands_for_users(
            user_value, self.env.company
        ).items():
            if f"default_{fname}" not in self.env.context:
                defaults[fname] = commands
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        context = self.env.context
        for vals in vals_list:
            if "user_ids" in vals:
                user_value = vals.pop("user_ids")
            elif "default_user_ids" in context:
                user_value = context["default_user_ids"]
            else:
                continue
            if vals.keys() & ASSIGNEE_FIELDS:
                _debug.logic(
                    "task_user_ids_dropped",
                    reason="assignees_given_explicitly",
                    on="create",
                )
                continue
            company = (
                self.env["res.company"].browse(vals["company_id"])
                if vals.get("company_id")
                else self.env["project.project"]
                .browse(vals.get("project_id"))
                .company_id
                or self.env.company
            )
            vals.update(self._assignee_commands_for_users(user_value, company))
        # a context default lands on user_ids as a value of its own, which a
        # computed field that is not readonly keeps instead of composing
        without_default = self.with_context(
            {key: value for key, value in context.items() if key != "default_user_ids"}
        )
        tasks = super(ProjectTask, without_default).create(vals_list).with_env(self.env)
        now = fields.Datetime.now()
        for task in tasks:
            if task.employee_ids and not task.date_assign:
                _debug.lifecycle(
                    "task_date_assign_set",
                    trigger="created_with_assignees",
                    task=task,
                    employees=task.employee_ids,
                )
                task.sudo().date_assign = now
        return tasks

    def _prepare_reservation_vals_list(self):
        self.check_singleton()
        start_field, end_field = self._get_fields_reservation_date()
        if not start_field or not end_field:
            _debug.logic(
                "task_reservation_skipped",
                reason="model_declares_no_reservation_dates",
                task=self,
            )
            return []
        date_start = self[start_field]
        date_end = self[end_field]
        if not date_start or not date_end:
            _debug.logic(
                "task_reservation_skipped",
                reason="dates_not_set",
                task=self,
                date_start=date_start,
                date_end=date_end,
            )
            return []

        vals_list = []
        for employee in self.employee_ids:
            resource = employee.resource_id
            if not resource:
                _debug.logic(
                    "task_reservation_skipped",
                    reason="employee_has_no_resource",
                    task=self,
                    employee=employee,
                )
                continue
            vals_list.append(
                {
                    "name": self.display_name,
                    "date_start": date_start,
                    "date_end": date_end,
                    "resource_id": resource.id,
                    "allocated_percentage": self.allocated_percentage or 100.0,
                    "enforcement_mode": "soft",
                }
            )
        _debug.pipeline(
            "task_reservations_prepared",
            task=self,
            employees=self.employee_ids,
            reservations=len(vals_list),
            date_start=date_start,
            date_end=date_end,
        )
        return vals_list

    def _get_fields_sync_trigger(self):
        triggers = super()._get_fields_sync_trigger()
        triggers.discard("user_ids")
        triggers.add("employee_ids")
        return triggers

    def action_view_schedule(self) -> dict:
        self.check_singleton()
        resources = self.employee_ids.resource_id

        if len(resources) == 1:
            action_name = self.env._("Schedule — %s", resources.name)
        elif resources:
            action_name = self.env._("Schedule — %s assignees", len(resources))
        else:
            action_name = self.env._("Schedule")

        context = {"search_default_my_schedule": 0}
        start_field, end_field = self._get_fields_reservation_date()
        anchor = (start_field and self[start_field]) or (end_field and self[end_field])
        if anchor:
            context["initial_date"] = anchor

        return {
            "type": "ir.actions.act_window",
            "name": action_name,
            "res_model": "resource.reservation",
            "view_mode": "calendar,list,form",
            "domain": [("resource_id", "in", resources.ids)],
            "context": context,
        }

    def write(self, vals):
        if "user_ids" in vals:
            # the caller's dict stays theirs: web_gantt_write reuses it per batch
            vals = dict(vals)
            user_value = vals.pop("user_ids")
            if not vals.keys() & ASSIGNEE_FIELDS:
                commands = self._get_user_commands(user_value)
                replaces = any(
                    command[0] in (Command.SET, Command.CLEAR) for command in commands
                )
                groups = self.grouped(
                    (lambda task: (task.company_id, task.user_ids))
                    if replaces
                    else "company_id"
                )
                if len(groups) > 1:
                    _debug.logic(
                        "task_assignees_split",
                        tasks=self,
                        companies=self.company_id,
                        by_current_users=replaces,
                        groups=len(groups),
                    )
                    for tasks in groups.values():
                        tasks.write({**vals, "user_ids": commands})
                    return True
                if replaces:
                    commands = self._get_user_commands_against(commands, self.user_ids)
                    _debug.logic(
                        "task_user_replacement_rebased",
                        tasks=self,
                        users=self.user_ids,
                        commands=len(commands),
                    )
                vals.update(
                    self._assignee_commands_for_users(
                        commands, self.company_id or self.env.company
                    )
                )
        now = fields.Datetime.now()
        dates_assign = {}
        if "employee_ids" in vals and "date_assign" not in vals:
            dates_assign = {task.id: task.date_assign for task in self}

        result = super().write(vals)

        if "employee_ids" in vals:
            self._create_missing_triages()
            for task in self.sudo():
                if not (task.employee_ids or task.direct_user_ids):
                    if task.date_assign:
                        _debug.lifecycle(
                            "task_date_assign_cleared",
                            trigger="last_assignee_removed",
                            task=task,
                        )
                        task.date_assign = False
                elif task.id in dates_assign and not task.date_assign:
                    # project clears the date once no user is left, which an
                    # employee without a user does not count as
                    _debug.lifecycle(
                        "task_date_assign_set",
                        trigger=(
                            "assignee_without_user_kept"
                            if dates_assign[task.id]
                            else "first_assignee_added"
                        ),
                        task=task,
                        employees=task.employee_ids,
                    )
                    task.date_assign = dates_assign[task.id] or now

        return result
