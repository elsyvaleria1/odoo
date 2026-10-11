from collections import defaultdict

from odoo import api, fields, models
from odoo.fields import Domain


class ProjectTask(models.Model):
    _name = "project.task"
    _inherit = "project.task"

    leave_warning = fields.Char(
        export_string_translation=False,
        compute="_compute_leave_warning",
        compute_sudo=True,
    )
    is_absent = fields.Boolean(
        string="Employees on Time Off",
        export_string_translation=False,
        compute="_compute_leave_warning",
        search="_search_is_absent",
        compute_sudo=True,
        readonly=True,
    )

    @api.depends_context("lang")
    @api.depends("date_start", "date_end", "user_ids", "project_id", "is_closed")
    def _compute_leave_warning(self):
        def group_by_leave(data):
            mapping_leaves = defaultdict(list)
            for item in data:
                name = item["name"]
                for leave in item["leaves"]:
                    leave_tuple = tuple(leave.items())
                    mapping_leaves[leave_tuple].append(name)
            res = []
            for leave_tuple, names in mapping_leaves.items():
                leave_dict = dict(leave_tuple)
                res.append({"names": names, "leaves": leave_dict})
            return res

        tasks = self.with_context(prefetch_fields=False)

        if all(self._ids):
            tasks = tasks.browse(self.ids)
            tasks.fetch(
                [
                    "user_ids",
                    "project_id",
                    "date_start",
                    "date_end",
                    "is_closed",
                ]
            )

        assigned_tasks = tasks.filtered(
            lambda t: (
                t.user_ids._origin.employee_ids
                and t.project_id
                and t.date_start
                and t.date_end
                and not t.is_closed
            )
        )
        (self - assigned_tasks).leave_warning = False
        (self - assigned_tasks).is_absent = False

        if not assigned_tasks:
            return None

        min_date = min(assigned_tasks.mapped("date_start"))
        date_from = max(fields.Datetime.today(), min_date)
        leaves = self.env["hr.leave"]._get_leave_interval(
            date_from=date_from,
            date_to=max(assigned_tasks.mapped("date_end")),
            employee_ids=assigned_tasks.user_ids._origin.employee_ids,
        )

        for task in assigned_tasks:
            leaves_parameters = {"validated": [], "requested": []}
            for employee in task.user_ids._origin.employee_ids:
                task_leaves = leaves.get(employee.id)
                if task_leaves:
                    employee_leaves = self.env[
                        "hr.leave"
                    ]._get_leave_warning_parameters(
                        task_leaves, employee, task.date_start, task.date_end
                    )
                    for leave_type, leaves_for_employee in employee_leaves.items():
                        if not leaves_for_employee:
                            continue
                        leaves_parameters[leave_type].append(leaves_for_employee)
            for leave_type, leaves_for_employee in leaves_parameters.items():
                leaves_parameters[leave_type] = group_by_leave(leaves_for_employee)
            warning = ""
            for leave_type, leaves_for_employee in leaves_parameters.items():
                for leave in leaves_for_employee:
                    if leave["leaves"]:
                        if leave_type == "validated":
                            if len(leave["names"]) == 1:
                                warning += self.env._(
                                    "%(names)s is on time off %(leaves)s. \n",
                                    names=leave["names"][0],
                                    leaves=self.env[
                                        "hr.leave"
                                    ].format_date_range_to_string(leave["leaves"]),
                                )
                            else:
                                warning += self.env._(
                                    "%(names)s are on time off %(leaves)s. \n",
                                    names=leave["names"],
                                    leaves=self.env[
                                        "hr.leave"
                                    ].format_date_range_to_string(leave["leaves"]),
                                )
                        else:
                            warning += self.env._(
                                "%(names)s requested time off %(leaves)s. \n",
                                names=leave["names"],
                                leaves=self.env["hr.leave"].format_date_range_to_string(
                                    leave["leaves"]
                                ),
                            )
            task.leave_warning = warning or False
            task.is_absent = bool(warning)
        return warning

    @api.model
    def _search_is_absent(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented

        tasks = self.search(
            [
                ("user_ids.employee_id", "!=", False),
                ("project_id", "!=", False),
                ("date_start", "!=", False),
                ("date_end", "!=", False),
                ("is_closed", "=", False),
            ]
        )
        if not tasks:
            return Domain(operator != "in")

        min_date = min(tasks.mapped("date_start"))
        date_from = max(fields.Datetime.today(), min_date)
        mapped_leaves = self.env["hr.leave"]._get_leave_interval(
            date_from=date_from,
            date_to=max(tasks.mapped("date_end")),
            employee_ids=tasks.user_ids.employee_ids,
        )
        task_ids = []
        for task in tasks:
            employees = tasks.user_ids.employee_ids
            for employee in employees:
                if employee.id in mapped_leaves:
                    leaves = mapped_leaves[employee.id]
                    period = self.env["hr.leave"]._group_leaves(
                        leaves, employee, task.date_start, task.date_end
                    )
                    if period:
                        task_ids.append(task.id)
        return [("id", operator, task_ids)]
