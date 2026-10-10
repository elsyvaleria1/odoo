from collections import defaultdict, deque
from collections.abc import Collection
from datetime import date, datetime, time, timedelta
from typing import Any, Literal, Self

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.numbers import float_utils
from odoo.tools import SQL, LazyTranslate, formatLang, get_lang
from odoo.tools.cache_version import versioned_envelope
from odoo.tools.date_utils import localized
from odoo.tools.misc import unquote

from .project_task import CLOSED_STATES, DELIVERED_STATES
from .project_update import STATUS_COLOR
from odoo.addons.base.models.resource_utils import last_day_of
from odoo.addons.mail.tools.discuss import Store, StoreFieldSpec
from odoo.addons.rating.models import rating_data

_debug = DebugLog(__name__)
_lt = LazyTranslate(__name__)


CpmPredecessors = dict[int, list[tuple[int, str, float]]]
CpmSuccessors = dict[int, list[int]]
LevellingSlot = tuple[datetime, datetime, float, int]


def get_cpm_topological_order(
    task_ids: Collection[int],
    deps_on: CpmPredecessors,
    successors_of: CpmSuccessors,
) -> list[int]:
    indegree = {tid: len(deps_on.get(tid, ())) for tid in task_ids}
    ready = deque(sorted(tid for tid in task_ids if not indegree[tid]))
    order: list[int] = []
    while ready:
        tid = ready.popleft()
        order.append(tid)
        for succ_id in successors_of.get(tid, ()):
            indegree[succ_id] -= 1
            if not indegree[succ_id]:
                ready.append(succ_id)
    return order


def get_cpm_earliest_start_and_finish(
    order: list[int],
    deps_on: CpmPredecessors,
    duration: dict[int, float],
    release: dict[int, float] | None = None,
) -> tuple[dict[int, float], dict[int, float]]:
    release = release or {}
    es: dict[int, float] = {}
    ef: dict[int, float] = {}
    for tid in order:
        start = release.get(tid, 0.0)
        finish_constraint = None
        for pred_id, dtype, lag in deps_on.get(tid, ()):
            if dtype == "fs":
                start = max(start, ef[pred_id] + lag)
            elif dtype == "ss":
                start = max(start, es[pred_id] + lag)
            elif dtype == "ff":
                finish_constraint = max(finish_constraint or 0.0, ef[pred_id] + lag)
            elif dtype == "sf":
                finish_constraint = max(finish_constraint or 0.0, es[pred_id] + lag)
        if finish_constraint is not None:
            start = max(start, finish_constraint - duration[tid])
        es[tid] = start
        ef[tid] = start + duration[tid]
    return es, ef


def get_cpm_latest_start(
    order: list[int],
    deps_on: CpmPredecessors,
    successors_of: CpmSuccessors,
    duration: dict[int, float],
    project_end: float,
) -> dict[int, float]:
    lf: dict[int, float] = {}
    ls: dict[int, float] = {}
    for tid in reversed(order):
        lf[tid] = project_end
        for succ_id in successors_of.get(tid, ()):
            for pred_id, dtype, lag in deps_on[succ_id]:
                if pred_id != tid:
                    continue
                if dtype == "fs":
                    lf[tid] = min(lf[tid], ls[succ_id] - lag)
                elif dtype == "ss":
                    lf[tid] = min(lf[tid], ls[succ_id] - lag + duration[tid])
                elif dtype == "ff":
                    lf[tid] = min(lf[tid], lf[succ_id] - lag)
                elif dtype == "sf":
                    lf[tid] = min(lf[tid], lf[succ_id] - lag + duration[tid])
        ls[tid] = lf[tid] - duration[tid]
    return ls


def solve_cpm(
    task_ids: Collection[int],
    deps_on: CpmPredecessors,
    successors_of: CpmSuccessors,
    duration: dict[int, float],
    release: dict[int, float] | None = None,
) -> tuple[dict[int, float], dict[int, float], dict[int, float]] | None:
    order = get_cpm_topological_order(task_ids, deps_on, successors_of)
    if len(order) != len(task_ids):
        return None
    es, ef = get_cpm_earliest_start_and_finish(order, deps_on, duration, release)
    project_end = max(ef.values(), default=0.0)
    ls = get_cpm_latest_start(order, deps_on, successors_of, duration, project_end)
    return es, ef, ls


def get_levelling_spread(slot: LevellingSlot, day_capacity: dict) -> dict:
    start, stop, hours, _task_id = slot
    days = {
        day: capacity
        for day, capacity in day_capacity.items()
        if start.date() <= day <= last_day_of(start, stop) and capacity
    }
    total = sum(days.values())
    if not total:
        return {}
    return {day: hours * capacity / total for day, capacity in days.items()}


def is_levelling_overloaded(
    slot: LevellingSlot, overlapping: list[LevellingSlot], day_capacity: dict
) -> bool:
    start, stop = slot[0], slot[1]
    load_by_day: dict = defaultdict(float)
    for other in (*overlapping, slot):
        for day, hours in get_levelling_spread(other, day_capacity).items():
            load_by_day[day] += hours
    last_day = last_day_of(start, stop)
    return any(
        start.date() <= day <= last_day
        and float_utils.float_compare(
            hours, day_capacity.get(day, 0.0), precision_digits=2
        )
        > 0
        for day, hours in load_by_day.items()
    )


class ProjectProject(models.Model):
    _name = "project.project"
    _description = "Project"
    _inherit = [
        "mixin.analytic.plan.fields",
        "mixin.mail.activity",
        "mixin.mail.alias",
        "mixin.mail.tracking.duration",
        "mixin.portal",
        "mixin.rating.parent",
        "mixin.user.favorite",
    ]
    _order = "sequence, name, id"
    _rating_satisfaction_days = 30
    _track_duration_field = "phase_id"

    @_debug.perf.timed
    def _compute_task_counts(self) -> None:
        closed_states = set(CLOSED_STATES)
        counts: dict[int, list[int]] = {}
        active_projects = self.filtered("active")
        for subset, active_test in (
            (active_projects, True),
            (self - active_projects, False),
        ):
            if not subset:
                continue
            ProjectTask = self.env["project.task"].with_context(active_test=active_test)
            for project, state, count in ProjectTask._read_group(
                Domain("project_id", "in", subset.ids)
                & Domain("is_template", "=", False),
                ["project_id", "state"],
                ["__count"],
            ):
                total = counts.setdefault(project.id, [0, 0, 0])
                total[0] += count
                total[2 if state in closed_states else 1] += count
        for project in self:
            project.task_count, project.open_task_count, project.closed_task_count = (
                counts.get(project.id, (0, 0, 0))
            )

    @api.model
    def _get_default_phase(self, company: Any) -> Any:
        return self.env["project.phase"].search(
            [("company_id", "in", [*company.ids, False])], limit=1
        )

    def _default_phase_id(self) -> Any:
        return self._get_default_phase(
            self.env["res.company"].browse(self.env.context.get("default_company_id"))
        )

    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        inverse="_inverse_company_id",
        store=True,
        readonly=False,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        export_string_translation=False,
        compute="_compute_currency_id",
        readonly=True,
    )
    account_id = fields.Many2one(
        comodel_name="account.analytic.account",
        copy=False,
        domain="['|', ('company_id', '=', False), ('company_id', '=?', company_id)]",
        ondelete="set null",
    )
    amount_analytic_balance = fields.Monetary(related="account_id.balance")
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        index="btree_not_null",
        domain="['|', ('company_id', '=?', company_id), ('company_id', '=', False)]",
        bypass_search_access=True,
        tracking=True,
    )
    resource_calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        string="Working Time",
        export_string_translation=False,
        compute="_compute_resource_calendar_id",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Project Manager",
        default=lambda self: self.env.user,
        falsy_value_label=_lt("👤 Unassigned"),
        tracking=True,
    )
    alias_id = fields.Many2one(
        help="Internal email associated with this project. Incoming emails are automatically synchronized "
        "with Tasks (or optionally Issues if the Issue Tracker module is installed)."
    )

    phase_id = fields.Many2one(
        comodel_name="project.phase",
        compute="_compute_phase_id",
        default=lambda self: self._default_phase_id(),
        store=True,
        index=True,
        copy=False,
        readonly=False,
        group_expand="_read_group_expand_full",
        ondelete="restrict",
        tracking=True,
        groups="project.group_project_stages",
    )
    phase_color = fields.Integer(
        related="phase_id.color",
        string="Phase Color",
        export_string_translation=False,
    )

    name = fields.Char(
        translate=True,
        index="trigram",
        required=True,
        tracking=True,
        default_export_compatible=True,
    )
    active = fields.Boolean(
        export_string_translation=False,
        default=True,
        copy=False,
    )
    sequence = fields.Integer(
        export_string_translation=False,
        default=10,
    )
    description = fields.Html(
        help="Description to provide more information and context about this project"
    )
    label_tasks = fields.Char(
        string="Use Tasks as",
        translate=True,
        default=lambda s: s.env._("Tasks"),
        help="Name used to refer to the tasks of your project e.g. tasks, tickets, sprints, etc...",
    )
    color = fields.Integer(
        string="Color Index",
        export_string_translation=False,
    )
    duration_tracking = fields.Json(groups="project.group_project_stages")
    date_start = fields.Date(
        string="Start Date",
        copy=False,
    )
    date_end = fields.Date(
        string="End Date",
        index=True,
        copy=False,
        tracking=True,
        help="Date on which this project ends. The timeframe defined on the "
        "project is taken into account when viewing its planning.",
    )
    date = fields.Date(
        related="date_end",
        string="Expiration Date",
        readonly=False,
    )

    privacy_visibility = fields.Selection(
        selection=[
            ("followers", "Team members only"),
            ("invited_users", "Team members and invited portal users"),
            ("employees", "All internal users"),
            ("portal", "All internal users and invited portal users"),
        ],
        string="Visibility",
        default="portal",
        required=True,
        tracking=True,
        help="Who can access the project and its tasks:\n"
        "- Team members only: the project manager and the team members.\n"
        "- Team members and invited portal users: the same, plus the portal users invited as collaborators.\n"
        "- All internal users: every internal user.\n"
        "- All internal users and invited portal users: every internal user, plus the portal users invited as collaborators.\n\n"
        "Collaborator access modes:\n"
        "- View: read the tasks and write in their chatter.\n"
        "- Edit: also create and update tasks.\n"
        "- Advanced Edit: also move tasks between steps and change their priority.\n\n"
        "Following a project or a task only subscribes to its notifications. An internal user "
        "or portal contact following a task can still read that task.",
    )
    member_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="project_project_member_user_rel",
        column1="project_id",
        column2="user_id",
        string="Team Members",
        domain=[("share", "=", False)],
        help="Internal users who can access the project when its visibility is limited to team members.",
    )
    user_has_access = fields.Boolean(
        export_string_translation=False,
        compute="_compute_user_has_access",
        search="_search_user_has_access",
    )
    access_instruction_message = fields.Char(
        export_string_translation=False,
        compute="_compute_access_instruction_message",
    )
    allow_dependencies = fields.Boolean(
        string="Task Dependencies",
        inverse="_inverse_allow_dependencies",
    )
    allow_milestones = fields.Boolean(
        string="Milestones",
        inverse="_inverse_allow_milestones",
    )
    allow_recurring_tasks = fields.Boolean(
        string="Recurring Tasks",
        inverse="_inverse_allow_recurring_tasks",
    )
    use_sprints = fields.Boolean(help="Enable time-boxed iterations for this project.")

    sprint_ids = fields.One2many(
        comodel_name="project.sprint",
        inverse_name="project_id",
        string="Sprints",
        export_string_translation=False,
    )
    active_sprint_id = fields.Many2one(
        comodel_name="project.sprint",
        export_string_translation=False,
        compute="_compute_active_sprint_id",
    )
    sprint_count = fields.Count(
        count_of="sprint_ids",
        export_string_translation=False,
    )

    tag_ids = fields.Many2many(
        comodel_name="project.tags",
        relation="project_project_project_tags_rel",
        string="Tags",
    )
    favorite_user_ids = fields.Many2many(string="Members")
    is_user_favorite = fields.Boolean(string="Show Project on Dashboard")
    workflow_step_ids = fields.Many2many(
        comodel_name="project.workflow.step",
        relation="project_workflow_step_project_rel",
        column1="project_id",
        column2="step_id",
        string="Workflow Steps",
        export_string_translation=False,
    )
    task_ids = fields.One2many(
        comodel_name="project.task",
        inverse_name="project_id",
        string="Tasks",
    )
    task_properties_definition = fields.PropertiesDefinition(string="Task Properties")
    archived_with_project_task_ids = fields.Many2many(
        comodel_name="project.task",
        relation="project_project_archived_task_rel",
        column1="project_id",
        column2="task_id",
        string="Tasks Archived with the Project",
        export_string_translation=False,
        copy=False,
        readonly=True,
    )
    archived_tasks_recorded = fields.Boolean(
        export_string_translation=False,
        copy=False,
        readonly=True,
    )
    task_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_task_counts",
    )
    open_task_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_task_counts",
    )
    closed_task_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_task_counts",
    )
    task_completion_percentage = fields.Float(
        export_string_translation=False,
        compute="_compute_task_completion_percentage",
    )

    collaborator_ids = fields.One2many(
        comodel_name="project.collaborator",
        inverse_name="project_id",
        string="Collaborators",
        export_string_translation=False,
        copy=False,
    )
    collaborator_count = fields.Integer(
        string="# Collaborators",
        export_string_translation=False,
        compute="_compute_collaborator_count",
        compute_sudo=True,
    )

    update_ids = fields.One2many(
        comodel_name="project.update",
        inverse_name="project_id",
        export_string_translation=False,
    )
    update_count = fields.Count(
        count_of="update_ids",
        export_string_translation=False,
    )
    last_update_id = fields.Many2one(
        comodel_name="project.update",
        export_string_translation=False,
        compute="_compute_last_update_id",
        compute_sudo=True,
        store=True,
    )
    last_update_status = fields.Selection(
        selection=[
            ("on_track", "On Track"),
            ("at_risk", "At Risk"),
            ("off_track", "Off Track"),
            ("on_hold", "On Hold"),
            ("to_define", "Set Status"),
            ("done", "Complete"),
        ],
        export_string_translation=False,
        compute="_compute_last_update_status",
        default="to_define",
        store=True,
        readonly=False,
        required=True,
    )
    last_update_color = fields.Integer(
        export_string_translation=False,
        compute="_compute_last_update_color",
    )

    milestone_ids = fields.One2many(
        comodel_name="project.milestone",
        inverse_name="project_id",
        export_string_translation=False,
        copy=True,
    )
    milestone_count = fields.Count(
        count_of="milestone_ids",
        export_string_translation=False,
        groups="project.group_project_milestone",
    )
    milestone_count_reached = fields.Integer(
        export_string_translation=False,
        compute="_compute_milestone_reached_count",
        groups="project.group_project_milestone",
    )
    is_milestone_exceeded = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_milestone_exceeded",
        search="_search_is_milestone_exceeded",
    )
    milestone_progress = fields.Integer(
        string="Milestones Reached",
        export_string_translation=False,
        compute="_compute_milestone_reached_count",
        groups="project.group_project_milestone",
    )
    next_milestone_id = fields.Many2one(
        comodel_name="project.milestone",
        export_string_translation=False,
        compute="_compute_next_milestone_indicators",
        groups="project.group_project_milestone",
    )
    can_mark_milestone_as_done = fields.Boolean(
        export_string_translation=False,
        compute="_compute_next_milestone_indicators",
        groups="project.group_project_milestone",
    )
    is_milestone_deadline_exceeded = fields.Boolean(
        export_string_translation=False,
        compute="_compute_next_milestone_indicators",
        groups="project.group_project_milestone",
    )

    benefit_ids = fields.One2many(
        comodel_name="project.benefit",
        inverse_name="project_id",
        string="Benefits",
        export_string_translation=False,
    )
    benefit_count = fields.Count(
        count_of="benefit_ids",
        export_string_translation=False,
    )

    baseline_ids = fields.One2many(
        comodel_name="project.baseline",
        inverse_name="project_id",
        string="Baselines",
        export_string_translation=False,
    )
    current_baseline_id = fields.Many2one(
        comodel_name="project.baseline",
        export_string_translation=False,
        compute="_compute_current_baseline_id",
    )

    gate_ids = fields.One2many(
        comodel_name="project.gate",
        inverse_name="project_id",
        string="Gate Reviews",
        export_string_translation=False,
    )
    gate_count = fields.Count(
        count_of="gate_ids",
        string="Gates",
        export_string_translation=False,
    )

    history_ids = fields.One2many(
        comodel_name="project.history",
        inverse_name="project_id",
        string="History Records",
        export_string_translation=False,
    )

    premortem_done = fields.Boolean(
        string="Pre-Mortem Conducted",
        help="Was a pre-mortem exercise conducted at project kickoff?",
    )
    date_premortem = fields.Date(string="Pre-Mortem Date")
    premortem_participant_ids = fields.Many2many(
        comodel_name="res.users",
        relation="project_premortem_participants_rel",
        column1="project_id",
        column2="user_id",
        string="Pre-Mortem Participants",
    )
    premortem_notes = fields.Html(
        string="Pre-Mortem Notes",
        help="'Imagine this project has failed. Why?' — capture all identified failure modes.",
    )

    retrospective_ids = fields.One2many(
        comodel_name="project.retrospective",
        inverse_name="project_id",
        string="Retrospectives",
        export_string_translation=False,
    )
    retrospective_count = fields.Count(
        count_of="retrospective_ids",
        export_string_translation=False,
    )

    health_score = fields.Integer(
        export_string_translation=False,
        compute="_compute_health_indicators",
        store=True,
        help="Composite 0-100 score based on deadlines, milestones, risk, and staleness.",
    )
    health_status = fields.Selection(
        selection=[
            ("healthy", "Healthy"),
            ("attention", "Needs Attention"),
            ("warning", "Warning"),
            ("critical", "Critical"),
        ],
        string="Health",
        export_string_translation=False,
        compute="_compute_health_indicators",
        store=True,
        help="Derived from health_score: healthy (80-100), attention (60-79), warning (40-59), critical (0-39).",
    )

    risk_ids = fields.One2many(
        comodel_name="project.risk",
        inverse_name="project_id",
        string="Risks",
        export_string_translation=False,
    )
    risk_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_risk_counts",
    )
    high_risk_count = fields.Integer(
        string="High/Critical Risks",
        export_string_translation=False,
        compute="_compute_risk_counts",
    )

    wip_count = fields.Integer(
        string="WIP Count",
        export_string_translation=False,
        compute="_compute_flow_metrics",
        store=True,
        help="Number of open, non-blocked tasks.",
    )
    avg_lead_time = fields.Float(
        string="Avg Lead Time (hours)",
        export_string_translation=False,
        digits=(16, 1),
        compute="_compute_flow_metrics",
        store=True,
        help="Average working hours from creation to closure (last 90 days). "
        "Includes queue wait time.",
    )
    avg_cycle_time = fields.Float(
        string="Avg Cycle Time (hours)",
        export_string_translation=False,
        digits=(16, 1),
        compute="_compute_flow_metrics",
        store=True,
        help="Average working hours from assignment to closure (last 90 days). "
        "Excludes queue wait time.",
    )
    throughput_week = fields.Float(
        string="Throughput / Week",
        export_string_translation=False,
        digits=(16, 1),
        compute="_compute_flow_metrics",
        store=True,
        help="Tasks closed per week (rolling 4-week average).",
    )
    deadline_compliance_pct = fields.Float(
        string="Deadline Compliance %",
        export_string_translation=False,
        digits=(5, 1),
        compute="_compute_flow_metrics",
        store=True,
        help="Percentage of closed tasks with deadlines that met their deadline.",
    )

    is_template = fields.Boolean(
        export_string_translation=False,
        copy=False,
    )
    show_ratings = fields.Boolean(
        export_string_translation=False,
        compute="_compute_show_ratings",
    )

    _project_date_greater = models.Constraint(
        "check(date_end >= date_start)",
        "The project's start date must be before its end date.",
    )

    @api.depends("company_id")
    def _compute_phase_id(self) -> None:
        for project in self:
            if (
                project.phase_id.company_id
                and project.phase_id.company_id != project.company_id
            ):
                project.phase_id = self._get_default_phase(project.company_id)
                _debug.logic(
                    "phase_follows_company",
                    project=project.id,
                    company=project.company_id.id,
                    phase=project.phase_id.id,
                )

    @api.depends(
        "milestone_ids",
        "milestone_ids.sequence",
        "milestone_ids.name",
        "milestone_ids.is_reached",
        "milestone_ids.date_deadline",
    )
    def _compute_next_milestone_indicators(self) -> None:
        next_milestone_per_project_id = {}
        for milestone in self.env["project.milestone"].search(
            [("project_id", "in", self.ids), ("is_reached", "=", False)]
        ):
            next_milestone_per_project_id.setdefault(milestone.project_id.id, milestone)
        next_milestones = self.env["project.milestone"].concat(
            *next_milestone_per_project_id.values()
        )
        task_counts = defaultdict(lambda: [0, 0])
        for milestone, state, count in self.env["project.task"]._read_group(
            [("milestone_id", "in", next_milestones.ids)],
            ["milestone_id", "state"],
            ["__count"],
        ):
            task_counts[milestone.id][state in CLOSED_STATES] += count
        for project in self:
            milestone = next_milestone_per_project_id.get(
                project.id, self.env["project.milestone"]
            )
            open_count, closed_count = task_counts[milestone.id]
            project.next_milestone_id = milestone
            project.is_milestone_deadline_exceeded = bool(
                milestone.is_deadline_exceeded and (open_count or not closed_count)
            )
            project.can_mark_milestone_as_done = bool(
                milestone and not open_count and closed_count
            )
            _debug.logic(
                "next_milestone_computed",
                project=project.id,
                milestone=milestone.id,
                open_tasks=open_count,
                closed_tasks=closed_count,
            )

    @api.depends("sprint_ids", "sprint_ids.state")
    def _compute_active_sprint_id(self) -> None:
        for project in self:
            project.active_sprint_id = project.sprint_ids.filtered(
                lambda s: s.state == "active"
            )[:1]

    @api.depends("baseline_ids", "baseline_ids.is_current")
    def _compute_current_baseline_id(self) -> None:
        for project in self:
            project.current_baseline_id = project.baseline_ids.filtered("is_current")[
                :1
            ]

    def action_snapshot_to_history(self) -> None:
        self.check_singleton()
        _debug.lifecycle("snapshot_to_history", project=self.id)
        self.env["project.history"].create_from_project(self)

    def _snapshot_archived_to_history(self) -> None:
        projects = self.filtered(lambda project: not project.is_template)
        _debug.logic("archive_snapshots", projects=projects, templates=self - projects)
        History = self.env["project.history"]
        for project in projects:
            History.create_from_project(project)

    def _get_cpm_tasks(self) -> Any:
        self.check_singleton()
        return self.env["project.task"].search(
            [
                ("project_id", "=", self.id),
                ("is_template", "=", False),
                ("state", "not in", list(CLOSED_STATES)),
            ]
        )

    def _get_cpm_network(
        self, tasks: Any
    ) -> tuple[CpmPredecessors, CpmSuccessors, dict[int, float]]:
        task_set = set(tasks.ids)
        deps_on: CpmPredecessors = defaultdict(list)
        successors_of: CpmSuccessors = defaultdict(list)
        seen_edges: set[tuple[int, int]] = set()

        def add_edge(tid, pred_id, dtype, lag) -> None:
            if tid not in task_set or pred_id not in task_set:
                return
            if (tid, pred_id) in seen_edges:
                return
            seen_edges.add((tid, pred_id))
            deps_on[tid].append((pred_id, dtype, lag))
            successors_of[pred_id].append(tid)

        for dep in self.env["project.task.dependency"].search(
            [("project_id", "=", self.id)]
        ):
            add_edge(
                dep.task_id.id,
                dep.depends_on_id.id,
                dep.dependency_type,
                dep.lag_hours,
            )
        duration = {task.id: task._get_cpm_duration_hours() for task in tasks}
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "critical_path_graph",
                project=self.id,
                edges=len(seen_edges),
                duration_hours=sum(duration.values()),
            )
        return deps_on, successors_of, duration

    def _solve_cpm(
        self,
        tasks: Any,
        deps_on: CpmPredecessors,
        successors_of: CpmSuccessors,
        duration: dict[int, float],
        release: dict[int, float] | None = None,
    ) -> tuple[dict[int, float], dict[int, float], dict[int, float]]:
        solved = solve_cpm(set(tasks.ids), deps_on, successors_of, duration, release)
        if solved is None:
            raise UserError(
                self.env._(
                    "A dependency cycle was detected among the tasks "
                    "of project %(project)s. Resolve the circular "
                    "dependency before computing the critical path.",
                    project=self.display_name,
                )
            )
        return solved

    def _get_cpm_datetime(self, hours: float, now: datetime) -> datetime:
        if not hours:
            return now
        if calendar := self.resource_calendar_id:
            return calendar.plan_hours(hours, now)
        return now + timedelta(hours=hours)

    @_debug.perf.timed
    def action_compute_critical_path(self) -> None:
        tasks = self._get_cpm_tasks()
        _debug.pipeline("critical_path_started", project=self.id, open_tasks=len(tasks))
        if not tasks:
            return
        es, ef, ls = self._solve_cpm(tasks, *self._get_cpm_network(tasks))
        if _debug.logic.enabled:
            _debug.logic(
                "critical_path_computed",
                project=self.id,
                end_hours=max(ef.values(), default=0.0),
                critical=tasks.browse(
                    [tid for tid in es if abs(ls[tid] - es[tid]) < 0.01]
                ),
            )
        self._update_cpm_schedule(tasks, es, ef, ls, fields.Datetime.now())

    def _update_cpm_schedule(
        self,
        tasks: Any,
        es: dict[int, float],
        ef: dict[int, float],
        ls_map: dict[int, float],
        now: datetime,
    ) -> None:
        tasks_by_vals = defaultdict(lambda: self.env["project.task"])
        vals_by_key = {}
        for task in tasks:
            tid = task.id
            es_h = es.get(tid, 0.0)
            ls_h = ls_map.get(tid, 0.0)
            total_fl = ls_h - es_h
            cpm_start = self._get_cpm_datetime(es_h, now)
            vals = {
                "cpm_date_earliest_start": cpm_start,
                "cpm_date_latest_start": self._get_cpm_datetime(ls_h, now),
                "total_float": total_fl,
                "is_critical_path": abs(total_fl) < 0.01,
                "cpm_date_start": cpm_start,
                "cpm_date_end": self._get_cpm_datetime(ef.get(tid, 0.0), now),
            }
            key = repr(sorted(vals.items()))
            tasks_by_vals[key] |= task
            vals_by_key[key] = vals
        _debug.perf.count(
            "cpm_schedule_write_groups",
            project=self.id,
            tasks=len(tasks),
            write_groups=len(tasks_by_vals),
        )
        for key, group in tasks_by_vals.items():
            group.write(vals_by_key[key])

    def _get_levelling_day_capacity(
        self, calendar: Any, date_start: Any, date_end: Any
    ) -> dict:
        calendar = (
            calendar or self.env["resource.calendar"]._get_fully_flexible_calendar()
        )
        intervals = calendar._work_intervals_batch(
            localized(date_start), localized(date_end)
        )[False]
        return calendar._get_hours_by_day(intervals)

    @_debug.perf.timed
    def action_level_resources(self) -> None:
        tasks = self._get_cpm_tasks()
        _debug.pipeline(
            "level_resources_started", project=self.id, open_tasks=len(tasks)
        )
        if not tasks:
            return
        deps_on, successors_of, duration = self._get_cpm_network(tasks)
        es, ef, ls = self._solve_cpm(tasks, deps_on, successors_of, duration)
        now = fields.Datetime.now()
        calendar = self.resource_calendar_id
        task_by_id = {task.id: task for task in tasks}
        dates = {
            tid: (
                self._get_cpm_datetime(es[tid], now),
                self._get_cpm_datetime(ef[tid], now),
            )
            for tid in es
        }
        load = {
            task.id: (task.allocated_hours or task.planned_hours or 0.0)
            / max(len(task.user_ids), 1)
            for task in tasks
        }
        user_slots: dict[int, dict[int, LevellingSlot]] = defaultdict(dict)
        for task in tasks:
            for user in task.user_ids:
                user_slots[user.id][task.id] = (*dates[task.id], load[task.id], task.id)

        leveling_order = sorted(
            (task for task in tasks if ls[task.id] - es[task.id] >= 0.01),
            key=lambda task: es[task.id] - ls[task.id],
        )
        _debug.logic(
            "level_resources_candidates",
            project=self.id,
            tasks=len(tasks),
            to_level=len(leveling_order),
        )

        window_start = min(start for start, _stop in dates.values())
        window_end = max(stop for _start, stop in dates.values())
        day_capacity_per_calendar: dict = {}

        def get_day_capacity(user):
            user_calendar = user.resource_calendar_id or calendar
            if user_calendar.id not in day_capacity_per_calendar:
                day_capacity_per_calendar[user_calendar.id] = (
                    self._get_levelling_day_capacity(
                        user_calendar, window_start, window_end
                    )
                )
            return day_capacity_per_calendar[user_calendar.id]

        release: dict[int, float] = {}
        for task in leveling_order:
            tid = task.id
            if not task.user_ids or not load[tid]:
                continue
            start, stop = dates[tid]
            slot = (start, stop, load[tid], tid)
            blocking_end = None
            for user in task.user_ids:
                overlapping = [
                    other
                    for other in user_slots[user.id].values()
                    if other[3] != tid and other[0] < stop and other[1] > start
                ]
                if overlapping and is_levelling_overloaded(
                    slot, overlapping, get_day_capacity(user)
                ):
                    user_end = max(other[1] for other in overlapping)
                    blocking_end = max(blocking_end or user_end, user_end)
            if blocking_end is None:
                continue
            new_start = (
                calendar.plan_hours(0.0, blocking_end) if calendar else blocking_end
            )
            shift_hours = (
                calendar.get_work_duration_data(start, new_start, compute_leaves=True)[
                    "hours"
                ]
                if calendar and new_start > start
                else (new_start - start).total_seconds() / 3600
            )
            float_hours = ls[tid] - es[tid]
            shifted = 0 < shift_hours <= float_hours
            _debug.logic(
                "level_resources_overload",
                task=task,
                users=task.user_ids.ids,
                shift_hours=shift_hours,
                float_hours=float_hours,
                action="shift" if shifted else "keep",
            )
            if not shifted:
                continue
            release[tid] = es[tid] + shift_hours
            previous_es = es
            es, ef, ls = self._solve_cpm(
                tasks, deps_on, successors_of, duration, release
            )
            for moved_id in [t for t in es if es[t] != previous_es[t]]:
                dates[moved_id] = (
                    self._get_cpm_datetime(es[moved_id], now),
                    self._get_cpm_datetime(ef[moved_id], now),
                )
                for user in task_by_id[moved_id].user_ids:
                    user_slots[user.id][moved_id] = (
                        *dates[moved_id],
                        load[moved_id],
                        moved_id,
                    )
        _debug.pipeline("level_resources_done", project=self.id, shifted=len(release))
        self._update_cpm_schedule(tasks, es, ef, ls, now)

    @_debug.perf.timed
    def _compute_health_indicators(self) -> None:
        if not self.ids:
            self.health_score = 100
            self.health_status = "healthy"
            return

        now = self.env.cr.now()
        today = now.date()

        self.env["project.task"].flush_model(
            [
                "project_id",
                "state",
                "date_end",
                "date_last_status_change",
                "create_date",
                "is_template",
                "active",
            ]
        )
        self.env["project.milestone"].flush_model(
            ["project_id", "is_reached", "date_deadline"]
        )
        self.env["project.risk"].flush_model(
            ["project_id", "risk_score", "active", "state"]
        )

        self.env.cr.execute(
            SQL(
                """
            SELECT
                t.project_id,
                -- Schedule: pct of open tasks with deadline that are not overdue
                CASE
                    WHEN COUNT(*) FILTER (
                        WHERE t.state NOT IN %(closed_states)s
                          AND t.date_end IS NOT NULL
                    ) = 0 THEN 100.0
                    ELSE 100.0 * COUNT(*) FILTER (
                        WHERE t.state NOT IN %(closed_states)s
                          AND t.date_end IS NOT NULL
                          AND t.date_end >= %(now)s
                    ) / NULLIF(COUNT(*) FILTER (
                        WHERE t.state NOT IN %(closed_states)s
                          AND t.date_end IS NOT NULL
                    ), 0)
                END AS schedule_score,
                -- Staleness: pct of open tasks not rotting
                CASE
                    WHEN COUNT(*) FILTER (
                        WHERE t.state NOT IN %(closed_states)s
                    ) = 0 THEN 100.0
                    ELSE 100.0 * COUNT(*) FILTER (
                        WHERE t.state NOT IN %(closed_states)s
                          AND COALESCE(t.date_last_status_change, t.create_date)
                              >= %(now)s - INTERVAL '14 days'
                    ) / NULLIF(COUNT(*) FILTER (
                        WHERE t.state NOT IN %(closed_states)s
                    ), 0)
                END AS staleness_score
            FROM project_task t
            WHERE t.project_id IN %(project_ids)s
              AND t.is_template IS NOT TRUE
              AND t.active = TRUE
            GROUP BY t.project_id
            """,
                project_ids=tuple(self.ids),
                closed_states=tuple(CLOSED_STATES),
                now=now,
            )
        )
        task_scores = {row[0]: (row[1], row[2]) for row in self.env.cr.fetchall()}

        self.env.cr.execute(
            SQL(
                """
            SELECT
                project_id,
                CASE
                    WHEN COUNT(*) = 0 THEN 100.0
                    ELSE 100.0 * COUNT(*) FILTER (
                        WHERE is_reached
                           OR date_deadline IS NULL
                           OR date_deadline >= %(today)s
                    ) / COUNT(*)
                END AS milestone_score
            FROM project_milestone
            WHERE project_id IN %(project_ids)s
            GROUP BY project_id
            """,
                project_ids=tuple(self.ids),
                today=today,
            )
        )
        milestone_scores: dict[int, float] = dict(self.env.cr.fetchall())

        self.env.cr.execute(
            SQL(
                """
            SELECT project_id, COALESCE(SUM(risk_score), 0)
            FROM project_risk
            WHERE project_id IN %(project_ids)s AND active = TRUE
              AND state != %(excluded_state)s
            GROUP BY project_id
            """,
                project_ids=tuple(self.ids),
                excluded_state=self._LIVE_RISK_STATE_EXCLUDED,
            )
        )
        risk_data: dict[int, int] = dict(self.env.cr.fetchall())

        for project in self:
            schedule, staleness = task_scores.get(project.id, (100.0, 100.0))
            milestone = milestone_scores.get(project.id, 100.0)
            total_risk = risk_data.get(project.id, 0)
            risk_health = max(0.0, 100.0 - total_risk * 2)

            score = int((schedule + staleness + milestone + risk_health) / 4)
            _debug.logic(
                "health_computed",
                project=project.id,
                schedule=schedule,
                staleness=staleness,
                milestone=milestone,
                risk=risk_health,
                score=score,
            )
            project.health_score = max(0, min(100, score))
            if score >= 80:
                project.health_status = "healthy"
            elif score >= 60:
                project.health_status = "attention"
            elif score >= 40:
                project.health_status = "warning"
            else:
                project.health_status = "critical"

    _LIVE_RISK_STATE_EXCLUDED = "resolved"

    @_debug.perf.timed
    @api.depends("risk_ids", "risk_ids.risk_level", "risk_ids.active", "risk_ids.state")
    def _compute_risk_counts(self) -> None:
        if not self.ids:
            self.risk_count = 0
            self.high_risk_count = 0
            return
        risk_data = self.env["project.risk"]._read_group(
            [
                ("project_id", "in", self.ids),
                ("active", "=", True),
                ("state", "!=", self._LIVE_RISK_STATE_EXCLUDED),
            ],
            ["project_id", "risk_level"],
            ["__count"],
        )
        counts: dict[int, tuple[int, int]] = {}
        for project, risk_level, count in risk_data:
            total, high = counts.get(project.id, (0, 0))
            total += count
            if risk_level in ("high", "critical"):
                high += count
            counts[project.id] = (total, high)
        for project in self:
            total, high = counts.get(project.id, (0, 0))
            project.risk_count = total
            project.high_risk_count = high

    @_debug.perf.timed
    def _compute_flow_metrics(self) -> None:
        if not self.ids:
            self.wip_count = 0
            self.avg_lead_time = 0.0
            self.avg_cycle_time = 0.0
            self.throughput_week = 0.0
            self.deadline_compliance_pct = 0.0
            return

        now = self.env.cr.now()

        self.env["project.task"].flush_model(
            [
                "project_id",
                "state",
                "date_closed",
                "date_end",
                "lead_time_hours",
                "cycle_time_hours",
                "is_template",
                "active",
            ]
        )

        self.env.cr.execute(
            SQL(
                """
            SELECT
                project_id,
                -- WIP: open non-blocked tasks
                COUNT(*) FILTER (
                    WHERE state NOT IN %(wip_excluded_states)s
                ) AS wip_count,
                -- Avg lead time: create→close (closed in last 90 days).
                -- NOTE: date_closed is the actual completion timestamp; date_end
                -- is the (renamed) deadline. Rolling windows must key off closure.
                AVG(lead_time_hours) FILTER (
                    WHERE state IN %(delivered_states)s
                      AND date_closed >= %(now)s - INTERVAL '90 days'
                      AND lead_time_hours > 0
                ) AS avg_lead_time,
                -- Avg cycle time: assign→close (closed in last 90 days)
                AVG(cycle_time_hours) FILTER (
                    WHERE state IN %(delivered_states)s
                      AND date_closed >= %(now)s - INTERVAL '90 days'
                      AND cycle_time_hours > 0
                ) AS avg_cycle_time,
                -- Throughput: tasks closed in last 28 days / 4
                COUNT(*) FILTER (
                    WHERE state IN %(delivered_states)s
                      AND date_closed >= %(now)s - INTERVAL '28 days'
                ) / 4.0 AS throughput_week,
                -- Deadline compliance: pct of deadline-having closed tasks whose
                -- actual closure (date_closed) landed on or before the deadline.
                CASE
                    WHEN COUNT(*) FILTER (
                        WHERE state IN %(delivered_states)s
                          AND date_end IS NOT NULL
                          AND date_closed IS NOT NULL
                    ) = 0 THEN 0.0
                    ELSE 100.0 * COUNT(*) FILTER (
                        WHERE state IN %(delivered_states)s
                          AND date_end IS NOT NULL
                          AND date_closed IS NOT NULL
                          AND date_closed <= date_end
                    ) / COUNT(*) FILTER (
                        WHERE state IN %(delivered_states)s
                          AND date_end IS NOT NULL
                          AND date_closed IS NOT NULL
                    )
                END AS deadline_compliance_pct
            FROM project_task
            WHERE project_id IN %(project_ids)s
              -- is_template has no default, so it is NULL (not FALSE) for normal
              -- tasks; `= FALSE` would wrongly exclude every non-template task.
              AND is_template IS NOT TRUE
              AND active = TRUE
            GROUP BY project_id
            """,
                project_ids=tuple(self.ids),
                delivered_states=DELIVERED_STATES,
                wip_excluded_states=(*CLOSED_STATES, "blocked"),
                now=now,
            )
        )
        results = {row[0]: row[1:] for row in self.env.cr.fetchall()}
        for project in self:
            wip, avg_lt, avg_ct, tp, dcp = results.get(
                project.id, (0, 0.0, 0.0, 0.0, 0.0)
            )
            _debug.logic(
                "flow_computed",
                project=project.id,
                wip=wip,
                lead=avg_lt,
                cycle=avg_ct,
                throughput=tp,
                deadline_pct=dcp,
            )
            project.wip_count = wip or 0
            project.avg_lead_time = avg_lt or 0.0
            project.avg_cycle_time = avg_ct or 0.0
            project.throughput_week = tp or 0.0
            project.deadline_compliance_pct = dcp or 0.0

    _SNAPSHOT_METRIC_FIELDS = (
        "health_score",
        "health_status",
        "wip_count",
        "avg_lead_time",
        "avg_cycle_time",
        "throughput_week",
        "deadline_compliance_pct",
    )

    @_debug.perf.timed
    def _reset_metrics(self) -> None:
        _debug.lifecycle("metrics_reset", projects=self)
        self._mark_metrics_to_compute()
        self.env.flush_all()

    def _mark_metrics_to_compute(self) -> None:
        for fname in self._SNAPSHOT_METRIC_FIELDS:
            self.env.add_to_compute(self._fields[fname], self)

    @api.model
    def _cron_reset_metrics(self) -> None:
        projects = self.search([])
        _debug.lifecycle("cron_reset_metrics_started", projects=len(projects))
        projects._reset_metrics()
        _debug.lifecycle("cron_reset_metrics_done")

    def action_reset_metrics(self) -> None:
        self._reset_metrics()

    def _compute_access_url(self) -> None:
        super()._compute_access_url()
        for project in self:
            project.access_url = f"/my/projects/{project.id}"

    @api.depends("account_id.company_id", "partner_id.company_id")
    def _compute_company_id(self) -> None:
        for project in self:
            if project.account_id.company_id:
                project.company_id = project.account_id.company_id
            if not project.company_id and project.partner_id.company_id:
                project.company_id = project.partner_id.company_id

    @api.depends_context("company")
    @api.depends("company_id", "company_id.resource_calendar_id")
    def _compute_resource_calendar_id(self) -> None:
        for project in self:
            project.resource_calendar_id = (
                project.company_id.resource_calendar_id
                or self.env.company.resource_calendar_id
            )

    def _inverse_company_id(self) -> None:
        for project in self:
            account = project.account_id
            if (
                project.partner_id
                and project.partner_id.company_id
                and project.company_id
                and project.company_id != project.partner_id.company_id
            ):
                raise UserError(
                    self.env._(
                        "The project and the associated partner must be linked to the same company."
                    )
                )
            if not account or not account.company_id:
                continue
            if project.company_id != account.company_id and (
                account._get_project_counts(include_archived=True)[account.id] > 1
                or account._has_analytic_lines()
            ):
                _debug.logic(
                    "account_company_change_refused",
                    project=project.id,
                    old_company=account.company_id.id,
                    new_company=project.company_id.id,
                    account=account.id,
                )
                raise UserError(
                    self.env._(
                        "The project's company cannot be changed if its analytic account has analytic lines or if more than one project is linked to it."
                    )
                )
            account.company_id = project.company_id or project.partner_id.company_id

    @api.depends("update_ids.date")
    def _compute_last_update_id(self) -> None:
        for project in self:
            latest = max(
                project.update_ids,
                key=lambda update: (update.date or date.min, update._origin.id),
                default=project.update_ids,
            )
            if latest != project.last_update_id:
                _debug.logic(
                    "last_update_reset", project=project.id, last_update=latest.id
                )
            project.last_update_id = latest

    @api.depends("last_update_id.status")
    def _compute_last_update_status(self) -> None:
        for project in self:
            project.last_update_status = project.last_update_id.status or "to_define"

    @api.depends("last_update_status")
    def _compute_last_update_color(self) -> None:
        for project in self:
            project.last_update_color = STATUS_COLOR[project.last_update_status]

    @api.depends("milestone_ids.is_reached", "milestone_count")
    def _compute_milestone_reached_count(self) -> None:
        read_group = self.env["project.milestone"]._read_group(
            [("project_id", "in", self.ids), ("is_reached", "=", True)],
            ["project_id"],
            ["__count"],
        )
        mapped_count = {project.id: count for project, count in read_group}
        for project in self:
            project.milestone_count_reached = mapped_count.get(project.id, 0)
            project.milestone_progress = (
                project.milestone_count
                and project.milestone_count_reached * 100 // project.milestone_count
            )

    @api.depends(
        "milestone_ids",
        "milestone_ids.is_reached",
        "milestone_ids.date_deadline",
        "allow_milestones",
    )
    def _compute_is_milestone_exceeded(self) -> None:
        today = fields.Date.context_today(self)
        read_group = self.env["project.milestone"]._read_group(
            [
                ("project_id", "in", self.filtered("allow_milestones").ids),
                ("is_reached", "=", False),
                ("date_deadline", "<=", today),
            ],
            ["project_id"],
            ["__count"],
        )
        mapped_count = {project.id: count for project, count in read_group}
        for project in self:
            project.is_milestone_exceeded = bool(mapped_count.get(project.id))

    @api.depends_context("company")
    @api.depends("company_id")
    def _compute_currency_id(self) -> None:
        default_currency_id = self.env.company.currency_id
        for project in self:
            project.currency_id = project.company_id.currency_id or default_currency_id

    @api.model
    def _search_is_milestone_exceeded(self, operator: str, value: Any) -> list:
        if operator != "in":
            return NotImplemented

        sql = SQL(
            """(
            SELECT P.id
              FROM project_project P
         LEFT JOIN project_milestone M ON P.id = M.project_id
             WHERE M.is_reached IS false
               AND P.allow_milestones IS true
               AND M.date_deadline <= %s
        )""",
            fields.Date.context_today(self),
        )
        return [("id", "any", sql)]

    @api.depends("collaborator_ids", "privacy_visibility")
    def _compute_collaborator_count(self) -> None:
        project_sharings = self.filtered(
            lambda project: project.privacy_visibility in ["invited_users", "portal"]
        )
        collaborator_read_group = self.env["project.collaborator"]._read_group(
            [("project_id", "in", project_sharings.ids)],
            ["project_id"],
            ["__count"],
        )
        collaborator_count_by_project = {
            project.id: count for project, count in collaborator_read_group
        }
        for project in self:
            project.collaborator_count = collaborator_count_by_project.get(
                project.id, 0
            )

    @api.depends_context("uid")
    @api.depends("privacy_visibility", "member_user_ids", "user_id", "collaborator_ids")
    def _compute_user_has_access(self) -> None:
        accessible = set(
            self.sudo()
            .with_context(active_test=False)
            ._search([("id", "in", self._origin.ids), ("user_has_access", "=", True)])
        )
        for project in self:
            project.user_has_access = project._origin.id in accessible

    def _search_user_has_access(self, operator: str, value: Any) -> Domain:
        if operator not in ("in", "not in"):
            return NotImplemented
        accessible = self._get_domain_user_access()
        return accessible if (operator == "in") == (True in value) else ~accessible

    def _get_domain_user_access(self) -> Domain:
        user = self.env.user
        if user.share:
            Collaborator = self.env["project.collaborator"]
            collaborations = Collaborator.sudo()._search(
                Collaborator._domain_of_user(user)
            )
            return Domain(
                "privacy_visibility", "in", ["invited_users", "portal"]
            ) & Domain("id", "in", collaborations.subselect("project_id"))
        return (
            Domain("privacy_visibility", "in", ["employees", "portal"])
            | Domain("member_user_ids", "in", user.id)
            | Domain("user_id", "=", user.id)
        )

    @api.depends("privacy_visibility")
    def _compute_access_instruction_message(self) -> None:
        for project in self:
            if project.privacy_visibility == "portal":
                project.access_instruction_message = self.env._(
                    "Every internal user can access the project. Invite portal users as collaborators to give them access."
                )
            elif project.privacy_visibility == "followers":
                project.access_instruction_message = self.env._(
                    "Only the project manager and the team members can access the project."
                )
            elif project.privacy_visibility == "invited_users":
                project.access_instruction_message = self.env._(
                    "Only the project manager and the team members can access the project, plus the portal users invited as collaborators."
                )
            else:
                project.access_instruction_message = ""

    @api.depends("workflow_step_ids.rating_active")
    def _compute_show_ratings(self) -> None:
        projects_with_rating_active = (
            self.env["project.workflow.step"]
            .search_fetch(
                domain=[
                    ("project_ids", "in", self.ids),
                    ("rating_active", "=", True),
                ],
                field_names=["project_ids"],
            )
            .project_ids
        )
        for project in self:
            project.show_ratings = project in projects_with_rating_active

    @_debug.perf.timed
    def _inverse_allow_dependencies(self) -> None:
        project_with_task_dependencies_feature = self.filtered("allow_dependencies")
        projects_without_task_dependencies_feature = (
            self - project_with_task_dependencies_feature
        )
        ProjectTask = self.env["project.task"]
        if project_with_task_dependencies_feature and (
            open_tasks_with_dependencies := ProjectTask.search(
                [
                    (
                        "project_id",
                        "in",
                        project_with_task_dependencies_feature.ids,
                    ),
                    ("predecessor_ids.state", "in", ProjectTask.OPEN_STATES),
                    ("state", "in", ProjectTask.OPEN_STATES),
                ]
            )
        ):
            _debug.logic(
                "dependencies_toggled",
                action="block",
                tasks=open_tasks_with_dependencies,
            )
            open_tasks_with_dependencies.state = "blocked"
        if projects_without_task_dependencies_feature and (
            waiting_tasks := ProjectTask.search(
                [
                    (
                        "project_id",
                        "in",
                        projects_without_task_dependencies_feature.ids,
                    ),
                    ("state", "=", "blocked"),
                ]
            )
        ):
            _debug.logic("dependencies_toggled", action="unblock", tasks=waiting_tasks)
            waiting_tasks.state = "in_progress"
        self._sync_feature_groups(["allow_dependencies"])

    def _inverse_allow_milestones(self) -> None:
        self._sync_feature_groups(["allow_milestones"])

    def _inverse_allow_recurring_tasks(self) -> None:
        self._sync_feature_groups(["allow_recurring_tasks"])

    @api.model
    def _prepare_map_tasks_defaults(self, project: Self) -> dict:
        return {
            "state": "in_progress",
            "company_id": project.company_id.id,
            "project_id": project.id,
        }

    @_debug.perf.timed
    def map_tasks(self, new_project_id: int) -> bool:
        project = self.browse(new_project_id)
        tasks = (
            self.env["project.task"]
            .with_context(active_test=False)
            .search([("project_id", "=", self.id), ("parent_id", "=", False)])
        )
        _debug.pipeline(
            "map_tasks_started",
            project=self.id,
            target=project.id,
            root_tasks=len(tasks),
        )
        defaults = self._prepare_map_tasks_defaults(project)
        new_tasks = tasks.with_context(copy_project=True).copy(defaults)
        all_subtasks = new_tasks._get_all_subtasks()
        relinked = all_subtasks.filtered(lambda child: child.project_id == self)
        _debug.pipeline(
            "map_tasks_copied",
            project=self.id,
            copied=new_tasks,
            relinked=len(relinked),
            subtasks=len(all_subtasks),
        )
        relinked.write({"project_id": project.id})
        return True

    def copy_data(self, default: ValuesType | None = None) -> list[ValuesType]:
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        copy_from_template = self.env.context.get("copy_from_template")
        _debug.lifecycle(
            "copy_data",
            projects=self,
            default_keys=sorted(default),
            copy_from_template=copy_from_template,
        )
        has_project_stage_feature = False
        if copy_from_template and "phase_id" not in default:
            has_project_stage_feature = self.env.user.has_group(
                "project.group_project_stages"
            )
        for project, vals in zip(self, vals_list, strict=True):
            if project.is_template and not copy_from_template:
                vals["is_template"] = True
            if copy_from_template:
                if has_project_stage_feature:
                    vals["phase_id"] = project.phase_id.id
                for field in self._get_template_field_blacklist():
                    if field in vals and field not in default:
                        del vals[field]
            if copy_from_template or (
                not project.is_template and vals.get("is_template")
            ):
                vals["name"] = default.get("name", project.name)
            else:
                vals["name"] = default.get(
                    "name", self.env._("%s (copy)", project.name)
                )
        return vals_list

    def copy_translations(self, new, excluded=()) -> None:
        if new.name == self.name:
            super().copy_translations(new, excluded=excluded)
            return
        super().copy_translations(new, excluded=(*excluded, "name"))
        self._copy_translations_of_renamed_field(
            new, "name", lambda record, term: record.env._("%s (copy)", term)
        )

    @_debug.perf.timed
    def copy(self, default: ValuesType | None = None) -> Self:
        default = dict(default or {})
        default["milestone_ids"] = False
        copy_context = dict(
            self.env.context,
            mail_auto_subscribe_no_notify=True,
            mail_create_nosubscribe=True,
        )
        copy_context.pop("default_phase_id", None)
        new_projects = super(ProjectProject, self.with_context(copy_context)).copy(
            default=default
        )
        _debug.lifecycle("copy", projects=self, copies=new_projects)
        if "milestone_mapping" not in self.env.context:
            self = self.with_context(milestone_mapping={})
        for old_project, new_project in zip(self, new_projects, strict=True):
            _debug.pipeline(
                "copy_relations",
                project=old_project.id,
                copy=new_project.id,
                followers=len(old_project.message_follower_ids),
                milestones=old_project.allow_milestones,
                tasks="task_ids" not in default,
            )
            partner_ids_per_subtypes = defaultdict(list)
            for follower in old_project.message_follower_ids:
                partner_ids_per_subtypes[tuple(follower.subtype_ids.ids)].extend(
                    follower.partner_id.ids
                )
            for subtype_ids, partner_ids in partner_ids_per_subtypes.items():
                new_project.message_subscribe(
                    partner_ids=partner_ids, subtype_ids=list(subtype_ids)
                )
            if old_project.allow_milestones:
                new_project.milestone_ids = old_project.milestone_ids.copy().ids
            if "task_ids" not in default:
                old_project.map_tasks(new_project.id)
            if not old_project.active:
                new_project.with_context(active_test=False).task_ids.active = True
        shared_embedded_actions_mapping = self._copy_shared_embedded_actions(
            new_projects
        )
        self._copy_embedded_actions_config(
            new_projects, shared_embedded_actions_mapping
        )
        return new_projects

    @_debug.perf.timed
    def _copy_shared_embedded_actions(self, new_projects: Self) -> dict[int, int]:
        shared_embedded_actions_per_record = dict(
            self.env["ir.embedded.actions"]
            .sudo()
            ._read_group(
                domain=[
                    ("parent_res_id", "in", self.ids),
                    ("parent_res_model", "=", self._name),
                    ("user_id", "=", False),
                ],
                groupby=["parent_res_id"],
                aggregates=["id:recordset"],
            )
        )
        shared_embedded_actions_mapping = {}
        for project, new_project in zip(self, new_projects, strict=True):
            shared_embedded_actions = shared_embedded_actions_per_record.get(project.id)
            if shared_embedded_actions:
                copy_shared_embedded_actions = shared_embedded_actions.copy(
                    {"parent_res_id": new_project.id}
                )
                for original_action, copied_action in zip(
                    shared_embedded_actions,
                    copy_shared_embedded_actions,
                    strict=True,
                ):
                    shared_embedded_actions_mapping[original_action.id] = (
                        copied_action.id
                    )
                    copied_action.filter_ids = original_action.filter_ids.copy(
                        {"embedded_parent_res_id": new_project.id}
                    )
        _debug.logic(
            "shared_embedded_actions_copied",
            projects=self,
            actions=len(shared_embedded_actions_mapping),
        )
        return shared_embedded_actions_mapping

    @_debug.perf.timed
    def _copy_embedded_actions_config(
        self,
        new_projects: Self,
        shared_embedded_actions_mapping: dict | None = None,
    ) -> None:
        shared_embedded_actions_mapping = shared_embedded_actions_mapping or {}
        embedded_action_configs_per_project = dict(
            self.env["res.users.settings.embedded.action"]
            .sudo()
            ._read_group(
                [("res_id", "in", self.ids), ("res_model", "=", self._name)],
                ["res_id"],
                ["id:recordset"],
            )
        )
        valid_embedded_action_ids = self.env["ir.embedded.actions"].sudo().search(
            domain=[
                ("parent_res_model", "=", self._name),
                ("user_id", "=", False),
            ],
        ).ids + [False]
        new_embedded_actions_config_vals_list = []
        for project, new_project in zip(self, new_projects, strict=True):
            configs = embedded_action_configs_per_project.get(
                project.id, self.env["res.users.settings.embedded.action"]
            )
            config_vals_list = configs.copy_data({"res_id": new_project.id})
            for config_vals in config_vals_list:
                if config_vals["embedded_actions_visibility"]:
                    embedded_actions_visibility = [
                        shared_embedded_actions_mapping.get(action_id, action_id)
                        for action_id in [
                            False if x == "false" else int(x)
                            for x in config_vals["embedded_actions_visibility"].split(
                                ","
                            )
                        ]
                        if action_id in valid_embedded_action_ids
                    ]
                    config_vals["embedded_actions_visibility"] = ",".join(
                        "false" if action_id is False else str(action_id)
                        for action_id in embedded_actions_visibility
                    )
                if config_vals["embedded_actions_order"]:
                    embedded_actions_order = [
                        shared_embedded_actions_mapping.get(action_id, action_id)
                        for action_id in [
                            False if x == "false" else int(x)
                            for x in config_vals["embedded_actions_order"].split(",")
                        ]
                        if action_id in valid_embedded_action_ids
                    ]
                    config_vals["embedded_actions_order"] = ",".join(
                        "false" if action_id is False else str(action_id)
                        for action_id in embedded_actions_order
                    )
                new_embedded_actions_config_vals_list.append(config_vals)
        _debug.logic(
            "embedded_actions_config_copied",
            projects=self,
            user_configs=len(new_embedded_actions_config_vals_list),
        )
        self.env["res.users.settings.embedded.action"].sudo().create(
            new_embedded_actions_config_vals_list
        )

    @api.model
    def _check_date_pair(self, date_start: Any, date_end: Any) -> None:
        if bool(date_start) != bool(date_end):
            raise UserError(
                self.env._(
                    "A project's start date and end date must be set "
                    "together: define both or clear both."
                )
            )

    def _create_default_workflow_steps(self) -> None:
        stepless = self.filtered(lambda project: not project.workflow_step_ids)
        if not stepless:
            return
        _debug.lifecycle("default_workflow_step_created", projects=stepless)
        self.env["project.workflow.step"].sudo().create(
            [
                {"name": self.env._("New"), "project_ids": [Command.link(project.id)]}
                for project in stepless
            ]
        )

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                count=len(vals_list),
                keys=sorted({key for vals in vals_list for key in vals}),
                uid=self.env.uid,
            )
        caller_env = self.env
        self = self.with_context(mail_create_nosubscribe=True)
        vals_list = [dict(vals) for vals in vals_list]
        if any("label_tasks" in vals and not vals["label_tasks"] for vals in vals_list):
            task_label = self.env._("Tasks")
            for vals in vals_list:
                if "label_tasks" in vals and not vals["label_tasks"]:
                    vals["label_tasks"] = task_label
        if self.env.user.has_group("project.group_project_stages"):
            if "default_phase_id" in self.env.context:
                stage = self.env["project.phase"].browse(
                    self.env.context["default_phase_id"]
                )
                if stage.company_id:
                    for vals in vals_list:
                        if vals.get("phase_id"):
                            continue
                        vals["company_id"] = stage.company_id.id
            else:
                phase_per_company_id = {}
                for vals in vals_list:
                    if vals.get("phase_id"):
                        continue
                    company_id = vals.get("company_id") or False
                    if company_id not in phase_per_company_id:
                        phase_per_company_id[company_id] = self._get_default_phase(
                            self.env["res.company"].browse(company_id)
                        )
                    vals["phase_id"] = phase_per_company_id[company_id].id
                    _debug.logic(
                        "default_phase_set",
                        phase=vals["phase_id"],
                        company=company_id,
                    )

        for vals in vals_list:
            self._check_date_pair(
                vals.get("date_start"),
                vals.get("date_end", vals.get("date")),
            )
        with _debug.perf("create_super", cr=self.env.cr):
            projects = super().create(vals_list)
        _debug.lifecycle("created", projects=projects)
        _debug.pipeline("create_default_workflow_steps_requested", projects=projects)
        projects._create_default_workflow_steps()
        projects._mark_metrics_to_compute()
        return projects.with_env(caller_env)

    @_debug.perf.timed
    def write(self, vals: dict[str, Any]) -> bool:
        _debug.lifecycle("write", projects=self, keys=sorted(vals), uid=self.env.uid)
        vals = dict(vals)
        company_id = vals.get("company_id")
        if company_id and self.env.user.has_group("project.group_project_stages"):
            projects_already_with_company = self.filtered(
                lambda p: p.company_id.id == company_id
            )
            if projects_already_with_company:
                _debug.logic(
                    "write_company_skipped",
                    projects=projects_already_with_company,
                    company=company_id,
                )
                projects_already_with_company.write(
                    {key: value for key, value in vals.items() if key != "company_id"}
                )
                self -= projects_already_with_company

        if "last_update_status" in vals and vals["last_update_status"] != "to_define":
            _debug.pipeline(
                "write_project_update_requested",
                projects=self,
                status=vals["last_update_status"],
            )
            for project in self:
                self.env["project.update"].with_context(
                    default_project_id=project.id
                ).create(
                    {
                        "name": self.env._(
                            "Status Update - %(date)s",
                            date=fields.Date.today().strftime(
                                get_lang(self.env).date_format
                            ),
                        ),
                        "status": vals["last_update_status"],
                    }
                )
            del vals["last_update_status"]
        visibility_before = (
            {project: project.privacy_visibility for project in self}
            if vals.get("privacy_visibility")
            else {}
        )

        if {"date_start", "date_end", "date"} & vals.keys():
            for project in self:
                self._check_date_pair(
                    vals.get("date_start", project.date_start),
                    vals.get("date_end", vals.get("date", project.date_end)),
                )

        active_changed = (
            self.filtered(lambda p: p.active != bool(vals["active"]))
            if "active" in vals
            else self.browse()
        )

        with _debug.perf("write_super", cr=self.env.cr):
            res = super().write(vals) if vals else True

        if visibility_before:
            _debug.pipeline(
                "write_visibility_sync_requested",
                projects=self,
                visibility=vals["privacy_visibility"],
            )
            self._sync_access_to_privacy_visibility(visibility_before)

        if "allow_recurring_tasks" in vals and not vals["allow_recurring_tasks"]:
            recurring = self.env["project.task"].search(
                [("project_id", "in", self.ids), ("recurring_task", "=", True)]
            )
            _debug.pipeline(
                "write_recurrence_disabled", projects=self, clearing=recurring
            )
            recurring.write({"recurring_task": False})

        if active_changed:
            if vals["active"]:
                active_changed._unarchive_tasks_archived_with_project()
            else:
                active_changed._snapshot_archived_to_history()
                active_changed._archive_tasks_with_project()
            active_changed._sync_feature_groups(
                active_changed._get_used_project_features()
            )
        if "name" in vals and self.account_id:
            projects_read_group = (
                self.env["project.project"]
                .with_context(active_test=False)
                ._read_group(
                    [("account_id", "in", self.account_id.ids)],
                    ["account_id"],
                    having=[("__count", "=", 1)],
                )
            )
            analytic_account_to_update = self.env["account.analytic.account"].browse(
                [analytic_account.id for [analytic_account] in projects_read_group]
            )
            _debug.pipeline(
                "write_analytic_accounts_renamed",
                projects=self,
                accounts=analytic_account_to_update,
            )
            analytic_account_to_update.write({"name": vals["name"]})
        return res

    def _archive_tasks_with_project(self) -> None:
        tasks = self.task_ids.filtered("active")
        for project in self:
            project.archived_with_project_task_ids = project.task_ids.filtered("active")
        self.archived_tasks_recorded = True
        _debug.pipeline("tasks_archived_with_project", projects=self, tasks=tasks)
        tasks.write({"active": False})

    def _unarchive_tasks_archived_with_project(self) -> None:
        projects = self.with_context(active_test=False)
        tasks = projects.archived_with_project_task_ids
        unrecorded = projects.filtered(lambda p: not p.archived_tasks_recorded)
        tasks |= unrecorded.task_ids
        tasks = tasks.filtered(lambda t: not t.active and t.project_id in projects)
        _debug.pipeline(
            "tasks_unarchived_with_project",
            projects=self,
            tasks=tasks,
            unrecorded=unrecorded,
        )
        projects.write(
            {"archived_with_project_task_ids": False, "archived_tasks_recorded": False}
        )
        tasks.write({"active": True})

    @_debug.perf.timed
    def unlink(self) -> bool:
        _debug.lifecycle("unlink", projects=self)
        self.env["res.users.settings.embedded.action"].sudo().search(
            domain=[("res_id", "in", self.ids), ("res_model", "=", self._name)],
        ).unlink()
        deleted_per_account = defaultdict(int)
        for project in self.with_context(active_test=False):
            if project.account_id:
                deleted_per_account[project.account_id] += 1
        accounts = self.env["account.analytic.account"].concat(*deleted_per_account)
        project_counts = accounts._get_project_counts(include_archived=True)
        analytic_accounts_to_delete = accounts.filtered(
            lambda account: (
                project_counts[account.id] <= deleted_per_account[account]
                and not account._has_analytic_lines()
            )
        )
        used_features = self._get_used_project_features()
        tasks = self.with_context(active_test=False).task_ids
        _debug.pipeline(
            "unlink_cascade",
            projects=self,
            tasks=tasks,
            accounts=analytic_accounts_to_delete,
            features=used_features,
        )
        tasks.unlink()
        ProjectProject = self.env["project.project"]
        result = super().unlink()
        analytic_accounts_to_delete.unlink()
        ProjectProject._sync_feature_groups(used_features)
        return result

    def _get_fields_assignment(self) -> set[str]:
        return {"user_id"}

    def _get_assigned_users(self, values: dict[str, Any]):
        user_id = values.get("user_id")
        return (
            self.env["res.users"].browse(user_id) if user_id else self.env["res.users"]
        )

    @api.model
    def _prepare_assignment_vals(self, users) -> dict[str, Any]:
        return {"user_id": users[:1].id}

    def _message_auto_subscribe_fields(self) -> set[str]:
        return super()._message_auto_subscribe_fields() | self._get_fields_assignment()

    def _message_auto_subscribe_followers(
        self, updated_values: dict, default_subtype_ids: list[int]
    ) -> list:
        manager = self._get_assigned_users(updated_values).sudo()
        if not manager or not manager.active or not manager.partner_id:
            return super()._message_auto_subscribe_followers(
                updated_values, default_subtype_ids
            )
        return [
            (
                manager.partner_id.id,
                default_subtype_ids,
                "mail.message_user_assigned" if manager != self.env.user else False,
            )
        ]

    def message_subscribe(
        self,
        partner_ids: list[int] | None = None,
        subtype_ids: list[int] | None = None,
    ) -> bool:
        res = super().message_subscribe(
            partner_ids=partner_ids, subtype_ids=subtype_ids
        )
        if subtype_ids:
            project_subtypes = self.env["mail.message.subtype"].browse(subtype_ids)
            task_subtypes = (
                project_subtypes.mapped("parent_id")
                | project_subtypes.filtered(lambda sub: sub.internal or sub.default)
            ).ids
            if task_subtypes:
                partner_set = set(partner_ids)
                tasks_by_partners = defaultdict(lambda: self.env["project.task"])
                for task in self.task_ids:
                    partners = frozenset(task.message_partner_ids.ids) & partner_set
                    if partners:
                        tasks_by_partners[partners] |= task
                _debug.pipeline(
                    "subscribe_propagated",
                    projects=self,
                    task_groups=len(tasks_by_partners),
                    subtypes=task_subtypes,
                )
                for partners, tasks in tasks_by_partners.items():
                    tasks.message_subscribe(
                        partner_ids=list(partners),
                        subtype_ids=task_subtypes,
                    )
                self.update_ids.message_subscribe(
                    partner_ids=partner_ids, subtype_ids=subtype_ids
                )
        return res

    def message_unsubscribe(self, partner_ids: list[int] | None = None) -> None:
        _debug.pipeline("unsubscribe_propagated", projects=self, partners=partner_ids)
        self.task_ids.message_unsubscribe(partner_ids=partner_ids)
        super().message_unsubscribe(partner_ids=partner_ids)

    def _alias_get_creation_values(self) -> dict:
        values = super()._alias_get_creation_values()
        values["alias_model_id"] = self.env["ir.model"]._get("project.task").id
        if self.id:
            values["alias_defaults"] = defaults = self._prepare_alias_defaults()
            defaults["project_id"] = self.id
        return values

    @api.constrains("phase_id", "company_id")
    def _check_phase_has_same_company(self) -> None:
        for project in self:
            if (
                project.phase_id.company_id
                and project.phase_id.company_id != project.company_id
            ):
                raise UserError(
                    self.env._(
                        "This project is associated with %(project_company)s, whereas the selected stage belongs to %(stage_company)s. "
                        "There are a couple of options to consider: either remove the company designation "
                        "from the project or from the stage. Alternatively, you can update the company "
                        "information for these records to align them under the same company.",
                        project_company=project.company_id.name,
                        stage_company=project.phase_id.company_id.name,
                    )
                    if project.company_id
                    else self.env._(
                        "This project is not associated with any company, while the stage is associated with %s. "
                        "There are a couple of options to consider: either change the project's company "
                        "to align with the stage's company or remove the company designation from the stage",
                        project.phase_id.company_id.name,
                    )
                )

    @versioned_envelope
    def get_template_tasks(self) -> list:
        self.check_singleton()
        return self.env["project.task"].search_read(
            [("project_id", "=", self.id), ("is_template", "=", True)],
            ["id", "name"],
        )

    @api.model
    def _sync_feature_group_to_usage(
        self, field_name: str, group_name: str
    ) -> bool | None:
        group = self.env.ref(group_name)
        base_group_user = self.env.ref("base.group_user")
        implied = group in base_group_user.implied_ids
        has_project_field_set = bool(
            self.env["project.project"]
            .sudo()
            .search_count([(field_name, "=", True)], limit=1)
        )
        res = None

        if not implied and has_project_field_set:
            base_group_user.sudo().write({"implied_ids": [Command.link(group.id)]})
            res = True
        elif implied and not has_project_field_set:
            base_group_user.sudo().write({"implied_ids": [Command.unlink(group.id)]})
            res = False
        _debug.logic(
            "feature_group_synced",
            field=field_name,
            group=group_name,
            implied=implied,
            in_use=has_project_field_set,
            result={True: "implied", False: "removed", None: "unchanged"}[res],
        )
        return res

    def _get_project_features_mapping(self) -> dict[str, str]:
        return {
            "allow_dependencies": "project.group_project_task_dependencies",
            "allow_milestones": "project.group_project_milestone",
            "allow_recurring_tasks": "project.group_project_recurring_tasks",
        }

    def _get_used_project_features(self) -> list[str]:
        return [
            field_name
            for field_name in self._get_project_features_mapping()
            if any(self.mapped(field_name))
        ]

    @api.model
    def _sync_feature_groups(self, field_names: Collection[str]) -> None:
        for field_name, group_name in self._get_project_features_mapping().items():
            if field_name not in field_names:
                continue
            implied = self._sync_feature_group_to_usage(field_name, group_name)
            if field_name == "allow_dependencies" and implied is not None:
                self.env.ref("project.mt_task_waiting").sudo().hidden = not implied
                self.env.ref(
                    "project.mt_project_task_waiting"
                ).sudo().hidden = not implied

    @api.model
    def get_features_groups(self) -> dict[str, str]:
        if not self.env.user.has_group("project.group_project_user"):
            return {}
        return self._get_project_features_mapping()

    @api.model
    def get_features_enabled(
        self, updated_features: list[str] | None = None
    ) -> dict[str, bool]:
        if not self.env.user.has_group("project.group_project_user"):
            return {}
        return {
            field_name: self.env.user.has_group(group)
            for field_name, group in self._get_project_features_mapping().items()
            if not updated_features or field_name in updated_features
        }

    def _track_template(self, changes: Collection[str]) -> dict:
        res = super()._track_template(changes)
        project = self[0]
        if (
            self.env.user.has_group("project.group_project_stages")
            and "phase_id" in changes
            and project.phase_id.mail_template_id
            and project.phase_id.mail_template_id.model == self._name
        ):
            res["phase_id"] = (
                project.phase_id.mail_template_id,
                {
                    "auto_delete_keep_log": False,
                    "subtype_id": self.env["ir.model.data"]._xmlid_to_res_id(
                        "mail.mt_note"
                    ),
                    "email_layout_xmlid": "mail.mail_notification_light",
                },
            )
        return res

    def _track_subtype(self, init_values: dict[str, Any]) -> Self:
        self.check_singleton()
        if "phase_id" in init_values:
            return self.env.ref("project.mt_project_stage_change")
        return super()._track_subtype(init_values)

    def _mail_get_message_subtypes(self) -> Self:
        res = super()._mail_get_message_subtypes()
        if len(self) == 1:
            waiting_subtype = self.env.ref("project.mt_project_task_waiting")
            if not self.allow_dependencies and waiting_subtype in res:
                res -= waiting_subtype
        return res

    def _notify_get_recipients_groups(
        self,
        message: Any,
        model_description: str,
        msg_vals: dict | Literal[False] = False,
    ) -> list:
        groups = super()._notify_get_recipients_groups(
            message, model_description, msg_vals=msg_vals
        )
        if not self:
            return groups

        self.check_singleton()
        portal_privacy = self.privacy_visibility in ["invited_users", "portal"]
        for group_name, _group_method, group_data in groups:
            if group_name in ["portal", "portal_customer"] and not portal_privacy:
                group_data["has_button_access"] = False
            elif group_name == "portal_customer" and not self._admits_link_partner(
                self._portal_customer()
            ):
                group_data["has_button_access"] = False
        return groups

    def action_project_task_burndown_chart_report(self) -> dict:
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.action_project_task_burndown_chart_report"
        )
        action["display_name"] = self.env._("%(name)s's Burndown Chart", name=self.name)
        context = action["context"].replace("active_id", str(self.id))
        context = self.env["ir.actions.actions"]._eval_action_context(context)
        context.update(
            {
                "stage_name_and_sequence_per_id": {
                    stage.id: {"sequence": stage.sequence, "name": stage.name}
                    for stage in self.workflow_step_ids
                }
            }
        )
        action["context"] = context
        return action

    def action_view_scatter_plot(self) -> dict:
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.action_project_task_scatter"
        )
        action["display_name"] = self.env._(
            "%(name)s's Cycle Time Scatter", name=self.name
        )
        return action

    def action_find_similar_projects(self) -> dict:
        self.check_singleton()
        domain = []
        if self.tag_ids:
            domain.append(("tag_ids", "in", self.tag_ids.ids))
        if self.task_count:
            team_size = len(
                self.env["project.task"]
                .search(
                    [
                        ("project_id", "=", self.id),
                        ("user_ids", "!=", False),
                    ]
                )
                .mapped("user_ids")
            )
            if team_size:
                domain.append(("team_size", ">=", max(1, team_size - 2)))
                domain.append(("team_size", "<=", team_size + 2))
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.action_project_history"
        )
        action["display_name"] = self.env._(
            "Similar Projects to %(name)s", name=self.name
        )
        action["domain"] = domain
        return action

    def action_view_project_updates(self) -> dict:
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.project_update_all_action"
        )
        action["display_name"] = self.env._("%(name)s Dashboard", name=self.name)
        return action

    def action_view_share_project_wizard(self) -> dict:
        template = self.env.ref(
            "project.mail_template_project_sharing", raise_if_not_found=False
        )

        local_context = self.env.context | {
            "default_template_id": template.id if template else False,
            "default_email_layout_xmlid": "mail.mail_notification_light",
            "active_id": self.id,
            "active_model": "project.project",
        }
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "project.project_share_wizard_action"
        )
        if self.env.context.get("default_access_mode"):
            action["name"] = self.env._("Share Project")
        action["context"] = local_context
        return action

    def action_view_tasks(self) -> dict:
        action = (
            self.env["ir.actions.act_window"]
            .with_context(active_id=self.id)
            ._get_action_dict_by_xml_id(
                "project.act_project_project_2_project_task_all"
            )
        )
        action["display_name"] = self.name
        context = action["context"].replace("active_id", str(self.id))
        context = self.env["ir.actions.actions"]._eval_action_context(context)
        context.update(
            {
                "create": self.active,
                "active_test": self.active,
                "active_id": self.id,
                "allow_milestones": self.allow_milestones,
                "allow_dependencies": self.allow_dependencies,
            }
        )
        action["context"] = context
        if self.is_template:
            action["context"].update({"template_project": True})
            action["views"] = [
                (view_id, view_type)
                for view_id, view_type in action["views"]
                if view_type not in ("pivot", "graph")
            ]
        return action

    def action_view_all_rating(self) -> dict:
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.rating_rating_action_view_project_rating"
        )
        action["display_name"] = self.env._("%(name)s's Rating", name=self.name)
        action_context = (
            self.env["ir.actions.actions"]._eval_action_context(action["context"])
            if action["context"]
            else {}
        )
        action_context.update(self.env.context)
        action_context["search_default_filter_write_date"] = (
            "custom_write_date_last_30_days"
        )
        action_context.pop("group_by", None)
        action["domain"] = [
            ("consumed", "=", True),
            ("parent_res_model", "=", "project.project"),
            ("parent_res_id", "=", self.id),
        ]
        if self.rating_child_count == 1:
            action.update(
                {
                    "view_mode": "form",
                    "views": [
                        (view_id, view_type)
                        for view_id, view_type in action["views"]
                        if view_type == "form"
                    ],
                    "res_id": self.rating_child_ids[0].id,
                }
            )
        return dict(action, context=action_context)

    def action_view_tasks_analysis(self) -> dict:
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.action_project_task_user_tree"
        )
        action["display_name"] = self.env._("%(name)s's Tasks Analysis", name=self.name)
        action_context = (
            self.env["ir.actions.actions"]._eval_action_context(action["context"])
            if action["context"]
            else {}
        )
        action_context["search_default_project_id"] = self.id
        return dict(action, context=action_context)

    def action_view_assigned_resources(self) -> dict:
        self.check_singleton()
        task_ids = self.env["project.task"].search([("project_id", "=", self.id)]).ids
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.action_project_task_assigned_resources"
        )
        action["display_name"] = self.env._(
            "%(name)s's Assigned Resources", name=self.name
        )
        action["domain"] = [
            ("res_model", "=", "project.task"),
            ("res_id", "in", task_ids),
        ]
        return action

    def action_get_list_view(self) -> dict:
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.project_milestone_action"
        )
        action["display_name"] = self.env._("%(name)s's Milestones", name=self.name)
        return action

    def action_view_tasks_from_project_milestone(self) -> dict:
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.project_milestone_action_view_tasks"
        )
        action["display_name"] = self.env._("Tasks")
        action["domain"] = [("milestone_id", "in", self.milestone_ids.ids)]
        return action

    def action_profitability_items(
        self,
        section_name: str,
        domain: list | None = None,
        res_id: int | bool = False,
    ) -> dict:
        return {}

    @_debug.perf.timed
    def get_panel_data(self) -> dict:
        self.check_singleton()
        if not self.env.user.has_group("project.group_project_user"):
            return {}
        show_profitability = self._is_profitability_shown()
        _debug.logic(
            "panel_data",
            project=self.id,
            profitability=show_profitability,
            milestones=self.allow_milestones,
        )
        panel_data = {
            "buttons": sorted(self._get_stat_buttons(), key=lambda k: k["sequence"]),
            "currency_id": self.currency_id.id,
            "show_project_profitability_helper": show_profitability
            and self._is_profitability_helper_shown(),
            "show_milestones": self.allow_milestones,
        }
        if self.allow_milestones:
            panel_data["milestones"] = self._get_milestones()
        if show_profitability:
            profitability_items = self.with_context(
                active_test=False
            )._get_profitability_items()
            if (
                self._get_profitability_sequence_per_invoice_type()
                and profitability_items
                and "revenues" in profitability_items
                and "costs" in profitability_items
            ):
                profitability_items["revenues"]["data"] = sorted(
                    profitability_items["revenues"]["data"],
                    key=lambda k: k["sequence"],
                )
                profitability_items["costs"]["data"] = sorted(
                    profitability_items["costs"]["data"],
                    key=lambda k: k["sequence"],
                )
            panel_data["profitability_items"] = profitability_items
            panel_data["profitability_labels"] = self._get_profitability_labels()
        return panel_data

    def _get_profitability_labels(self) -> dict:
        return {}

    def _get_profitability_sequence_per_invoice_type(self) -> dict:
        return {}

    def _get_already_included_profitability_invoice_line_ids(self) -> list:
        return []

    def _is_profitability_shown(self) -> bool:
        self.check_singleton()
        return True

    def _is_profitability_helper_shown(self) -> bool:
        return self.env.user.has_group("analytic.group_analytic_accounting")

    def _get_domain_profitability_aal(self) -> list:
        return [("account_id", "in", self.account_id.ids)]

    def _get_profitability_items(self, with_action: bool = True) -> dict:
        return self._get_items_from_aal(with_action)

    def _get_items_from_aal(self, with_action: bool = True) -> dict:
        return {
            "revenues": {
                "data": [],
                "total": {"invoiced": 0.0, "to_invoice": 0.0},
            },
            "costs": {"data": [], "total": {"billed": 0.0, "to_bill": 0.0}},
        }

    def _get_milestones(self) -> dict:
        self.check_singleton()
        return {
            "data": self.milestone_ids._get_export_values_list(),
        }

    def _get_stat_buttons(self) -> list:
        self.check_singleton()
        closed_task_count = self.closed_task_count
        if self.task_count:
            number = self.env._(
                "%(closed_task_count)s / %(task_count)s (%(closed_rate)s%%)",
                closed_task_count=closed_task_count,
                task_count=self.task_count,
                closed_rate=round(100 * closed_task_count / self.task_count),
            )
        else:
            number = self.env._(
                "%(closed_task_count)s / %(task_count)s",
                closed_task_count=closed_task_count,
                task_count=self.task_count,
            )
        buttons = [
            {
                "icon": "check",
                "text": self.label_tasks,
                "number": number,
                "action_type": "object",
                "action": "action_view_tasks",
                "show": True,
                "sequence": 1,
            }
        ]
        if self.rating_child_count != 0:
            if self.rating_child_avg >= rating_data.RATING_AVG_TOP:
                icon = "smile-o text-success"
            elif self.rating_child_avg >= rating_data.RATING_AVG_OK:
                icon = "meh-o text-warning"
            else:
                icon = "frown-o text-danger"
            buttons.append(
                {
                    "icon": icon,
                    "text": self.env._("Average Rating"),
                    "number": f"{int(self.rating_child_avg) if self.rating_child_avg.is_integer() else round(self.rating_child_avg, 1)} / 5",
                    "action_type": "object",
                    "action": "action_view_all_rating",
                    "show": self.show_ratings,
                    "sequence": 15,
                }
            )
        if self.env.user.has_group("project.group_project_user"):
            buttons.append(
                {
                    "icon": "area-chart",
                    "text": self.env._("Burndown Chart"),
                    "action_type": "action",
                    "action": "project.action_project_task_burndown_chart_report",
                    "additional_context": json_dumps(
                        {
                            "active_id": self.id,
                            "stage_name_and_sequence_per_id": {
                                stage.id: {
                                    "sequence": stage.sequence,
                                    "name": stage.name,
                                }
                                for stage in self.workflow_step_ids
                            },
                        }
                    ),
                    "show": True,
                    "sequence": 60,
                }
            )
        return buttons

    @_debug.perf.timed
    def _get_profitability_values(self) -> tuple[dict, bool]:
        if not self.env.user.has_group("project.group_project_manager"):
            return {}, False
        profitability_items = self._get_profitability_items(False)
        if (
            profitability_items
            and "revenues" in profitability_items
            and "costs" in profitability_items
        ):
            profitability_items["revenues"]["data"] = sorted(
                profitability_items["revenues"]["data"],
                key=lambda k: k["sequence"],
            )
            profitability_items["costs"]["data"] = sorted(
                profitability_items["costs"]["data"],
                key=lambda k: k["sequence"],
            )
        costs = sum(profitability_items["costs"]["total"].values())
        revenues = sum(profitability_items["revenues"]["total"].values())
        margin = revenues + costs
        to_bill_to_invoice = (
            profitability_items["costs"]["total"]["to_bill"]
            + profitability_items["revenues"]["total"]["to_invoice"]
        )
        billed_invoiced = (
            profitability_items["costs"]["total"]["billed"]
            + profitability_items["revenues"]["total"]["invoiced"]
        )
        (
            expected_percentage,
            to_bill_to_invoice_percentage,
            billed_invoiced_percentage,
        ) = (0, 0, 0)
        if revenues:
            expected_percentage = formatLang(
                self.env, (margin / revenues) * 100, digits=0
            )
        if profitability_items["revenues"]["total"]["to_invoice"]:
            to_bill_to_invoice_percentage = formatLang(
                self.env,
                (
                    to_bill_to_invoice
                    / profitability_items["revenues"]["total"]["to_invoice"]
                )
                * 100,
                digits=0,
            )
        if profitability_items["revenues"]["total"]["invoiced"]:
            billed_invoiced_percentage = formatLang(
                self.env,
                (billed_invoiced / profitability_items["revenues"]["total"]["invoiced"])
                * 100,
                digits=0,
            )
        profitability_values_dict = {
            "account_id": self.account_id,
            "costs": profitability_items["costs"],
            "revenues": profitability_items["revenues"],
            "expected_percentage": expected_percentage,
            "to_bill_to_invoice_percentage": to_bill_to_invoice_percentage,
            "billed_invoiced_percentage": billed_invoiced_percentage,
            "total": {
                "costs": costs,
                "revenues": revenues,
                "margin": margin,
                "margin_percentage": formatLang(
                    self.env,
                    (
                        not float_utils.float_is_zero(costs, precision_digits=2)
                        and (margin / -costs) * 100
                    )
                    or 0.0,
                    digits=0,
                ),
            },
            "labels": self._get_profitability_labels(),
        }
        show_profitability = bool(
            profitability_values_dict.get("account_id")
            and (
                profitability_values_dict.get("costs")
                or profitability_values_dict.get("revenues")
            )
        )
        return profitability_values_dict, show_profitability

    def _is_partner_hidden(self) -> bool:
        return False

    @api.model
    def _prepare_analytic_account_vals_list(
        self, project_vals_list: list[dict]
    ) -> list[dict]:
        project_plan, _other_plans = self.env["account.analytic.plan"]._get_all_plans()
        return [
            {
                "name": project_vals.get(
                    "name", self.env._("Unknown Analytic Account")
                ),
                "company_id": project_vals.get("company_id", False),
                "partner_id": project_vals.get("partner_id", False),
                "plan_id": project_plan.id,
            }
            for project_vals in project_vals_list
        ]

    @_debug.perf.timed
    def _create_analytic_account(self) -> None:
        analytic_accounts_values = self._prepare_analytic_account_vals_list(
            self._read_format(["name", "company_id", "partner_id"], None)
        )
        analytic_accounts = self.env["account.analytic.account"].create(
            analytic_accounts_values
        )
        _debug.lifecycle(
            "analytic_accounts_created", projects=self, accounts=analytic_accounts
        )
        for project, analytic_account in zip(self, analytic_accounts, strict=True):
            project.account_id = analytic_account

    def _get_domain_projects_to_make_billable(self) -> list:
        return [("partner_id", "!=", False)]

    @api.constrains(lambda self: self._get_plan_fnames())
    def _check_account_id(self) -> None:
        pass

    def _get_domain_plan(self, plan: Any) -> list:
        return Domain.AND(
            [
                super()._get_domain_plan(plan),
                [
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=?", unquote("company_id")),
                ],
            ]
        )

    def _prepare_account_node_context(self, plan: Any) -> dict:
        return {
            **super()._prepare_account_node_context(plan),
            "default_company_id": unquote("company_id"),
        }

    @_debug.perf.timed
    def _sync_access_to_privacy_visibility(self, visibility_before: dict) -> None:
        shared = ("invited_users", "portal")
        for project in self:
            old_visibility = visibility_before[project]
            if project.privacy_visibility == old_visibility:
                continue
            _debug.logic(
                "privacy_visibility_changed",
                project=project.id,
                old=old_visibility,
                new=project.privacy_visibility,
            )
            if project.privacy_visibility in shared and old_visibility not in shared:
                project._add_collaborators(project.partner_id, access_mode="view")
                for partner, tasks in (
                    project.task_ids.filtered("partner_id")
                    .grouped("partner_id")
                    .items()
                ):
                    tasks.message_subscribe(partner_ids=partner.ids)
            elif old_visibility in shared and project.privacy_visibility not in shared:
                portal_users = project.message_partner_ids.user_ids.filtered("share")
                _debug.pipeline(
                    "visibility_closed_portal_unsubscribed",
                    project=project.id,
                    portal_users=portal_users,
                )
                project.message_unsubscribe(partner_ids=portal_users.partner_id.ids)
                project.task_ids._unsubscribe_portal_users()
                project.task_ids._portal_revoke_tokens()
                project._portal_revoke_tokens()

    def _is_project_sharing_accessible(self) -> bool:
        self.check_singleton()
        if self.privacy_visibility not in ["invited_users", "portal"]:
            _debug.logic(
                "project_sharing_accessible",
                project=self.id,
                visibility=self.privacy_visibility,
                accessible=False,
            )
            return False
        if self.env.user._is_portal():
            accessible = bool(
                self.env["project.collaborator"].search_count(
                    [
                        ("project_id", "=", self.sudo().id),
                        ("is_current_user_collaboration", "=", True),
                    ],
                    limit=1,
                )
            )
            _debug.logic(
                "project_sharing_accessible",
                project=self.id,
                portal_user=self.env.uid,
                accessible=accessible,
            )
            return accessible
        return self.env.user._is_internal()

    def _admits_link_partner(self, partner: Any, task: Any = None) -> bool:
        self.check_singleton()
        project = self.env["ir.access"]._access_evaluator(self._name).browse(self.id)
        visibility = project.privacy_visibility
        if visibility == "followers":
            admitted = False
        elif visibility == "invited_users":
            Collaborator = project.env["project.collaborator"]
            admitted = bool(partner) and (
                bool(
                    Collaborator.search_count(
                        Domain("project_id", "=", project.id)
                        & Domain("partner_id", "=", partner.id)
                        & Domain.custom(to_sql=Collaborator._live_sql),
                        limit=1,
                    )
                )
                or bool(
                    task and partner in task.with_env(project.env).message_partner_ids
                )
            )
        else:
            admitted = True
        _debug.logic(
            "link_partner_admitted",
            project=self.id,
            task=task.id if task else None,
            visibility=visibility,
            partner=partner.id,
            admitted=admitted,
        )
        return admitted

    def _add_collaborators(
        self, partners: Any, access_mode: str = "advanced_edit"
    ) -> None:
        self.check_singleton()
        new_collaborators = self._get_new_collaborators(partners)
        _debug.lifecycle(
            "collaborators_added",
            project=self.id,
            partners=partners,
            new=new_collaborators,
            mode=access_mode,
        )
        if not new_collaborators:
            return
        self.write(
            {
                "collaborator_ids": [
                    Command.create(
                        {
                            "partner_id": collaborator.id,
                            "access_mode": access_mode,
                        }
                    )
                    for collaborator in new_collaborators
                ],
            }
        )

    def _revoke_collaborator_access(self, partners: Any) -> None:
        self.check_singleton()
        tasks = self.with_context(active_test=False).task_ids
        _debug.lifecycle(
            "collaborator_access_revoked", project=self.id, partners=partners
        )
        self.message_unsubscribe(partner_ids=partners.ids)
        tasks.filtered(lambda task: not task.active).message_unsubscribe(
            partner_ids=partners.ids
        )
        reason = "the partner is no longer a collaborator of the project"
        Link = self.env["access.link"].with_privilege(
            "base.privilege_manage_links", reason=reason
        )
        partner_domain = Domain("partner_id", "in", partners.ids)
        Link._revoke_record_links(self, reason, domain=partner_domain)
        Link._revoke_record_links(tasks, reason, domain=partner_domain)
        self.invalidate_recordset(["access_token"])
        tasks.invalidate_recordset(["access_token"])

    def _get_new_collaborators(self, partners: Any) -> list:
        self.check_singleton()
        return partners.filtered(
            lambda partner: (
                partner not in self.collaborator_ids.partner_id
                and partner.partner_share
            )
        )

    def _thread_to_store(
        self,
        store: Store,
        field_specs: list[StoreFieldSpec],
        *,
        request_list: list[str] | None = None,
    ) -> None:
        super()._thread_to_store(store, field_specs, request_list=request_list)
        if request_list and "followers" in request_list:
            store.add(
                self,
                {
                    "collaborator_ids": Store.Many(
                        self.sudo().collaborator_ids.partner_id, []
                    )
                },
                as_thread=True,
            )

    @api.depends("task_count", "open_task_count")
    def _compute_task_completion_percentage(self) -> None:
        for task in self:
            task.task_completion_percentage = (
                task.task_count and 1 - task.open_task_count / task.task_count
            )

    def _get_template_to_project_warnings(self) -> list:
        self.check_singleton()
        return []

    def action_confirm_template_to_project(self, callbacks: dict[str, Any]) -> None:
        self.check_singleton()
        pass

    def _get_template_to_project_confirmation_callbacks(self) -> dict:
        self.check_singleton()
        return {}

    def action_toggle_project_template_mode(self) -> dict | None:
        self.check_singleton()
        config = {
            "params": {
                "project_id": self.id,
            },
        }
        if self.is_template:
            config["tag"] = "project_template_show_undo_confirmation_dialog"
            if callbacks := self._get_template_to_project_confirmation_callbacks():
                config["params"]["callbacks"] = callbacks
            if warning_messages := self._get_template_to_project_warnings():
                config["params"]["message"] = self.env._(
                    "%(warning_messages)s\nAre you sure you want to continue?",
                    warning_messages="\n".join(warning_messages),
                )
            else:
                config["params"]["message"] = self.env._(
                    "This project is currently a template. Would you like to convert it back into a regular project?",
                )
        else:
            config["tag"] = "project_to_template_redirection_action"
        return {
            "type": "ir.actions.client",
            **config,
        }

    def action_undo_create_template_from_project(
        self, template_id: int, callbacks: dict[str, Any]
    ) -> dict:
        self.check_singleton()
        self.browse(template_id).filtered("is_template").unlink()
        if callbacks.get("unarchive_project"):
            self.action_unarchive()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Template converted back to regular project."),
            },
        }

    def _get_template_from_project_undo_callbacks(self) -> dict:
        self.check_singleton()
        return {"unarchive_project": True} if self.active else {}

    def action_create_template_from_project(self) -> dict:
        self.check_singleton()
        template = self.copy(default={"is_template": True, "partner_id": False})
        _debug.lifecycle("template_created", project=self.id, template=template.id)
        template._update_template_mode(True)
        template.message_post(body=self.env._("Template created from %s.", self.name))
        callbacks = self._get_template_from_project_undo_callbacks()
        if self.active:
            _debug.lifecycle("template_source_archived", project=self.id)
            self.action_archive()
        return {
            "type": "ir.actions.client",
            "tag": "project_template_show_notification",
            "params": {
                "project_id": template.id,
                "undo_method": "action_undo_create_template_from_project",
                "undo_args": [self.id, template.id, callbacks],
                "removes_record": True,
            },
        }

    def action_undo_convert_to_template(
        self, callbacks: dict[str, Any] | None = None
    ) -> dict | None:
        self.check_singleton()
        self._update_template_mode(False)
        self.message_post(
            body=self.env._("Template converted back to regular project.")
        )
        if callbacks:
            self.action_confirm_template_to_project(callbacks)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Template converted back to regular project."),
                "next": {
                    "type": "ir.actions.client",
                    "tag": "soft_reload",
                },
            },
        }

    def _update_template_mode(self, is_template: bool) -> None:
        self.check_singleton()
        _debug.lifecycle(
            "template_mode_updated", project=self.id, is_template=is_template
        )
        self.is_template = is_template
        if not is_template:
            self.task_ids.role_ids = False

    @api.model
    def _get_template_default_context_whitelist(self) -> list[str]:
        return [
            "allow_milestones",
        ]

    @api.model
    def _get_template_field_blacklist(self) -> list[str]:
        return [
            "partner_id",
        ]

    @_debug.perf.timed
    def action_create_from_template(
        self, values: dict | None = None, role_to_users_mapping: Any = None
    ) -> Self:
        self.check_singleton()
        values = dict(values or {})
        _debug.lifecycle("create_from_template", template=self.id, keys=sorted(values))

        if self.date_start and self.date:
            if not values.get("date_start"):
                values["date_start"] = fields.Date.today()
            if not values.get("date"):
                values["date"] = values["date_start"] + (self.date - self.date_start)

        default = {
            key.removeprefix("default_"): value
            for key, value in self.env.context.items()
            if key.startswith("default_")
            and key.removeprefix("default_")
            in self._get_template_default_context_whitelist()
        } | values
        project = (
            self.with_context(copy_from_template=True, copy_from_project_template=True)
            .copy(default=default)
            .with_env(self.env)
        )
        _debug.pipeline(
            "created_from_template",
            template=self.id,
            project=project.id,
            tasks=len(project.task_ids),
        )
        project.message_post(
            body=self.env._("Project created from template %(name)s.", name=self.name)
        )

        if role_to_users_mapping and (
            mapping := role_to_users_mapping.filtered(lambda entry: entry.user_ids)
        ):
            for new_task in project.task_ids:
                for entry in mapping:
                    if entry.role_id in new_task.role_ids:
                        new_task.user_ids |= entry.user_ids

        project.task_ids.role_ids = False

        tasks_to_schedule = self.env["project.task"]
        first_possible_date_per_task = {}
        if project.date_start and self.date_start:
            delta = project.date_start - self.date_start
            project_start_datetime = datetime.combine(project.date_start, time.min)
            project_end_datetime = datetime.combine(
                project.date + timedelta(days=1), time.min
            )
            for original_task, copied_task in self._get_template_task_pairs(project):
                if original_task.date_start:
                    first_possible_date_per_task[copied_task.id] = (
                        original_task.date_start + delta
                    )
                    tasks_to_schedule += copied_task
        else:
            project_start_datetime = datetime.combine(
                project.date_start or fields.Date.today(), time.min
            )
            project_end_datetime = project_start_datetime + timedelta(days=365)
            for original_task, copied_task in self._get_template_task_pairs(project):
                if original_task.date_start:
                    tasks_to_schedule += copied_task
        _debug.pipeline(
            "template_tasks_scheduled",
            project=project.id,
            tasks=tasks_to_schedule,
            start=project_start_datetime,
            end=project_end_datetime,
            pinned=len(first_possible_date_per_task),
        )
        tasks_to_schedule._schedule_tasks(
            {
                "date_start": datetime.strftime(
                    project_start_datetime, "%Y-%m-%d %H:%M:%S"
                ),
                "date_end": datetime.strftime(
                    project_end_datetime, "%Y-%m-%d %H:%M:%S"
                ),
            },
            project_end_datetime,
            first_possible_date_per_task=first_possible_date_per_task,
        )
        return project

    def _get_template_task_pairs(self, project: Self) -> list[tuple[Any, Any]]:
        Task = self.env["project.task"].with_context(active_test=False)
        root_domain = [("parent_id", "=", False)]
        originals = Task.search([("project_id", "=", self.id), *root_domain])
        copies = Task.search([("project_id", "=", project.id), *root_domain])
        task_mapping, _dependencies = originals._get_task_mapping_and_dependencies(
            copies
        )
        _debug.logic(
            "template_task_pairs",
            template=self.id,
            project=project.id,
            pairs=len(task_mapping),
        )
        return [
            (Task.browse(original_id), copy)
            for original_id, copy in task_mapping.items()
        ]
