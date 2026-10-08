from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

from .project_task import (
    CLOSED_STATES,
    FINISH_ANCHORED_TYPES,
    START_CONSTRAINED_TYPES,
    UNSTARTED_STATES,
)

_debug = DebugLog(__name__)


class ProjectTaskDependency(models.Model):
    _name = "project.task.dependency"
    _access_anchors = frozendict({"company": "project_id.company_id"})
    _description = "Task Dependency"
    _order = "id"
    _rec_name = "display_name"

    task_id = fields.Many2one(
        comodel_name="project.task",
        string="Dependent Task",
        index=True,
        required=True,
        ondelete="cascade",
        help="The task that is blocked or constrained.",
    )
    depends_on_id = fields.Many2one(
        comodel_name="project.task",
        string="Predecessor Task",
        index=True,
        required=True,
        ondelete="cascade",
        help="The task that must complete (or start) first.",
    )
    dependency_type = fields.Selection(
        selection=[
            ("fs", "Finish-to-Start"),
            ("ss", "Start-to-Start"),
            ("ff", "Finish-to-Finish"),
            ("sf", "Start-to-Finish"),
        ],
        string="Type",
        default="fs",
        required=True,
        help="FS: B cannot start until A is closed, nor be planned to start before "
        "A ends. "
        "SS: B cannot start until A has started, nor be planned to start before A "
        "starts. "
        "FF: B cannot be done until A is closed, nor be planned to end before A "
        "ends. "
        "SF: B cannot be done until A has started, nor be planned to end before A "
        "starts.",
    )
    lag_hours = fields.Float(
        string="Lag (hours)",
        default=0.0,
        required=True,
        help="Calendar hours added to the predecessor date the dependency reads. "
        "Negative = lead time.",
    )
    project_id = fields.Many2one(
        related="task_id.project_id",
    )

    _unique_dependency = models.Constraint(
        "UNIQUE(task_id, depends_on_id)",
        "A dependency between these two tasks already exists.",
    )
    _no_self_dependency = models.Constraint(
        "CHECK(task_id != depends_on_id)",
        "A task cannot depend on itself.",
    )

    @api.depends("task_id", "depends_on_id", "dependency_type")
    def _compute_display_name(self) -> None:
        type_labels = dict(self._fields["dependency_type"].selection)
        for dep in self:
            dep.display_name = (
                f"{dep.depends_on_id.display_name} -> "
                f"{dep.task_id.display_name} "
                f"({type_labels.get(dep.dependency_type, 'FS')})"
            )

    @api.constrains("task_id", "depends_on_id")
    def _check_no_cyclic_dependencies(self) -> None:
        self.flush_recordset(["task_id", "depends_on_id"])
        self.task_id._check_no_cyclic_dependencies()

    def _is_start_blocking(self) -> bool:
        self.check_singleton()
        state = self.depends_on_id.state
        if self.dependency_type == "fs":
            return state not in CLOSED_STATES
        if self.dependency_type == "ss":
            return state in UNSTARTED_STATES
        return False

    def _is_finish_blocking(self) -> bool:
        self.check_singleton()
        state = self.depends_on_id.state
        if self.dependency_type == "ff":
            return state not in CLOSED_STATES
        if self.dependency_type == "sf":
            return state in UNSTARTED_STATES
        return False

    def _get_constrained_date_field(self) -> str:
        self.check_singleton()
        if self.dependency_type in START_CONSTRAINED_TYPES:
            return "date_start"
        return "date_end"

    def _get_date_bound(self) -> datetime | None:
        self.check_singleton()
        predecessor = self.depends_on_id
        anchor = (
            predecessor.date_end
            if self.dependency_type in FINISH_ANCHORED_TYPES
            else predecessor.date_start
        )
        if not anchor:
            return None
        return anchor + timedelta(hours=self.lag_hours)

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> ProjectTaskDependency:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                count=len(vals_list),
                keys=sorted({k for vals in vals_list for k in vals}),
            )
        records = super().create(vals_list)
        records.task_id._invalidate_dependency_links(records.depends_on_id)
        return records

    @_debug.perf.timed
    def write(self, vals: dict) -> bool:
        remap = "task_id" in vals or "depends_on_id" in vals
        _debug.lifecycle("write", dependencies=self, keys=sorted(vals), remap=remap)
        if not remap:
            return super().write(vals)
        old_tasks, old_predecessors = self.task_id, self.depends_on_id
        res = super().write(vals)
        self.flush_recordset(["task_id", "depends_on_id"])
        _debug.logic(
            "dependency_remapped",
            dependencies=self,
            tasks=self.task_id,
            predecessors=self.depends_on_id,
        )
        (old_tasks | self.task_id)._invalidate_dependency_links(
            old_predecessors | self.depends_on_id
        )
        return res

    @_debug.perf.timed
    def unlink(self) -> bool:
        tasks, predecessors = self.task_id, self.depends_on_id
        _debug.lifecycle("unlink", dependencies=self, tasks=tasks)
        res = super().unlink()
        tasks._invalidate_dependency_links(predecessors)
        return res
