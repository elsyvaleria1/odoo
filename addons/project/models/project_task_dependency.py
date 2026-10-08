from collections import defaultdict

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

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
        help="FS: B waits for A to finish (default). "
        "SS: B waits for A to start. "
        "FF: B cannot finish until A finishes. "
        "SF: B cannot finish until A starts.",
    )
    lag_hours = fields.Float(
        string="Lag (hours)",
        default=0.0,
        help="Delay after the dependency condition is met. Negative = lead time.",
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

    @_debug.perf.timed
    @api.constrains("task_id", "depends_on_id")
    def _check_no_cyclic_dependencies(self) -> None:
        self.flush_model(["task_id", "depends_on_id"])
        starts = [dep.task_id.id for dep in self]
        targets = [dep.depends_on_id.id for dep in self]
        if not starts:
            return
        self.env.cr.execute(
            """
            WITH RECURSIVE reachable(source, id) AS (
                    SELECT d.depends_on_id, d.task_id
                      FROM project_task_dependency d
                     WHERE d.depends_on_id = ANY(%(starts)s)
                 UNION
                    SELECT r.source, d.task_id
                      FROM project_task_dependency d
                      JOIN reachable r ON d.depends_on_id = r.id
            )
            SELECT 1
              FROM reachable r
              JOIN unnest(%(starts)s::integer[], %(targets)s::integer[])
                     AS edge(start_id, target_id)
                ON r.source = edge.start_id AND r.id = edge.target_id
             LIMIT 1
            """,
            {"starts": starts, "targets": targets},
        )
        if self.env.cr.fetchone():
            raise ValidationError(
                self.env._("Adding this dependency would create a circular reference.")
            )

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
        _debug.pipeline("m2m_sync_requested", dependencies=records)
        records._sync_to_m2m()
        return records

    @_debug.perf.timed
    def write(self, vals: dict) -> bool:
        remap = "task_id" in vals or "depends_on_id" in vals
        _debug.lifecycle("write", dependencies=self, keys=sorted(vals), remap=remap)
        old_pairs = [(dep.task_id, dep.depends_on_id) for dep in self] if remap else []
        res = super().write(vals)
        if remap:
            for (old_task, old_pred), dep in zip(old_pairs, self, strict=True):
                if dep.task_id == old_task and dep.depends_on_id == old_pred:
                    continue
                _debug.logic(
                    "dependency_remapped",
                    dependency=dep,
                    old_task=old_task.id,
                    old_predecessor=old_pred.id,
                    task=dep.task_id.id,
                    predecessor=dep.depends_on_id.id,
                )
                if old_pred in old_task.predecessor_ids:
                    old_task.with_context(skip_dependency_sync=True).write(
                        {"predecessor_ids": [fields.Command.unlink(old_pred.id)]}
                    )
                dep._sync_to_m2m()
        return res

    @_debug.perf.timed
    def unlink(self) -> bool:
        preds_by_task = defaultdict(lambda: self.env["project.task"])
        for dep in self:
            preds_by_task[dep.task_id] |= dep.depends_on_id
        _debug.lifecycle("unlink", dependencies=self, tasks=len(preds_by_task))
        for task, preds in preds_by_task.items():
            task.with_context(skip_dependency_sync=True).write(
                {"predecessor_ids": [fields.Command.unlink(p.id) for p in preds]}
            )
        return super().unlink()

    def _sync_to_m2m(self) -> None:
        new_pairs = set()
        for dep in self:
            if dep.depends_on_id not in dep.task_id.predecessor_ids:
                new_pairs.add((dep.task_id.id, dep.depends_on_id.id))
        _debug.logic("m2m_pairs_missing", dependencies=self, pairs=len(new_pairs))
        if not new_pairs:
            return

        Task = self.env["project.task"]
        field = Task._fields["predecessor_ids"]
        pairs = sorted(new_pairs)
        self.env.cr.execute(
            SQL(
                "INSERT INTO %s (%s, %s) "
                "SELECT * FROM unnest(%s::integer[], %s::integer[]) "
                "ON CONFLICT DO NOTHING",
                SQL.identifier(field.relation),
                SQL.identifier(field.column1),
                SQL.identifier(field.column2),
                [task_id for task_id, _pred in pairs],
                [pred for _task, pred in pairs],
            )
        )
        tasks = Task.browse({task_id for task_id, _pred in new_pairs})
        predecessors = Task.browse({pred for _task, pred in new_pairs})
        tasks.invalidate_recordset(["predecessor_ids"])
        (tasks | predecessors).invalidate_recordset(["successor_ids"])
        tasks.modified(["predecessor_ids"])
        predecessors.modified(["successor_ids"])
        tasks._check_no_cyclic_dependencies()
