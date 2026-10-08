from datetime import datetime, time

from odoo import Command, api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

from .project_task import CLOSED_STATES, DELIVERED_STATES

_debug = DebugLog(__name__)


class ProjectHistory(models.Model):
    _name = "project.history"
    _access_anchors = frozendict({"company": "company_id"})
    _description = "Project History"
    _order = "date_completed desc, id desc"

    project_id = fields.Many2one(
        comodel_name="project.project",
        index=True,
        ondelete="set null",
        help="Link to the original project (may be archived or deleted).",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        store=True,
        index=True,
        readonly=False,
        help="Kept when the project is deleted, so the snapshot stays scoped to "
        "its company.",
    )
    name = fields.Char(
        string="Project Name (snapshot)",
        required=True,
        help="Frozen project name at time of archival.",
    )
    date_completed = fields.Date(required=True)
    date_start = fields.Date(string="Date Started")
    planned_duration_days = fields.Integer(
        string="Planned Duration (days)",
        help="Days from date_start to planned end date.",
    )
    actual_duration_days = fields.Integer(
        string="Actual Duration (days)",
        help="Days from date_start to actual completion.",
    )
    duration_variance_pct = fields.Float(
        string="Duration Variance %",
        export_string_translation=False,
        compute="_compute_variances",
        store=True,
        help="(actual - planned) / planned * 100. Positive = over-schedule.",
    )
    planned_hours = fields.Float(string="Planned Hours (sum of task.planned_hours)")
    actual_hours = fields.Float(
        help="Sum of effective_hours (requires timesheet module)."
    )
    hours_variance_pct = fields.Float(
        string="Hours Variance %",
        export_string_translation=False,
        compute="_compute_variances",
        store=True,
        help="(actual - planned) / planned * 100. Positive = over-budget.",
    )
    task_count = fields.Integer(string="Total Tasks")
    team_size = fields.Integer(string="Team Size (distinct assignees)")
    tag_ids = fields.Many2many(
        comodel_name="project.tags",
        relation="project_history_tags_rel",
        column1="history_id",
        column2="tag_id",
        string="Tags",
        help="Copied from project tags for reference class search.",
    )
    avg_lead_time = fields.Float(
        string="Avg Lead Time (hours)",
        help="Average lead_time_hours (create→end) at project completion.",
    )
    avg_cycle_time = fields.Float(
        string="Avg Cycle Time (hours)",
        help="Average cycle_time_hours (assign→end) at project completion.",
    )
    deadline_compliance_pct = fields.Float(
        string="Deadline Compliance %",
        help="Percentage of tasks that met their deadlines.",
    )

    @api.depends("project_id")
    def _compute_company_id(self) -> None:
        for history in self:
            if history.project_id:
                history.company_id = history.project_id.company_id

    @api.depends(
        "planned_duration_days",
        "actual_duration_days",
        "planned_hours",
        "actual_hours",
    )
    def _compute_variances(self) -> None:
        for rec in self:
            if rec.planned_duration_days:
                rec.duration_variance_pct = (
                    (rec.actual_duration_days - rec.planned_duration_days)
                    / rec.planned_duration_days
                    * 100
                )
            else:
                rec.duration_variance_pct = 0.0
            if rec.planned_hours:
                rec.hours_variance_pct = (
                    (rec.actual_hours - rec.planned_hours) / rec.planned_hours * 100
                )
            else:
                rec.hours_variance_pct = 0.0

    @_debug.perf.timed
    @api.model
    def create_from_project(self, project) -> ProjectHistory:
        vals = self._prepare_history_vals(project)
        today_start = datetime.combine(fields.Date.today(), time.min)
        snapshot = self.search(
            [("project_id", "=", project.id), ("create_date", ">=", today_start)],
            limit=1,
        )
        _debug.logic(
            "history_snapshot_written",
            project=project.id,
            mode="update" if snapshot else "create",
            history=snapshot,
        )
        if snapshot:
            snapshot.write(vals)
            return snapshot
        return self.create(vals)

    @_debug.perf.timed
    @api.model
    def _prepare_history_vals(self, project) -> dict:
        Task = self.env["project.task"]
        domain = Domain("project_id", "=", project.id) & Domain(
            "is_template", "=", False
        )
        delivered = domain & Domain("state", "in", DELIVERED_STATES)
        has_hours = "effective_hours" in Task._fields
        aggregates = ["__count", "planned_hours:sum"]
        if has_hours:
            aggregates.append("effective_hours:sum")
        [totals] = Task._read_group(domain, aggregates=aggregates)
        task_count, planned_hours, *effective = totals
        actual_hours = effective[0] if has_hours else 0.0
        team_size = sum(1 for [user] in Task._read_group(domain, ["user_ids"]) if user)
        [[last_closed]] = Task._read_group(
            domain & Domain("state", "in", list(CLOSED_STATES)),
            aggregates=["date_closed:max"],
        )
        [[avg_lead_time]] = Task._read_group(
            delivered & Domain("lead_time_hours", "!=", 0),
            aggregates=["lead_time_hours:avg"],
        )
        [[avg_cycle_time]] = Task._read_group(
            delivered & Domain("cycle_time_hours", "!=", 0),
            aggregates=["cycle_time_hours:avg"],
        )
        deadline_counts = dict(
            Task._read_group(
                delivered & Domain("deadline_met", "!=", False),
                ["deadline_met"],
                ["__count"],
            )
        )
        deadline_judged = sum(deadline_counts.values())
        deadline_pct = (
            deadline_counts.get("met", 0) / deadline_judged * 100
            if deadline_judged
            else 0.0
        )

        completion_date = last_closed.date() if last_closed else fields.Date.today()
        planned_days = 0
        if project.date_start and project.date:
            planned_days = (project.date - project.date_start).days
        actual_days = 0
        if project.date_start:
            actual_days = (completion_date - project.date_start).days

        _debug.logic(
            "history_measured",
            project=project.id,
            tasks=task_count,
            planned_days=planned_days,
            actual_days=actual_days,
            planned_hours=planned_hours,
            actual_hours=actual_hours,
            lead_time=avg_lead_time,
            cycle_time=avg_cycle_time,
            deadline_pct=deadline_pct,
        )
        return {
            "project_id": project.id,
            "company_id": project.company_id.id,
            "name": project.name,
            "date_completed": completion_date,
            "date_start": project.date_start,
            "planned_duration_days": planned_days,
            "actual_duration_days": actual_days,
            "planned_hours": planned_hours,
            "actual_hours": actual_hours,
            "task_count": task_count,
            "team_size": team_size,
            "tag_ids": [Command.set(project.tag_ids.ids)],
            "avg_lead_time": avg_lead_time or 0.0,
            "avg_cycle_time": avg_cycle_time or 0.0,
            "deadline_compliance_pct": deadline_pct,
        }
