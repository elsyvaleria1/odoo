from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)


class ProjectBaseline(models.Model):
    _name = "project.baseline"
    _access_anchors = frozendict({"company": "project_id.company_id"})
    _description = "Project Baseline"
    _order = "date_created desc, id desc"

    name = fields.Char(
        string="Baseline Name",
        required=True,
        help="e.g. 'Original Plan', 'Replan v2'.",
    )
    project_id = fields.Many2one(
        comodel_name="project.project",
        index=True,
        required=True,
        ondelete="cascade",
    )
    date_created = fields.Datetime(
        string="Created On",
        default=fields.Datetime.now,
        readonly=True,
    )
    created_by_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.user,
        readonly=True,
    )
    is_current = fields.Boolean(
        string="Current Baseline",
        default=False,
        copy=False,
        help="Only one baseline per project can be marked as current.",
    )
    line_ids = fields.One2many(
        comodel_name="project.baseline.line",
        inverse_name="baseline_id",
        string="Baseline Lines",
    )
    line_count = fields.Count(
        count_of="line_ids",
        string="Tasks Snapshot",
        export_string_translation=False,
    )

    _unique_current_baseline = models.UniqueIndex(
        "(project_id) WHERE (is_current IS TRUE)",
        "Only one baseline per project can be marked as current.",
    )

    def action_set_current(self) -> None:
        self.check_singleton()
        previous = self.project_id.baseline_ids.filtered("is_current")
        _debug.lifecycle(
            "baseline_set_current",
            baseline=self,
            project=self.project_id.id,
            replacing=previous,
        )
        previous.write({"is_current": False})
        self.is_current = True

    @_debug.perf.timed
    def action_capture_snapshot(self) -> None:
        self.check_singleton()
        if self.line_ids:
            raise UserError(
                self.env._(
                    "This baseline already has snapshot data. "
                    "Create a new baseline instead."
                )
            )
        tasks = self.env["project.task"].search(
            [
                ("project_id", "=", self.project_id.id),
                ("is_template", "=", False),
            ]
        )
        _debug.lifecycle(
            "snapshot_captured",
            baseline=self,
            project=self.project_id.id,
            tasks=len(tasks),
        )
        lines = [
            {
                "baseline_id": self.id,
                "task_id": task.id,
                "task_name": task.name,
                "date_planned_start": task.date_start,
                "date_planned_end": task.date_end,
                "planned_hours": task.planned_hours,
                "milestone_id": task.milestone_id.id,
                "step_id": task.step_id.id,
            }
            for task in tasks
        ]
        self.env["project.baseline.line"].create(lines)


class ProjectBaselineLine(models.Model):
    _name = "project.baseline.line"
    _access_anchors = frozendict({"company": "project_id.company_id"})
    _description = "Baseline Task Snapshot"
    _order = "sequence, id"

    _SNAPSHOT_FIELDS = frozenset(
        {
            "baseline_id",
            "task_name",
            "date_planned_start",
            "date_planned_end",
            "planned_hours",
            "milestone_id",
            "step_id",
        }
    )

    baseline_id = fields.Many2one(
        comodel_name="project.baseline",
        index=True,
        required=True,
        ondelete="cascade",
    )
    project_id = fields.Many2one(
        related="baseline_id.project_id",
    )
    task_id = fields.Many2one(
        comodel_name="project.task",
        index=True,
        ondelete="set null",
        help="Link to the original task (may be deleted since snapshot).",
    )
    task_name = fields.Char(
        string="Task Name (snapshot)",
        required=True,
    )
    sequence = fields.Integer(default=10)
    date_planned_start = fields.Datetime(string="Planned Start (snapshot)")
    date_planned_end = fields.Datetime(string="Planned End (snapshot)")
    planned_hours = fields.Float(string="Planned Hours (snapshot)")
    milestone_id = fields.Many2one(
        comodel_name="project.milestone",
        string="Milestone (snapshot)",
        ondelete="set null",
    )
    step_id = fields.Many2one(
        comodel_name="project.workflow.step",
        string="Step (snapshot)",
        ondelete="set null",
    )
    start_variance_days = fields.Float(
        string="Start Slip (days)",
        export_string_translation=False,
        digits=(16, 1),
        compute="_compute_variances",
        help="Current planned start minus the snapshot's. Positive = later.",
    )
    end_variance_days = fields.Float(
        string="End Slip (days)",
        export_string_translation=False,
        digits=(16, 1),
        compute="_compute_variances",
        help="Current deadline minus the snapshot's. Positive = later.",
    )
    hours_variance = fields.Float(
        string="Hours Change",
        export_string_translation=False,
        compute="_compute_variances",
        help="Current planned hours minus the snapshot's. Positive = more effort.",
    )

    @api.depends(
        "task_id.date_start",
        "task_id.date_end",
        "task_id.planned_hours",
        "date_planned_start",
        "date_planned_end",
        "planned_hours",
    )
    def _compute_variances(self) -> None:
        def get_slip_days(current, planned) -> float:
            if not (current and planned):
                return 0.0
            return (current - planned).total_seconds() / 86400

        for line in self:
            task = line.task_id
            line.start_variance_days = get_slip_days(
                task.date_start, line.date_planned_start
            )
            line.end_variance_days = get_slip_days(task.date_end, line.date_planned_end)
            line.hours_variance = (
                task.planned_hours - line.planned_hours if task else 0.0
            )

    def write(self, vals: ValuesType) -> bool:
        frozen = self._SNAPSHOT_FIELDS & vals.keys()
        if frozen:
            _debug.logic("snapshot_edit_refused", lines=self, fields=sorted(frozen))
            raise UserError(
                self.env._(
                    "A baseline snapshot cannot be edited; capture a new baseline "
                    "instead."
                )
            )
        return super().write(vals)
