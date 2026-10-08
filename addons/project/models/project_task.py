import logging
import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Collection
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal, Self

from dateutil.relativedelta import relativedelta
from lxml import html

from odoo import SUPERUSER_ID, api, fields, models, tools
from odoo.api import ValuesType
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command, Date, Domain
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals
from odoo.tools import (
    SQL,
    LazyTranslate,
    escape_psql,
    float_compare,
    float_is_zero,
    format_list,
    frozendict,
    html_sanitize,
    topological_sort,
)
from odoo.tools.date_utils import get_intervals_hours, localized

from odoo.addons.base.models.mixin_recurrence_rule import (
    REPEAT_TYPE_SELECTION,
    REPEAT_UNIT_SELECTION,
)
from odoo.addons.html_editor.tools import handle_history_divergence
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.rating.models import rating_data
from odoo.addons.resource.models.utils import filter_domain_leaf, split_at_midnight

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)
_lt = LazyTranslate(__name__)

PROJECT_TASK_READABLE_FIELDS = {
    "id",
    "active",
    "priority",
    "project_id",
    "display_in_project",
    "allow_dependencies",
    "subtask_count",
    "email_from",
    "create_date",
    "write_date",
    "company_id",
    "displayed_image_id",
    "display_name",
    "portal_user_names",
    "user_ids",
    "display_parent_task_button",
    "current_user_same_company_partner",
    "allow_recurring_tasks",
    "allow_milestones",
    "milestone_id",
    "has_late_and_unreached_milestone",
    "date_assign",
    "successor_ids",
    "message_is_follower",
    "recurring_task",
    "closed_subtask_count",
    "successor_count",
    "predecessor_ids",
    "predecessor_count",
    "repeat_interval",
    "repeat_unit",
    "repeat_type",
    "repeat_until",
    "recurrence_id",
    "recurring_count",
    "duration_tracking",
    "display_follow_button",
    "is_template",
    "has_template_ancestor",
    "has_project_template",
    "step_color",
    "deadline_met",
    "cd3_score",
    "access_url",
    "date_last_status_change",
    "is_closed",
    "lost_reason_id",
}

PROJECT_TASK_WRITABLE_FIELDS = {
    "name",
    "description",
    "partner_id",
    "date_start",
    "date_end",
    "tag_ids",
    "sequence",
    "step_id",
    "child_ids",
    "color",
    "parent_id",
    "priority",
    "state",
}

CLOSED_STATES = {
    "done": "Done",
    "canceled": "Cancelled",
}

DELIVERED_STATES = ("done",)

STATES_RESET_ON_STEP_CHANGE = ("approved", "changes_requested")

UNSTARTED_STATES = ("todo", "blocked")

START_CONSTRAINED_TYPES = ("fs", "ss")

FINISH_ANCHORED_TYPES = ("fs", "ff")


class ProjectTask(models.Model):
    _name = "project.task"
    _description = "Task"
    _access_residual_class = "project.task_portal_hidden"
    _date_name = "date_assign"
    _inherit = [
        "mixin.html.field.history",
        "mixin.mail.thread.cc",
        "mixin.mail.activity",
        "mixin.mail.tracking.duration",
        "mixin.portal",
        "mixin.rating",
        "mixin.recurrence.occurrence",
        "mixin.resource.allocation",
    ]
    _mail_post_access = "read"
    _mail_thread_customer = True
    _order = "priority desc, sequence, date_end asc, id desc"
    _primary_email = "email_from"
    _systray_view = "list"
    _track_duration_field = "step_id"
    _track_duration_last_update_field = "date_last_status_change"
    _access_anchors = frozendict(
        {
            "owner": "user_ids",
            "partner": "message_partner_ids",
        }
    )

    def _get_fields_versioned(self) -> list[str]:
        return [ProjectTask.description.name]

    @api.model
    def _get_default_partner_id(self, project=None, parent=None) -> int | bool:
        if parent and parent.partner_id:
            return parent.partner_id.id
        if project and project.partner_id:
            return project.partner_id.id
        return False

    def _default_step_id(self) -> int | bool:
        project_id = self.env.context.get("default_project_id")
        if not project_id and (parent_id := self.env.context.get("default_parent_id")):
            project_id = self.browse(parent_id).project_id.id
        return self._get_default_step_id(project_id)

    @api.model
    def _get_default_step_id(self, project_id: int | bool) -> int | bool:
        if not project_id:
            return False
        return self.browse().get_step_id(project_id, order="fold, sequence, id")

    @api.model
    def _default_user_ids(self) -> tuple | list[int]:
        return (
            self.env.user.ids
            if any(
                key in self.env.context
                for key in (
                    "default_triage_ids",
                    "default_triage_id",
                )
            )
            else ()
        )

    @api.model
    def _default_company_id(self) -> bool:
        if self.env.context.get("default_project_id"):
            return (
                self.env["project.project"]
                .browse(self.env.context["default_project_id"])
                .company_id
            )
        return False

    @api.model
    def _read_group_step_ids(self, stages: Self, domain: list) -> Self:
        search_domain = [("id", "in", stages.ids)]
        if (
            "default_project_id" in self.env.context
            and not self.env.context.get("subtask_action")
            and "project_kanban" in self.env.context
        ):
            search_domain = [
                "|",
                ("project_ids", "=", self.env.context["default_project_id"]),
            ] + search_domain

        step_ids = stages._search(search_domain, order=stages._order)
        return stages.browse(step_ids)

    @api.model
    def _read_group_triage_ids(self, stages: Self, domain: list) -> Self:
        return stages.search(
            ["|", ("id", "in", stages.ids), ("user_id", "=", self.env.user.id)]
        )

    project_id = fields.Many2one(
        comodel_name="project.project",
        compute="_compute_project_id",
        precompute=True,
        recursive=True,
        change_default=True,
        store=True,
        index=True,
        readonly=False,
        falsy_value_label=_lt("🔒 Private"),
        domain="['|', ('company_id', '=', False), ('company_id', '=?',  company_id)]",
        tracking=True,
    )
    project_privacy_visibility = fields.Selection(
        related="project_id.privacy_visibility",
        string="Project Visibility",
        tracking=False,
    )
    display_in_project = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_in_project",
        store=True,
    )
    task_properties = fields.Properties(
        definition="project_id.task_properties_definition",
        string="Properties",
        copy=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        recursive=True,
        default=lambda self: self._default_company_id(),
        store=True,
        copy=True,
        readonly=False,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        compute="_compute_partner_id",
        recursive=True,
        store=True,
        index="btree_not_null",
        readonly=False,
        domain="['|', ('company_id', '=?', company_id), ('company_id', '=', False)]",
        tracking=True,
    )
    phone_ids = fields.Many2many(
        comodel_name="phone.number",
        relation="project_task_phone_number_rel",
        column1="task_id",
        column2="phone_number_id",
        string="Contact Numbers",
        compute="_compute_phone_ids",
        inverse="_inverse_phone_ids",
        store=True,
        copy=False,
        readonly=False,
    )
    partner_phones_editable = fields.Boolean(
        export_string_translation=False,
        compute="_compute_partner_phones_editable",
    )
    name = fields.Char(
        string="Title",
        index="trigram",
        required=True,
        tracking=True,
    )
    active = fields.Boolean(
        export_string_translation=False,
        default=True,
    )
    sequence = fields.Integer(
        export_string_translation=False,
        default=10,
    )
    description = fields.Html(sanitize_attributes=False)
    color = fields.Integer(
        string="Color Index",
        export_string_translation=False,
    )
    create_date = fields.Datetime(
        string="Created On",
        index=True,
        readonly=True,
    )
    write_date = fields.Datetime(
        string="Last Updated On",
        readonly=True,
    )
    date_closed = fields.Datetime(
        string="Closed Date",
        compute="_compute_date_closed",
        store=True,
        index=True,
        copy=False,
        readonly=False,
        help="When the task actually reached a closed state. Derived from "
        "``state``, the single closure signal every metric reads.",
    )
    date_assign = fields.Datetime(
        string="Assigning Date",
        copy=False,
        readonly=True,
        help="When the task went from no assignee to some; cleared when its last "
        "assignee is removed and stamped again on the next assignment.",
    )
    date_first_assign = fields.Datetime(
        string="First Assigning Date",
        compute="_compute_date_first_assign",
        store=True,
        copy=False,
        readonly=True,
        help="When the task first got an assignee. Written once, never cleared: "
        "queue and cycle time are measured from it.",
    )
    date_start = fields.Datetime(
        string="Start date",
        copy=False,
        tracking=True,
    )
    date_end = fields.Datetime(
        string="Deadline",
        index=True,
        copy=False,
        tracking=True,
    )
    _planned_dates_check = models.Constraint(
        "CHECK ((date_start <= date_end))",
        "The planned start date must be before the planned end date.",
    )
    date_start_effective = fields.Datetime(
        compute="_compute_date_start_effective",
        inverse="_inverse_date_start_effective",
        search="_search_date_start_effective",
    )
    planning_overlap = fields.Html(
        export_string_translation=False,
        compute="_compute_planning_overlap",
        search="_search_planning_overlap",
    )
    dependency_warning = fields.Html(
        export_string_translation=False,
        compute="_compute_dependency_warning",
        search="_search_dependency_warning",
        compute_sudo=True,
    )

    priority = fields.Selection(
        selection=[
            ("0", "Normal"),
            ("1", "Important"),
            ("2", "High"),
            ("3", "Urgent"),
        ],
        default="0",
        index=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("todo", "To Do"),
            ("in_progress", "In Progress"),
            ("changes_requested", "Changes Requested"),
            ("approved", "Approved"),
            *CLOSED_STATES.items(),
            ("blocked", "Waiting"),
        ],
        compute="_compute_state",
        inverse="_inverse_state",
        precompute=True,
        recursive=True,
        store=True,
        index=True,
        copy=False,
        readonly=False,
        required=True,
        tracking=True,
    )
    is_closed = fields.Boolean(
        string="Closed state",
        compute="_compute_is_closed",
        search="_search_is_closed",
    )
    lost_reason_id = fields.Many2one(
        comodel_name="loss.reason",
        index=True,
        domain=[("scope", "in", [False, "task"])],
        ondelete="restrict",
        tracking=True,
    )

    step_id = fields.Many2one(
        comodel_name="project.workflow.step",
        string="Workflow Step",
        compute="_compute_step_id",
        precompute=True,
        default=lambda self: self._default_step_id(),
        store=True,
        index=True,
        readonly=False,
        group_expand="_read_group_step_ids",
        domain="[('project_ids', '=', project_id)]",
        ondelete="restrict",
        tracking=True,
    )
    step_color = fields.Integer(
        related="step_id.color",
        string="Step Color",
        export_string_translation=False,
    )
    rating_active = fields.Boolean(
        related="step_id.rating_active",
        string="Step Rating Status",
    )
    date_last_status_change = fields.Datetime(
        string="Last Status Change",
        index=True,
        copy=False,
        readonly=True,
        help="Date on which the state of your task has last been modified.\n"
        "Based on this information you can identify tasks that are stalling and get statistics on the time it usually takes to move tasks from one stage/state to another.",
    )

    role_ids = fields.Many2many(
        comodel_name="resource.role",
        string="Project Roles",
        help="When you create a project from a template, you can choose which employee takes each role. These employees will be added to the tasks, along with anyone already assigned.",
    )
    user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="project_task_user_rel",
        column1="task_id",
        column2="user_id",
        string="Assignees",
        default=lambda self: self._default_user_ids(),
        falsy_value_label=_lt("👤 Unassigned"),
        domain="[('share', '=', False), ('active', '=', True)]",
        context={"active_test": False},
        tracking=True,
    )
    tag_ids = fields.Many2many(
        comodel_name="project.tags",
        string="Tags",
    )

    scheduled_hours = fields.Float(
        string="Working Duration",
        compute="_compute_scheduled_hours",
        store=True,
        help="Working hours within the task's date range, computed against "
        "the company calendar.  PMBOK: Activity Duration in working time "
        "units.  One person at 100%% allocation could cover this many hours.",
    )
    planned_resources = fields.Integer(
        default=1,
        tracking=True,
        help="Number of parallel resources the PM expects to need to deliver "
        "this task in its scheduled window.  Multiplies scheduled_hours to "
        "derive total effort (planned_hours).  Example: 2-day window (16h) "
        "with planned_resources=2 -> 32h effort = work for two people in "
        "parallel.  PMBOK: planned resource units.",
    )
    _planned_resources_positive = models.Constraint(
        "CHECK (planned_resources > 0)",
        "Planned Resources must be greater than zero.",
    )
    planned_hours = fields.Float(
        compute="_compute_planned_hours",
        inverse="_inverse_planned_hours",
        store=True,
        readonly=False,
        help="Estimated person-hours to complete the task.  Auto-derived as "
        "scheduled_hours x planned_resources x (allocated_percentage / 100); "
        "user can override.  PMBOK: Activity Effort / Work (scope baseline).",
    )
    planned_hours_manual = fields.Boolean(
        string="Planned Hours Overridden",
        export_string_translation=False,
        copy=False,
        help="Set when a user writes a Planned Hours that contradicts the PMBOK "
        "formula, so the formula stops overwriting their estimate. Cleared by "
        "writing back the value the formula would produce.",
    )
    allocated_hours = fields.Float(
        tracking=True,
        help="Working hours committed across all assigned employees "
        "(sum of reservation_ids.allocated_hours).  PMBOK: Resource "
        "Assignment Work / total person-hours.",
    )
    allocation_state = fields.Selection(
        selection=[
            ("unestimated", "Unestimated"),
            ("unallocated", "Unallocated"),
            ("under_allocated", "Under-Allocated"),
            ("allocated", "Allocated"),
            ("over_allocated", "Over-Allocated"),
        ],
        string="Allocation Status",
        compute="_compute_allocation_state",
        store=True,
        help="Resource allocation health relative to plan.  Tracks whether "
        "the task has enough employees committed to cover its planned "
        "effort.  Operational signal for PMs.  Pattern analog to "
        "invoice_state on sale.order.",
    )
    subtask_planned_hours = fields.Float(
        string="Sub-tasks Planned Hours",
        export_string_translation=False,
        compute="_compute_subtask_planned_hours",
        help="Sum of the planned hours for all the sub-tasks (and their own sub-tasks) linked to this task. Usually less than or equal to the planned hours of this task.",
    )
    portal_user_names = fields.Char(
        export_string_translation=False,
        compute="_compute_portal_user_names",
        search="_search_portal_user_names",
        compute_sudo=True,
    )
    triage_ids = fields.Many2many(
        comodel_name="project.triage",
        relation="project_task_triage",
        column1="task_id",
        column2="triage_id",
        string="Personal Triage Buckets",
        export_string_translation=False,
        copy=False,
        readonly=True,
        group_expand="_read_group_triage_ids",
        domain="[('user_id', '=', uid)]",
        ondelete="restrict",
    )
    personal_triage_id = fields.Many2one(
        comodel_name="project.task.triage",
        string="Personal Stage State",
        compute="_compute_personal_triage_id",
        search="_search_personal_triage_id",
        compute_sudo=False,
        group_expand="_read_group_triage_ids",
        help="The current user's personal stage.",
    )
    triage_id = fields.Many2one(
        comodel_name="project.triage",
        related="personal_triage_id.triage_id",
        string="Personal Triage",
        store=False,
        readonly=False,
        group_expand="_read_group_triage_ids",
        domain="[('user_id', '=', uid)]",
        group_by_field="triage_ids",
        help="The current user's personal triage bucket.",
    )
    email_from = fields.Char()
    email_cc = fields.Char(
        help="Email addresses that were in the CC of the incoming emails from this task and that are not currently linked to an existing customer."
    )

    attachment_ids = fields.One2many(
        comodel_name="ir.attachment",
        string="Attachments",
        export_string_translation=False,
        compute="_compute_attachment_ids",
        help="Attachments that don't come from a message",
    )
    displayed_image_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Cover Image",
        index="btree_not_null",
        domain="[('res_model', '=', 'project.task'), ('res_id', '=', id), ('mimetype', 'ilike', 'image')]",
    )

    allow_dependencies = fields.Boolean(
        related="project_id.allow_dependencies",
        export_string_translation=False,
    )
    parent_id = fields.Many2one(
        comodel_name="project.task",
        string="Parent Task",
        inverse="_inverse_parent_id",
        index=True,
        domain="['!', ('id', 'child_of', id)]",
        tracking=True,
    )
    child_ids = fields.One2many(
        comodel_name="project.task",
        inverse_name="parent_id",
        string="Sub-tasks",
        export_string_translation=False,
        domain="[('recurring_task', '=', False)]",
    )
    subtask_count = fields.Integer(
        string="Sub-task Count",
        export_string_translation=False,
        compute="_compute_subtask_counts",
    )
    closed_subtask_count = fields.Integer(
        string="Closed Sub-tasks Count",
        export_string_translation=False,
        compute="_compute_subtask_counts",
    )
    subtask_completion_percentage = fields.Float(
        export_string_translation=False,
        compute="_compute_subtask_completion_percentage",
    )
    predecessor_ids = fields.Many2many(
        comodel_name="project.task",
        relation="project_task_dependency",
        column1="task_id",
        column2="depends_on_id",
        string="Blocked By",
        copy=False,
        domain="[('project_id', '!=', False), ('id', '!=', id)]",
        tracking=True,
    )
    predecessor_count = fields.Integer(
        string="Depending on Tasks",
        compute="_compute_predecessor_counts",
        compute_sudo=True,
    )
    closed_predecessor_count = fields.Integer(
        string="Closed Depending on Tasks",
        compute="_compute_predecessor_counts",
        compute_sudo=True,
    )
    successor_ids = fields.Many2many(
        comodel_name="project.task",
        relation="project_task_dependency",
        column1="depends_on_id",
        column2="task_id",
        string="Block",
        export_string_translation=False,
        copy=False,
        domain="[('project_id', '!=', False), ('id', '!=', id)]",
    )
    successor_count = fields.Integer(
        string="Dependent Tasks",
        export_string_translation=False,
        compute="_compute_successor_count",
    )
    dependency_ids = fields.One2many(
        comodel_name="project.task.dependency",
        inverse_name="task_id",
        string="Dependency Details",
        export_string_translation=False,
        help="Typed dependencies with FS/SS/FF/SF and lag.",
    )
    dependent_on_me_ids = fields.One2many(
        comodel_name="project.task.dependency",
        inverse_name="depends_on_id",
        string="Tasks Depending on Me",
        export_string_translation=False,
    )

    cpm_date_earliest_start = fields.Datetime(
        string="Earliest Start",
        export_string_translation=False,
        copy=False,
        help="Computed by critical path analysis (forward pass).",
    )
    cpm_date_latest_start = fields.Datetime(
        string="Latest Start",
        export_string_translation=False,
        copy=False,
        help="Computed by critical path analysis (backward pass).",
    )
    total_float = fields.Float(
        string="Total Float (hours)",
        export_string_translation=False,
        copy=False,
        help="Latest Start - Earliest Start. Zero = critical path.",
    )
    is_critical_path = fields.Boolean(
        string="On Critical Path",
        export_string_translation=False,
        copy=False,
        help="True when total_float is zero (no scheduling slack).",
    )
    cpm_date_start = fields.Datetime(
        string="CPM Start",
        export_string_translation=False,
        copy=False,
        help="Calendar-aware start date computed by critical path analysis. "
        "Distinct from date_start (the user-entered scheduled start).",
    )
    cpm_date_end = fields.Datetime(
        string="CPM End",
        export_string_translation=False,
        copy=False,
        help="Calendar-aware end date computed by critical path analysis. "
        "Distinct from date_end (the user-entered deadline) and from "
        "date_closed (actual completion).",
    )

    is_overallocated = fields.Boolean(
        string="Overallocated Assignee",
        export_string_translation=False,
        compute="_compute_is_overallocated",
        help="True when any of this task's reservations conflicts in time "
        "with another reservation of the same resource summing more "
        "than 100% allocation (PMBOK concurrent overcommit).",
    )

    queue_time_hours = fields.Float(
        string="Queue Time (hours)",
        digits=(16, 2),
        compute="_compute_elapsed",
        store=True,
        aggregator="avg",
        help="Working hours from task creation to first assignment.",
    )
    queue_time_days = fields.Float(
        string="Queue Time (days)",
        compute="_compute_elapsed",
        store=True,
        aggregator="avg",
        help="Working days from task creation to first assignment.",
    )
    lead_time_hours = fields.Float(
        string="Lead Time (hours)",
        digits=(16, 2),
        compute="_compute_elapsed",
        store=True,
        aggregator="avg",
        help="Working hours from task creation to closure. Includes queue wait.",
    )
    lead_time_days = fields.Float(
        string="Lead Time (days)",
        compute="_compute_elapsed",
        store=True,
        aggregator="avg",
        help="Working days from task creation to closure. Includes queue wait.",
    )
    cycle_time_hours = fields.Float(
        string="Cycle Time (hours)",
        digits=(16, 2),
        compute="_compute_elapsed",
        store=True,
        aggregator="avg",
        help="Working hours from first assignment to closure. Excludes queue wait.",
    )
    cycle_time_days = fields.Float(
        string="Cycle Time (days)",
        compute="_compute_elapsed",
        store=True,
        aggregator="avg",
        help="Working days from first assignment to closure. Excludes queue wait.",
    )

    deadline_met = fields.Selection(
        selection=[("met", "Met"), ("missed", "Missed")],
        string="Deadline Result",
        export_string_translation=False,
        compute="_compute_deadline_met",
        store=True,
        help="Whether this task was closed on or before its deadline. "
        "Empty when the task has no deadline or is not yet closed — a "
        "distinct case from 'missed', which a Boolean could not represent.",
    )

    cost_of_delay = fields.Float(
        string="Cost of Delay",
        tracking=True,
        help="Estimated weekly cost of not completing this task (in currency). "
        "Used to compute CD3 score for value-based prioritization.",
    )
    cd3_score = fields.Float(
        string="CD3 Score",
        export_string_translation=False,
        compute="_compute_cd3_score",
        store=True,
        help="Cost of Delay Divided by Duration (CD3). Higher = do first. "
        "Computed as cost_of_delay / planned_hours when both are set.",
    )

    sprint_id = fields.Many2one(
        comodel_name="project.sprint",
        index="btree_not_null",
        copy=False,
        domain="[('project_id', '=', project_id)]",
        tracking=True,
    )
    use_sprints = fields.Boolean(
        related="project_id.use_sprints",
        export_string_translation=False,
    )
    story_points = fields.Float(
        help="Relative effort estimate. Used for sprint velocity tracking."
    )

    allow_recurring_tasks = fields.Boolean(
        related="project_id.allow_recurring_tasks",
        export_string_translation=False,
    )
    recurring_task = fields.Boolean(string="Recurrent")
    recurring_count = fields.Integer(
        string="Tasks in Recurrence",
        compute="_compute_recurring_count",
    )
    recurrence_id = fields.Many2one(
        comodel_name="project.task.recurrence",
        index="btree_not_null",
        copy=False,
    )
    repeat_interval = fields.Integer(
        string="Repeat Every",
        compute="_compute_repeat",
        compute_sudo=True,
        default=1,
        readonly=False,
    )
    repeat_unit = fields.Selection(
        selection=REPEAT_UNIT_SELECTION,
        compute="_compute_repeat",
        compute_sudo=True,
        default="week",
        readonly=False,
    )
    repeat_type = fields.Selection(
        selection=REPEAT_TYPE_SELECTION,
        string="Until",
        compute="_compute_repeat",
        compute_sudo=True,
        default="forever",
        readonly=False,
    )
    repeat_until = fields.Date(
        string="End Date",
        compute="_compute_repeat",
        compute_sudo=True,
        readonly=False,
    )
    recurrence_update = fields.Selection(
        selection=[
            ("this", "This task"),
            ("subsequent", "This and following tasks"),
            ("all", "All tasks"),
        ],
        help="Which tasks of the recurrence this change applies to.",
    )

    allow_milestones = fields.Boolean(
        related="project_id.allow_milestones",
        export_string_translation=False,
    )
    milestone_id = fields.Many2one(
        comodel_name="project.milestone",
        compute="_compute_milestone_id",
        store=True,
        index="btree_not_null",
        readonly=False,
        domain="[('project_id', '=', project_id)]",
        tracking=True,
        help="Deliver your services automatically when a milestone is reached by linking it to a sales order item.",
    )
    has_late_and_unreached_milestone = fields.Boolean(
        export_string_translation=False,
        compute="_compute_has_late_and_unreached_milestone",
        search="_search_has_late_and_unreached_milestone",
    )

    website_message_ids = fields.One2many(
        export_string_translation=False,
        domain=lambda self: [
            ("model", "=", self._name),
            (
                "message_type",
                "in",
                ["email", "comment", "email_outgoing", "auto_comment"],
            ),
        ],
    )

    is_template = fields.Boolean(export_string_translation=False)
    has_project_template = fields.Boolean(
        related="project_id.is_template",
        string="Has Project Template",
        export_string_translation=False,
    )
    has_template_ancestor = fields.Boolean(
        export_string_translation=False,
        compute="_compute_has_template_ancestor",
        recursive=True,
        store=True,
    )

    display_parent_task_button = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_parent_task_button",
        compute_sudo=True,
    )
    current_user_same_company_partner = fields.Boolean(
        export_string_translation=False,
        compute="_compute_current_user_same_company_partner",
        compute_sudo=True,
    )
    display_follow_button = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_follow_button",
        compute_sudo=True,
    )

    display_name = fields.Char(
        inverse="_inverse_display_name",
        help="""Use these keywords in the title to set new tasks:\n
            #tags Set tags on the task
            @user Assign the task to a user
            ! Set the task a medium priority
            !! Set the task a high priority
            !!! Set the task a urgent priority\n
            Make sure to use the right format and order e.g. Improve the configuration screen #feature #v16 @Mitchell !""",
    )
    link_preview_name = fields.Char(
        export_string_translation=False,
        compute="_compute_link_preview_name",
    )

    _recurring_task_has_no_parent = models.Constraint(
        "CHECK (NOT (recurring_task IS TRUE AND parent_id IS NOT NULL))",
        "You cannot convert this task into a sub-task because it is recurrent.",
    )
    _private_task_has_no_parent = models.Constraint(
        "CHECK (NOT (project_id IS NULL AND parent_id IS NOT NULL))",
        "A private task cannot have a parent.",
    )

    _is_template_idx = models.Index("(is_template) WHERE is_template IS TRUE")

    @api.constrains("company_id", "partner_id")
    def _check_company_consistency_with_partner(self) -> None:
        for task in self:
            if (
                task.partner_id
                and task.partner_id.company_id
                and task.company_id
                and task.company_id != task.partner_id.company_id
            ):
                raise ValidationError(
                    self.env._(
                        "The task and the associated partner must be linked to the same company."
                    )
                )

    @api.constrains("company_id", "recurrence_id")
    def _check_recurrence_one_company(self) -> None:
        for recurrence in self.recurrence_id:
            if len(recurrence.task_ids.company_id.root_id) > 1:
                raise ValidationError(
                    self.env._(
                        "The tasks of a recurrence belong to one company and its "
                        "branches."
                    )
                )

    @api.constrains("child_ids", "project_id")
    def _check_super_task_is_not_private(self) -> None:
        for task in self:
            if not task.project_id and task.subtask_count:
                raise ValidationError(
                    self.env._("This task has sub-tasks, so it can't be private.")
                )

    @property
    def TASK_PORTAL_READABLE_FIELDS(self) -> set[str]:
        return PROJECT_TASK_READABLE_FIELDS

    @property
    def TASK_PORTAL_WRITABLE_FIELDS(self) -> set[str]:
        return PROJECT_TASK_WRITABLE_FIELDS

    @api.depends("parent_id.project_id")
    def _compute_project_id(self) -> None:
        self.env.remove_to_compute(self._fields["display_in_project"], self)
        for task in self:
            if (
                task.parent_id
                and (not task.project_id or not task.display_in_project)
                and task.parent_id.project_id != task.project_id
            ):
                task.project_id = task.parent_id.project_id

    @api.depends("project_id", "parent_id")
    def _compute_display_in_project(self) -> None:
        for record in self:
            record.display_in_project = not record.project_id or (
                not record.parent_id or record.project_id != record.parent_id.project_id
            )

    def _inverse_parent_id(self) -> None:
        for task in self.sudo():
            if not task.parent_id:
                task.display_in_project = True
            elif (
                task.display_in_project
                and task.project_id == task.parent_id.sudo().project_id
            ):
                task.display_in_project = False

    @api.depends("predecessor_ids.state", "dependency_ids.dependency_type", "step_id")
    def _compute_state(self) -> None:
        for task in self:
            previous = state = task.state
            blocked = None
            if state not in CLOSED_STATES:
                blocked = task._is_waiting_on_predecessors()
                if blocked:
                    state = "blocked"
                elif state == "blocked":
                    state = "in_progress"
            # a stored task entering a step gets its state from write(), which
            # also runs the closing side effects; new and onchange records get
            # here the same answer write() will give
            entered_step = task.step_id != task._origin.step_id
            if entered_step:
                state = task._resolve_entered_step_state(state) or state
                if state not in CLOSED_STATES:
                    if blocked is None:
                        blocked = task._is_waiting_on_predecessors()
                    if blocked:
                        state = "blocked"
            task.state = state or "todo"
            if task.state != previous:
                _debug.logic(
                    "task_state_computed",
                    task=task,
                    previous=previous,
                    state=task.state,
                    step_state=task.step_id.task_state,
                    entered_step=entered_step,
                    waiting=bool(blocked),
                )

    def _is_waiting_on_predecessors(self) -> bool:
        self.check_singleton()
        return bool(self.allow_dependencies and self.is_blocked_by_predecessors())

    def _resolve_entered_step_state(self, state: str | None) -> str | None:
        # a step mapped to a closed state closes even a waiting task, as the
        # state widget offers it; an open predecessor finishing first is
        # checked on the move into done, not here
        self.check_singleton()
        step_state = self.step_id.task_state
        if step_state in CLOSED_STATES:
            return step_state
        if state == "blocked":
            return None
        if step_state:
            return step_state
        if state in STATES_RESET_ON_STEP_CHANGE:
            return "in_progress"
        return None

    @api.depends("state")
    def _compute_is_closed(self) -> None:
        for task in self:
            task.is_closed = task.state in CLOSED_STATES

    @api.depends("user_ids", "date_assign")
    def _compute_date_first_assign(self) -> None:
        for task in self:
            if task.user_ids and not task.date_first_assign:
                # date_assign can land after this runs (none for a default
                # assignee at create, a later write under project_hr): the
                # assignment is this transaction's, which create_date would date
                # back and which at create is create_date itself
                task.date_first_assign = task.date_assign or self.env.cr.now()
                _debug.logic(
                    "first_assign_stamped",
                    task=task,
                    from_date_assign=bool(task.date_assign),
                )
            else:
                task.date_first_assign = task.date_first_assign

    @api.depends("state")
    def _compute_date_closed(self) -> None:
        now = fields.Datetime.now()
        for task in self:
            if task.state in CLOSED_STATES:
                task.date_closed = task.date_closed or now
            else:
                task.date_closed = False

    def _search_is_closed(self, operator: str, value: Any) -> list:
        if operator == "in":
            searched_states = list(CLOSED_STATES.keys())
        elif operator == "not in":
            searched_states = self.OPEN_STATES
        else:
            return NotImplemented
        return [("state", "in", searched_states)]

    def _get_rotting_depends_fields(self) -> list[str]:
        return super()._get_rotting_depends_fields() + ["is_closed"]

    def _get_domain_rotting_records(self) -> list:
        return super()._get_domain_rotting_records() & Domain("is_closed", "=", False)

    @property
    def OPEN_STATES(self) -> list[str]:
        return list(
            set(self._fields["state"].get_values(self.env)) - set(CLOSED_STATES)
        )

    @api.onchange("project_id")
    def _onchange_project_id(self) -> None:
        if self.state in STATES_RESET_ON_STEP_CHANGE:
            self.state = "in_progress"
        if not self.project_id and not self.user_ids:
            self.user_ids = self.env.user

        if not self.project_id and self.parent_id and self.parent_id.project_id:
            self.project_id = self.parent_id.project_id.id
            self.display_in_project = False

    def is_blocked_by_predecessors(self) -> bool:
        return any(
            dependency._is_start_blocking()
            for dependency in self._get_predecessor_dependencies()
        )

    def _get_predecessor_dependencies(self):
        # one row per linked predecessor; a link made in a form and not saved
        # yet has no row, and reads as the finish-to-start default
        self.check_singleton()
        Dependency = self.env["project.task.dependency"]
        rows = {dep.depends_on_id._origin: dep for dep in self.dependency_ids}
        return Dependency.union(
            *(
                rows.get(predecessor._origin)
                or Dependency.new({"depends_on_id": predecessor._origin.id})
                for predecessor in self.predecessor_ids
            )
        )

    def _check_finish_dependencies(self) -> None:
        # called on a privileged recordset entering a delivered state, never on a
        # recompute: a predecessor reopened after its successor was done leaves
        # the successor done. Every predecessor binds; only those the acting user
        # may read are named
        for task in self:
            if task.state not in DELIVERED_STATES or not task.allow_dependencies:
                continue
            blocking = task._get_predecessor_dependencies().filtered(
                lambda dep: dep._is_finish_blocking()
            )
            if not blocking:
                continue
            predecessors = blocking.depends_on_id
            readable = predecessors.sudo(False)._filtered_access("read")
            hidden = len(predecessors - readable)
            _debug.logic(
                "finish_refused",
                task=task,
                predecessors=predecessors,
                readable=readable,
                hidden=hidden,
            )
            names = readable.mapped("display_name")
            if hidden == 1:
                names.append(self.env._("1 other task"))
            elif hidden:
                names.append(self.env._("%(count)s other tasks", count=hidden))
            raise ValidationError(
                self.env._(
                    "%(task)s cannot be done before these tasks finish (or "
                    "start, for start-to-finish): %(tasks)s",
                    task=task.display_name,
                    tasks=format_list(self.env, names),
                )
            )

    def _update_state_from_predecessors(self) -> None:
        blocked = self.sudo().filtered(
            lambda task: (
                task.allow_dependencies
                and task.state not in CLOSED_STATES
                and task.state != "blocked"
                and task.is_blocked_by_predecessors()
            )
        )
        if blocked:
            _debug.logic("predecessors_blocked", blocked=blocked, tasks=self)
            blocked.state = "blocked"

    @_debug.perf.timed
    def _inverse_state(self) -> None:
        last_task_id_per_recurrence_id = (
            self.recurrence_id._get_last_task_id_per_recurrence_id()
        )
        tasks = self.filtered(
            lambda task: (
                task.state in CLOSED_STATES
                and task.id == last_task_id_per_recurrence_id.get(task.recurrence_id.id)
            )
        )
        _debug.pipeline(
            "next_occurrences_requested", tasks=self, closed_last_occurrences=tasks
        )
        self.env["project.task.recurrence"]._create_next_occurrences(tasks)
        self.filtered(
            lambda task: (
                task.state == "canceled"
                and task.date_start
                and task.date_start > fields.Datetime.now()
            )
        ).write(
            {
                "date_start": False,
                "date_end": False,
            }
        )

    @_debug.perf.timed
    @api.depends_context("uid")
    @api.depends("user_ids")
    def _compute_personal_triage_id(self) -> None:
        personal_triages = self.env["project.task.triage"].search(
            [("user_id", "=", self.env.uid), ("task_id", "in", self.ids)]
        )
        self.personal_triage_id = False
        for personal_triage in personal_triages:
            personal_triage.task_id.personal_triage_id = personal_triage

    @api.model
    def _search_personal_triage_id(self, operator: str, value: Any) -> list:
        if operator in Domain.NEGATIVE_OPERATORS:
            return NotImplemented
        values = value if isinstance(value, (list, tuple)) else [value]
        field_name = "display_name" if any(isinstance(v, str) for v in values) else "id"
        domain = Domain(field_name, operator, value) & Domain(
            "user_id", "=", self.env.uid
        )
        personal_triages = self.env["project.task.triage"]._search(domain)
        return Domain("id", "in", personal_triages.subselect("task_id"))

    @api.model
    def _prepare_default_triage_vals(self, user_id: int) -> list[dict]:
        return [
            {
                "sequence": 1,
                "name": self.env._("Inbox"),
                "user_id": user_id,
                "fold": False,
            },
            {
                "sequence": 2,
                "name": self.env._("Today"),
                "user_id": user_id,
                "fold": False,
            },
            {
                "sequence": 3,
                "name": self.env._("This Week"),
                "user_id": user_id,
                "fold": False,
            },
            {
                "sequence": 4,
                "name": self.env._("This Month"),
                "user_id": user_id,
                "fold": False,
            },
            {
                "sequence": 5,
                "name": self.env._("Later"),
                "user_id": user_id,
                "fold": False,
            },
            {
                "sequence": 6,
                "name": self.env._("Done"),
                "user_id": user_id,
                "fold": True,
            },
            {
                "sequence": 7,
                "name": self.env._("Cancelled"),
                "user_id": user_id,
                "fold": True,
            },
        ]

    @_debug.perf.timed
    def _create_missing_triages(self) -> None:
        if not self:
            return

        TaskTriage = self.env["project.task.triage"].sudo()

        existing = TaskTriage.search([("task_id", "in", self.ids)])
        existing_pairs = {(r.task_id.id, r.user_id.id) for r in existing}
        to_create = [
            {"task_id": task.id, "user_id": user.id}
            for task in self.sudo()
            for user in task.user_ids
            if (task.id, user.id) not in existing_pairs
        ]
        _debug.pipeline(
            "triages_created",
            tasks=self,
            existing=len(existing),
            to_create=len(to_create),
        )
        if to_create:
            TaskTriage.create(to_create)

        triages_without_bucket = TaskTriage.search(
            [("task_id", "in", self.ids), ("triage_id", "=", False)]
        )
        if not triages_without_bucket:
            return
        _debug.logic("triages_without_bucket", count=len(triages_without_bucket))

        triage_by_user = defaultdict(lambda: self.env["project.task.triage"])
        for task_triage in triages_without_bucket:
            triage_by_user[task_triage.user_id] |= task_triage

        Triage = self.env["project.triage"].sudo()
        bucket_by_user = {}
        for bucket in Triage.search(
            [("user_id", "in", [u.id for u in triage_by_user])]
        ):
            bucket_by_user.setdefault(bucket.user_id.id, bucket)

        triages_by_bucket = defaultdict(self.env["project.task.triage"].sudo)
        for user_id, user_triages in triage_by_user.items():
            bucket = bucket_by_user.get(user_id.id)
            if not bucket:
                _debug.lifecycle("default_triage_buckets_created", user=user_id.id)
                bucket = Triage.with_context(lang=user_id.partner_id.lang).create(
                    self.with_context(
                        lang=user_id.partner_id.lang
                    )._prepare_default_triage_vals(user_id.id)
                )[0]
                bucket_by_user[user_id.id] = bucket
            triages_by_bucket[bucket] |= user_triages

        for bucket, user_triages in triages_by_bucket.items():
            user_triages.write({"triage_id": bucket.id})

    def _remove_orphan_triages(self) -> None:
        if not self:
            return
        rows = (
            self.env["project.task.triage"].sudo().search([("task_id", "in", self.ids)])
        )
        if not rows:
            return
        assignees_per_task = {task.id: set(task.user_ids.ids) for task in self.sudo()}
        stale = rows.filtered(
            lambda row: row.user_id.id not in assignees_per_task.get(row.task_id.id, ())
        )
        _debug.pipeline(
            "orphan_triages_removed", tasks=self, rows=len(rows), stale=len(stale)
        )
        if stale:
            stale.unlink()

    def message_subscribe(self, partner_ids=None, subtype_ids=None) -> bool:
        partner_ids = list(partner_ids or [])
        if subtype_ids or not partner_ids:
            return super().message_subscribe(partner_ids, subtype_ids)
        subscribed = True
        for project, tasks in self.grouped("project_id").items():
            project_followers = project.sudo().message_follower_ids.filtered(
                lambda f: f.partner_id.id in partner_ids
            )
            for project_follower in project_followers:
                project_subtypes = project_follower.subtype_ids
                task_subtypes = (
                    (
                        project_subtypes.parent_id
                        | project_subtypes.filtered(
                            lambda sub: sub.internal or sub.default
                        )
                    ).ids
                    if project_subtypes
                    else None
                )
                _debug.logic(
                    "project_subtypes_inherited",
                    tasks=tasks,
                    partner=project_follower.partner_id.id,
                    subtypes=task_subtypes,
                )
                super(ProjectTask, tasks).message_subscribe(
                    project_follower.partner_id.ids, task_subtypes
                )
            inherited = set(project_followers.partner_id.ids)
            subscribed &= super(ProjectTask, tasks).message_subscribe(
                [pid for pid in partner_ids if pid not in inherited]
            )
        return subscribed

    @api.constrains("predecessor_ids")
    def _check_no_cyclic_dependencies(self) -> None:
        if self._has_cycle("predecessor_ids"):
            raise ValidationError(self.env._("Two tasks cannot depend on each other."))

    def _check_no_self_dependency(self, vals: dict[str, Any]) -> None:
        # the many2many writes the dependency table directly, whose CHECK would
        # surface as a database error before any constraint runs
        linked_ids = set()
        for fname in ("predecessor_ids", "successor_ids"):
            for command in vals.get(fname) or ():
                if isinstance(command, int):
                    linked_ids.add(command)
                elif command[0] == Command.LINK:
                    linked_ids.add(command[1])
                elif command[0] == Command.SET:
                    linked_ids.update(command[2])
        if linked_ids.intersection(self.ids):
            _debug.logic("self_dependency_refused", tasks=self)
            raise ValidationError(self.env._("A task cannot depend on itself."))

    def _invalidate_dependency_links(self, predecessors: Self) -> None:
        # project.task.dependency is the table both many2many read: a row
        # written through the model leaves their cache behind
        self.invalidate_recordset(["predecessor_ids"])
        predecessors.invalidate_recordset(["successor_ids"])
        self.modified(["predecessor_ids"])
        predecessors.modified(["successor_ids"])

    def _invalidate_dependency_rows(self) -> None:
        # and a link written through either many2many leaves the rows' cache
        self.env["project.task.dependency"].invalidate_model()
        self.invalidate_model(["dependency_ids", "dependent_on_me_ids"])

    @api.model
    def _get_fields_recurrence(self) -> list[str]:
        return [
            "repeat_interval",
            "repeat_unit",
            "repeat_type",
            "repeat_until",
        ]

    @api.depends("recurring_task")
    def _compute_repeat(self) -> None:
        rec_fields = self._get_fields_recurrence()
        defaults = self.default_get(rec_fields)
        for task in self:
            for f in rec_fields:
                if task.recurrence_id:
                    task[f] = task.recurrence_id.sudo()[f]
                elif task.recurring_task:
                    task[f] = defaults.get(f)
                else:
                    task[f] = False

    def _is_recurrence_valid(self) -> bool:
        self.check_singleton()
        return self.repeat_interval > 0 and (
            self.repeat_type != "until"
            or (self.repeat_until and self.repeat_until > fields.Date.today())
        )

    @api.depends("recurrence_id")
    def _compute_recurring_count(self) -> None:
        self.recurring_count = 0
        recurring_tasks = self.filtered(lambda l: l.recurrence_id)
        count = self.env["project.task"]._read_group(
            [("recurrence_id", "in", recurring_tasks.recurrence_id.ids)],
            ["recurrence_id"],
            ["__count"],
        )
        tasks_count = {recurrence.id: count for recurrence, count in count}
        for task in recurring_tasks:
            task.recurring_count = tasks_count.get(task.recurrence_id.id, 0)

    @api.depends("allow_dependencies", "predecessor_ids.state")
    def _compute_predecessor_counts(self) -> None:
        for task in self:
            predecessors = (
                task.predecessor_ids
                if task.allow_dependencies
                else task.predecessor_ids.browse()
            )
            task.predecessor_count = len(predecessors)
            task.closed_predecessor_count = len(
                predecessors.filtered(lambda t: t.state in CLOSED_STATES)
            )

    @api.depends("allow_dependencies", "successor_ids.is_closed")
    def _compute_successor_count(self) -> None:
        for task in self:
            task.successor_count = (
                len(task.successor_ids.filtered(lambda t: not t.is_closed))
                if task.allow_dependencies
                else 0
            )

    @api.constrains("project_id")
    def _check_risks_follow_project(self) -> None:
        self.env["project.risk"].search(
            [("task_id", "in", self.ids)]
        )._check_task_project()

    @api.constrains("parent_id")
    def _check_parent_id(self) -> None:
        if self._has_cycle():
            raise ValidationError(
                self.env._("Error! You cannot create a recursive hierarchy of tasks.")
            )

    @_debug.perf.timed
    def _compute_attachment_ids(self) -> None:
        attachments_by_task: dict[int, list[int]] = {}
        message_attachment_ids: set[int] = set()
        if task_ids := self._origin.ids:
            attachments_by_task = dict(
                self.env["ir.attachment"]._read_group(
                    [("res_model", "=", "project.task"), ("res_id", "in", task_ids)],
                    ["res_id"],
                    ["id:array_agg"],
                )
            )
            message_attachment_ids = set(
                self.env["mail.message"]
                .search([("model", "=", "project.task"), ("res_id", "in", task_ids)])
                .attachment_ids.ids
            )
        for task in self:
            task.attachment_ids = [
                Command.set(
                    [
                        attachment_id
                        for attachment_id in attachments_by_task.get(
                            task._origin.id, []
                        )
                        if attachment_id not in message_attachment_ids
                    ]
                )
            ]

    @_debug.perf.timed
    @api.depends(
        "create_date",
        "date_closed",
        "date_first_assign",
        "project_id.resource_calendar_id",
    )
    def _compute_elapsed(self) -> None:
        by_calendar = defaultdict(lambda: self.env["project.task"])
        for task in self:
            if not task.create_date:
                task._update_elapsed_times()
                continue
            key = (
                task.project_id.resource_calendar_id.id,
                tuple(task.project_id.company_id.ids),
            )
            by_calendar[key] |= task

        for (calendar_id, company_ids), tasks in by_calendar.items():
            calendar = self.env["resource.calendar"].browse(calendar_id)
            _debug.logic(
                "elapsed_computed",
                tasks=len(tasks),
                calendar=calendar_id,
                companies=company_ids,
                mode="work_intervals" if calendar else "wall_clock",
            )
            if not calendar:
                for task in tasks:
                    task._update_elapsed_times(**task._get_elapsed_spans_wall_clock())
                continue
            leave_domain = [
                ("company_id", "in", list(company_ids)),
                ("time_type_id.is_work", "=", False),
            ]
            bounds = [
                value
                for task in tasks
                for value in (
                    task.create_date,
                    task.date_first_assign,
                    task.date_closed,
                )
                if value
            ]
            with _debug.perf(
                "elapsed_work_intervals",
                cr=self.env.cr,
                start=min(bounds),
                stop=max(bounds),
            ):
                intervals = calendar._work_intervals_batch(
                    localized(min(bounds)),
                    localized(max(bounds)),
                    domain=leave_domain,
                )[False]
            items = list(intervals)
            index = (items, [item[0] for item in items], [item[1] for item in items])
            for task in tasks:
                task._update_elapsed_times(
                    **task._get_elapsed_spans_calendar(calendar, index)
                )

    def _get_elapsed_spans_wall_clock(self) -> dict[str, tuple[float, float]]:
        self.check_singleton()

        def get_span_hours_and_days(start, stop):
            if not (start and stop):
                return 0.0, 0.0
            elapsed = stop - start
            return elapsed.total_seconds() / 3600, elapsed.days

        return {
            "queue": get_span_hours_and_days(self.create_date, self.date_first_assign),
            "lead": get_span_hours_and_days(self.create_date, self.date_closed),
            "cycle": get_span_hours_and_days(self.date_first_assign, self.date_closed),
        }

    def _get_elapsed_spans_calendar(
        self, calendar: Any, index: tuple[list, list, list]
    ) -> dict[str, tuple[float, float]]:
        self.check_singleton()
        items, item_starts, item_stops = index

        def get_span_hours_and_days(start, stop):
            if not (start and stop) or start >= stop:
                return 0.0, 0.0
            low, high = localized(start), localized(stop)
            clipped = [
                (max(item_start, low), min(item_stop, high), recs)
                for item_start, item_stop, recs in items[
                    bisect_right(item_stops, low) : bisect_left(item_starts, high)
                ]
                if max(item_start, low) < min(item_stop, high)
            ]
            data = calendar._get_duration_data(Intervals(clipped))
            return data["hours"], data["days"]

        return {
            "queue": get_span_hours_and_days(self.create_date, self.date_first_assign),
            "lead": get_span_hours_and_days(self.create_date, self.date_closed),
            "cycle": get_span_hours_and_days(self.date_first_assign, self.date_closed),
        }

    def _update_elapsed_times(
        self, queue=(0.0, 0.0), lead=(0.0, 0.0), cycle=(0.0, 0.0)
    ) -> None:
        self.queue_time_hours, self.queue_time_days = queue
        self.lead_time_hours, self.lead_time_days = lead
        self.cycle_time_hours, self.cycle_time_days = cycle

    @api.depends("date_closed", "date_end", "state")
    def _compute_deadline_met(self) -> None:
        for task in self:
            if not task.date_end or task.state not in DELIVERED_STATES:
                task.deadline_met = False
            elif task.date_closed and task.date_closed <= task.date_end:
                task.deadline_met = "met"
            else:
                task.deadline_met = "missed"

    @api.depends("cost_of_delay", "planned_hours")
    def _compute_cd3_score(self) -> None:
        for task in self:
            if task.cost_of_delay and task.planned_hours:
                task.cd3_score = task.cost_of_delay / task.planned_hours
            else:
                task.cd3_score = 0.0

    @api.depends("reservation_ids.schedule_overlap_count")
    def _compute_is_overallocated(self) -> None:
        for task in self:
            task.is_overallocated = any(
                r.schedule_overlap_count for r in task.reservation_ids
            )

    def _compute_access_url(self) -> None:
        super()._compute_access_url()
        for task in self:
            task.access_url = f"/my/tasks/{task.id}"

    @api.depends("child_ids.planned_hours")
    def _compute_subtask_planned_hours(self) -> None:
        for task in self:
            task.subtask_planned_hours = sum(task.child_ids.mapped("planned_hours"))

    @api.depends(
        "date_start",
        "date_end",
        "company_id.resource_calendar_id",
        "project_id.company_id.resource_calendar_id",
        "user_ids.company_id.resource_calendar_id",
        "create_uid.company_id.resource_calendar_id",
    )
    def _compute_scheduled_hours(self) -> None:
        fixed_per_calendar = defaultdict(self.browse)
        for task in self:
            calendar = (
                task._scheduling_resolve_calendar()
                if task.date_start and task.date_end and task.date_end > task.date_start
                else None
            )
            if calendar and calendar.schedule_type == "fully_fixed":
                fixed_per_calendar[calendar] |= task
            else:
                task.scheduled_hours = round(
                    task._scheduling_get_work_hours(
                        task.date_start, task.date_end, compute_leaves=True
                    ),
                    2,
                )
        Attendance = self.env["resource.calendar.attendance"]
        for calendar, tasks in fixed_per_calendar.items():
            for window in tasks._split_scheduling_windows():
                work_intervals = calendar._work_intervals_batch(
                    localized(min(window.mapped("date_start"))),
                    localized(max(window.mapped("date_end"))),
                )[False]
                _debug.logic(
                    "scheduled_hours_batched", calendar=calendar.id, tasks=window
                )
                for task in window:
                    task_interval = Intervals(
                        [
                            (
                                localized(task.date_start),
                                localized(task.date_end),
                                Attendance,
                            )
                        ]
                    )
                    task.scheduled_hours = round(
                        get_intervals_hours(work_intervals & task_interval), 2
                    )

    def _scheduling_resolve_calendar(self):
        # never the company of whoever triggers the recompute: a task with no
        # company of its own reads its assignees' one company, else its
        # creator's; a company without a calendar counts elapsed hours
        self.check_singleton()
        company = self.company_id or self.project_id.company_id
        if not company:
            companies = self.user_ids.company_id
            if len(companies) == 1:
                company = companies
            else:
                company = (self.create_uid or self.env.user).company_id
        _debug.logic(
            "scheduling_calendar_resolved",
            task=self,
            company=company.id,
            calendar=company.resource_calendar_id.id,
        )
        return company.resource_calendar_id

    def _split_scheduling_windows(
        self, max_gap=timedelta(days=7), max_span=timedelta(days=366)
    ) -> list[Self]:
        # one interval fetch per cluster of nearby tasks: a fetch costs what its
        # span costs, so one stray date years away would make a single fetch
        # over the whole batch slower than a fetch per task
        windows = []
        window = self.browse()
        start = end = None
        for task in self.sorted("date_start"):
            if window and (
                task.date_start > end + max_gap or task.date_end - start > max_span
            ):
                windows.append(window)
                window = self.browse()
            if not window:
                start, end = task.date_start, task.date_end
            window |= task
            end = max(end, task.date_end)
        if window:
            windows.append(window)
        return windows

    def _get_planned_hours(self) -> float:
        self.check_singleton()
        return round(
            self.scheduled_hours
            * self.planned_resources
            * (self.allocated_percentage / 100.0),
            2,
        )

    @api.depends("scheduled_hours", "planned_resources", "allocated_percentage")
    def _compute_planned_hours(self) -> None:
        for task in self:
            if task.planned_hours_manual or not task.scheduled_hours:
                task.planned_hours = task.planned_hours or 0.0
                continue
            task.planned_hours = task._get_planned_hours()

    def _inverse_planned_hours(self) -> None:
        diverging = self.filtered(
            lambda task: float_compare(
                task.planned_hours,
                task._get_planned_hours(),
                precision_digits=2,
            )
        )
        diverging.planned_hours_manual = True
        (self - diverging).planned_hours_manual = False

        overridden = diverging.filtered("scheduled_hours")
        _debug.logic(
            "planned_hours_inverted",
            tasks=self,
            diverging=diverging,
            overridden=overridden,
        )
        if not overridden:
            return
        overridden._message_log_batch(
            bodies={
                task.id: self.env._(
                    "Planned Hours manually overridden to %(value).2f h "
                    "(formula override).",
                    value=task.planned_hours,
                )
                for task in overridden
            }
        )

    def _get_cpm_duration_hours(self) -> float:
        self.check_singleton()
        if self.scheduled_hours:
            return self.scheduled_hours
        units = (self.allocated_percentage or 100.0) / 100.0
        if self.planned_hours and self.planned_resources:
            return self.planned_hours / (self.planned_resources * units)
        if self.allocated_hours:
            return self.allocated_hours / (max(len(self.user_ids), 1) * units)
        return 0.0

    @api.depends("planned_hours", "allocated_hours")
    def _compute_allocation_state(self) -> None:
        for task in self:
            if float_is_zero(task.planned_hours, precision_digits=2):
                task.allocation_state = "unestimated"
                continue
            if float_is_zero(task.allocated_hours, precision_digits=2):
                task.allocation_state = "unallocated"
                continue
            delta = float_compare(
                task.allocated_hours, task.planned_hours, precision_digits=2
            )
            if delta == 0:
                task.allocation_state = "allocated"
            elif delta > 0:
                task.allocation_state = "over_allocated"
            else:
                task.allocation_state = "under_allocated"

    @_debug.perf.timed
    @api.depends("child_ids", "child_ids.state")
    def _compute_subtask_counts(self) -> None:
        if not any(self._ids):
            for task in self:
                task.subtask_count, task.closed_subtask_count = (
                    len(task.child_ids),
                    len(task.child_ids.filtered(lambda r: r.state in CLOSED_STATES)),
                )
            return
        total_and_closed_subtask_count_per_parent_id = {
            parent.id: (count, sum(s in CLOSED_STATES for s in states))
            for parent, states, count in self.env["project.task"]._read_group(
                [("parent_id", "in", self.ids)],
                ["parent_id"],
                ["state:array_agg", "__count"],
            )
        }
        for task in self:
            task.subtask_count, task.closed_subtask_count = (
                total_and_closed_subtask_count_per_parent_id.get(task.id, (0, 0))
            )

    @api.depends("partner_id.phone_ids")
    def _compute_phone_ids(self) -> None:
        for task in self:
            task.phone_ids = task.partner_id.phone_ids

    @api.depends_context("uid")
    @api.depends("partner_id")
    def _compute_partner_phones_editable(self) -> None:
        writable = self.partner_id._filtered_access("write")
        for task in self:
            task.partner_phones_editable = (
                not task.partner_id or task.partner_id in writable
            )

    def _inverse_phone_ids(self) -> None:
        for task in self.filtered("partner_id"):
            if task.phone_ids != task.partner_id.phone_ids:
                task.partner_id.phone_ids = task.phone_ids

    @api.onchange("company_id")
    def _onchange_task_company(self) -> None:
        if self.project_id.company_id and self.project_id.company_id != self.company_id:
            self.project_id = False

    @api.depends("project_id.company_id", "parent_id.company_id")
    def _compute_company_id(self) -> None:
        for task in self:
            if not task.parent_id and not task.project_id:
                continue
            task.company_id = task.project_id.company_id or task.parent_id.company_id

    @api.depends("project_id")
    def _compute_step_id(self) -> None:
        default_step_by_project: dict[int, int | bool] = {}
        for task in self:
            project = task.project_id or task.parent_id.project_id
            if not project:
                task.step_id = False
                continue
            if project not in task.step_id.project_ids:
                if project.id not in default_step_by_project:
                    default_step_by_project[project.id] = self._get_default_step_id(
                        project.id
                    )
                _debug.logic(
                    "step_defaulted",
                    task=task,
                    step=task.step_id.id,
                    project=project.id,
                    default_step=default_step_by_project[project.id],
                )
                task.step_id = default_step_by_project[project.id]

    @api.depends("user_ids")
    @api.depends_context("lang")
    def _compute_portal_user_names(self) -> None:
        # the assignees' names, read whole even when the viewer cannot read
        # every assignee; a record being edited keeps its unsaved assignees
        if saved := self.filtered(lambda task: isinstance(task.id, int)):
            saved.invalidate_recordset(fnames=["user_ids"])
            saved.fetch(["user_ids"])
        for task in self.with_context(prefetch_fields=False):
            task.portal_user_names = format_list(self.env, task.user_ids.mapped("name"))

    def _search_portal_user_names(self, operator: str, value: Any) -> list:
        if operator != "ilike" or not isinstance(value, str):
            return NotImplemented

        sql = SQL(
            """(
            SELECT task_user.task_id
              FROM project_task_user_rel task_user
        INNER JOIN res_users users ON task_user.user_id = users.id
        INNER JOIN res_partner partners ON partners.id = users.partner_id
             WHERE partners.name ILIKE %s
        )""",
            f"%{value}%",
        )
        return [("id", "in", sql)]

    @api.depends_context("uid")
    def _compute_display_parent_task_button(self) -> None:
        accessible_parent_tasks = self.parent_id.with_user(
            self.env.user
        )._filtered_access("read")
        for task in self:
            task.display_parent_task_button = task.parent_id in accessible_parent_tasks

    @api.depends_context("uid")
    def _compute_current_user_same_company_partner(self) -> None:
        commercial_partner_id = self.env.user.partner_id.commercial_partner_id
        for task in self:
            task.current_user_same_company_partner = (
                task.partner_id
                and commercial_partner_id == task.partner_id.commercial_partner_id
            )

    @api.depends_context("uid")
    def _compute_display_follow_button(self) -> None:
        if not self.env.user.share:
            self.display_follow_button = False
            return
        collaborated_projects = (
            self.env["project.collaborator"]
            .sudo()
            .search(
                [
                    ("project_id", "in", self.project_id.ids),
                    ("is_current_user_collaboration", "=", True),
                ]
            )
            .project_id
        )
        for task in self:
            task.display_follow_button = task.project_id in collaborated_projects

    def _get_pattern_per_group(self) -> dict[str, str]:
        return {
            "tags_and_users": r"\s([#@]%s[^\s]+)",
            "priority": r"(?:^|\s)(!{1,3})(?=\s|$)",
        }

    def _get_patterns_in_group_order(self) -> list[str]:
        group = self._get_pattern_per_group()
        return [
            group["tags_and_users"] % "",
            group["priority"],
        ]

    def _get_pattern_alternation(self) -> list[str]:
        return [
            r"(?:%s)*" % ("|").join(self._get_patterns_in_group_order()),
        ]

    def _get_cannot_start_with_patterns(self) -> list[str]:
        return [r"(?![#!@\s])"]

    def _extract_tags_and_users(self, title: str) -> str:
        tags = []
        users = []
        tags_and_users_group = self._get_pattern_per_group()["tags_and_users"]
        for word in re.findall(tags_and_users_group % "", title):
            (tags if word.startswith("#") else users).append(word[1:])
        users_to_keep = []
        user_ids = []
        for user in users:
            matched_users = self.env["res.users"].name_search(  # noqa: E8507 - one lookup per @mention in the title
                user, domain=[("share", "=", False)]
            )
            if len(matched_users) == 1:
                user_ids.append(Command.link(matched_users[0][0]))
            else:
                users_to_keep.append(r"%s\b" % re.escape(user))
        _debug.logic(
            "tags_and_users_extracted",
            tasks=self,
            tags=tags,
            users=users,
            matched_users=len(user_ids),
            unmatched=len(users_to_keep),
        )
        self.user_ids = user_ids
        if tags:
            domain = Domain.OR(
                Domain("name", "=ilike", escape_psql(tag)) for tag in tags
            )
            existing_tags = self.env["project.tags"].search(domain)
            existing_tags_names = {tag.name.lower() for tag in existing_tags}
            new_tags_names = {
                tag for tag in tags if tag.lower() not in existing_tags_names
            }
            if _debug.logic.enabled:
                _debug.logic(
                    "tags_created",
                    existing=existing_tags,
                    creating=sorted(new_tags_names),
                )
            self.tag_ids = [Command.set(existing_tags.ids)] + [
                Command.create({"name": name}) for name in new_tags_names
            ]
        pattern = tags_and_users_group % (
            "(?!%s)" % ("|").join(users_to_keep) if users_to_keep else ""
        )
        return re.subn(pattern, "", title)[0]

    def _extract_priority(self, title: str) -> str:
        priority_group = self._get_pattern_per_group()["priority"]
        match = re.search(priority_group, title)
        if not match:
            return title
        self.priority = str(min(len(match.group(1)), 3))
        return re.subn(priority_group, "", title)[0]

    def _get_extractors_in_group_order(self) -> list:
        return [
            lambda task, title: task._extract_tags_and_users(title),
            lambda task, title: task._extract_priority(title),
        ]

    def _inverse_display_name(self) -> None:
        for task in self:
            if not task.display_name:
                continue
            pattern = re.compile(
                r"^%s.+?%s$"
                % (
                    ("").join(task._get_cannot_start_with_patterns()),
                    ("").join(task._get_pattern_alternation()),
                )
            )
            match = pattern.match(task.display_name)
            if not match:
                continue
            title = task.display_name
            for group, extract_data in enumerate(
                task._get_extractors_in_group_order(), start=1
            ):
                if match.group(group):
                    title = extract_data(task, title)
            _debug.logic(
                "display_name_inverted",
                task=task,
                previous=task.display_name,
                name=title.strip(),
            )
            task.name = title.strip()

    @api.depends("display_name", "project_id.name")
    def _compute_link_preview_name(self) -> None:
        for task in self:
            link_preview_name = task.display_name
            if task.project_id:
                link_preview_name += f" | {task.project_id.sudo().name}"
            task.link_preview_name = link_preview_name

    @api.depends("is_template", "parent_id.has_template_ancestor")
    def _compute_has_template_ancestor(self) -> None:
        for task in self:
            task.has_template_ancestor = task.is_template or (
                task.parent_id and task.parent_id.sudo().has_template_ancestor
            )

    @_debug.perf.timed
    def copy_data(self, default=None) -> list[ValuesType]:
        default = dict(default or {})
        default.update(
            {
                "predecessor_ids": False,
                "successor_ids": False,
            }
        )
        _debug.lifecycle(
            "copy_data",
            tasks=self,
            default=sorted(default),
            copy_project=self.env.context.get("copy_project"),
            copy_from_template=self.env.context.get("copy_from_template"),
        )
        vals_list = super().copy_data(default=default)
        vals_list = [
            {
                k: v
                for k, v in vals.items()
                if self._has_field_access(self._fields[k], "read")
            }
            for vals in vals_list
        ]

        has_default_users = "user_ids" in default
        milestone_mapping = self.env.context.get("milestone_mapping", {})
        for task, vals in zip(self, vals_list, strict=True):
            if not default.get("step_id"):
                vals["step_id"] = task.step_id.id
            if (
                "active" not in default
                and not task["active"]
                and not self.env.context.get("copy_project")
            ):
                vals["active"] = True
            if not default.get("name"):
                vals["name"] = (
                    task.name
                    if self.env.context.get("copy_project")
                    or self.env.context.get("copy_from_template")
                    else self.env._("%s (copy)", task.name)
                )
            if task.recurrence_id and "recurrence_id" not in default:
                vals["recurrence_id"] = task.recurrence_id.copy().id
                _debug.logic(
                    "recurrence_copied",
                    task=task,
                    recurrence=task.recurrence_id.id,
                    copy=vals["recurrence_id"],
                )
            if task.allow_milestones:
                vals["milestone_id"] = milestone_mapping.get(
                    vals["milestone_id"], vals["milestone_id"]
                )
            if not default.get("child_ids") and task.child_ids:
                whitelisted_fields = (
                    self._get_template_default_context_whitelist()
                    if self.env.context.get("copy_from_template")
                    else []
                )
                child_default = {
                    key: value
                    for key, value in default.items()
                    if key in whitelisted_fields
                }
                child_default["parent_id"] = False
                current_task = task
                if self.env.context.get("copy_from_template"):
                    current_task = current_task.with_context(active_test=True)
                child_ids = current_task.child_ids.sorted("id")
                _debug.pipeline("subtasks_copied", task=task, subtasks=len(child_ids))
                vals["child_ids"] = [
                    Command.create(child_id.copy_data(child_default)[0])
                    for child_id in child_ids.filtered(lambda c: c.active)
                ]
            task._copy_data_assignment(vals, default, has_default_users)
            if self.env.context.get("copy_from_template") and not self.env.context.get(
                "copy_from_project_template"
            ):
                vals["is_template"] = False
            if self.env.context.get("copy_from_template"):
                for field in set(self._get_template_field_blacklist()) & set(
                    vals.keys()
                ):
                    del vals[field]
        return vals_list

    def _get_task_mapping_and_dependencies(
        self, copied_tasks: Self
    ) -> tuple[dict, dict]:
        task_mapping, task_dependencies = {}, {}
        # copies are created in the copied recordset's order, so their ids
        # ascend along self; children were copied by id (copy_data)
        copied_tasks = copied_tasks.sorted("id")
        for original_task, copied_task in zip(self, copied_tasks, strict=True):
            task_mapping[original_task.id] = copied_task
            if original_task.allow_dependencies:
                # archived neighbours too: a link between two copied tasks is
                # copied whatever their active state; the many2many read still
                # leaves out the tasks the user may not read
                linked = original_task.with_context(active_test=False)
                if linked.predecessor_ids or linked.successor_ids:
                    task_dependencies[original_task.id] = [
                        linked.predecessor_ids.ids,
                        linked.successor_ids.ids,
                    ]
            active_children = original_task.child_ids.filtered("active").sorted("id")
            if active_children:
                children_mapping, children_dependencies = (
                    active_children._get_task_mapping_and_dependencies(
                        copied_task.child_ids
                    )
                )
                task_mapping.update(children_mapping)
                task_dependencies.update(children_dependencies)
        return task_mapping, task_dependencies

    def _portal_verify_parent_hash(
        self, signature: str, pid: int, token: str | None = None
    ) -> bool:
        # a project's link reaches the tasks its page lists, and only with the
        # hash signed over that very link: a bare hash would be judged against
        # whichever link the project's customer holds, at no role at all
        project = self.project_id
        if not (project and token and self.active) or self.has_template_ancestor:
            return False
        return project._portal_token_opens(
            token, role="comment", action=None
        ) and project._verify_sign_token(signature, pid, token=token)

    @_debug.perf.timed
    def _update_copied_dependencies(self, copied_tasks: Self) -> None:
        task_mapping, task_dependencies = self._get_task_mapping_and_dependencies(
            copied_tasks
        )
        _debug.pipeline(
            "copied_dependencies_updated",
            tasks=self,
            mapped=len(task_mapping),
            with_dependencies=len(task_dependencies),
        )
        if not task_dependencies:
            return
        pairs = set()
        for task_id, (predecessor_ids, successor_ids) in task_dependencies.items():
            pairs.update(
                (task_id, predecessor_id) for predecessor_id in predecessor_ids
            )
            pairs.update((successor_id, task_id) for successor_id in successor_ids)
        left_behind = self.browse(
            sorted({task_id for pair in pairs for task_id in pair})
        )
        left_behind = left_behind.filtered(lambda task: task.id not in task_mapping)
        archived_ids = set(left_behind.filtered(lambda task: not task.active).ids)
        pairs = {pair for pair in pairs if not archived_ids.intersection(pair)}
        if not pairs:
            return
        rows = self.env["project.task.dependency"].search(
            [
                ("task_id", "in", list({pair[0] for pair in pairs})),
                ("depends_on_id", "in", list({pair[1] for pair in pairs})),
            ]
        )
        row_per_pair = {(row.task_id.id, row.depends_on_id.id): row for row in rows}

        def get_copied_id(task_id):
            copied = task_mapping.get(task_id)
            return copied.id if copied else task_id

        vals_per_pair = {}
        for pair in sorted(pairs):
            copied_pair = tuple(get_copied_id(task_id) for task_id in pair)
            row = row_per_pair.get(pair)
            vals_per_pair.setdefault(
                copied_pair,
                {
                    "task_id": copied_pair[0],
                    "depends_on_id": copied_pair[1],
                    "dependency_type": row.dependency_type if row else "fs",
                    "lag_hours": row.lag_hours if row else 0.0,
                },
            )
        _debug.logic(
            "dependencies_copied",
            originals=len(pairs),
            copied=len(vals_per_pair),
            archived_left_behind=len(archived_ids),
        )
        self.env["project.task.dependency"].create(list(vals_per_pair.values()))

    @_debug.perf.timed
    def copy(self, default=None) -> Self:
        default = default or {}
        copied_tasks = super(
            ProjectTask,
            self.with_context(
                mail_auto_subscribe_no_notify=True,
                mail_create_nosubscribe=True,
                mail_create_nolog=bool(not self.env.context.get("copy_from_template")),
            ),
        ).copy(default=default)
        _debug.lifecycle("copy", tasks=self, copies=copied_tasks)

        self._update_copied_dependencies(copied_tasks)
        if not self.env.context.get("copy_from_template"):
            log_message = self.env._("Task Created")
            copied_tasks._message_log_batch(
                bodies={task.id: log_message for task in copied_tasks}
            )

        return copied_tasks

    @api.model
    def get_empty_list_help(self, help_message: str) -> str:
        tname = self.env._("task")
        project_id = self.env.context.get("default_project_id", False)
        if project_id:
            name = self.env["project.project"].browse(project_id).label_tasks
            if name:
                tname = name.lower()

        self = self.with_context(
            empty_list_help_id=self.env.context.get("default_project_id"),
            empty_list_help_model="project.project",
            empty_list_help_document_name=tname,
        )
        return super().get_empty_list_help(help_message)

    def get_step_id(
        self,
        section_id: int | bool,
        domain: list | None = None,
        order: str = "sequence, id",
    ) -> int | bool:
        domain = domain or []
        section_ids = []
        if section_id:
            section_ids.append(section_id)
        section_ids.extend(self.mapped("project_id").ids)
        search_domain = []
        if section_ids:
            search_domain = ["|"] * (len(section_ids) - 1)
            for sec_id in section_ids:
                search_domain.append(("project_ids", "=", sec_id))
        search_domain += list(domain)
        step_id = (
            self.env["project.workflow.step"]
            .search(search_domain, order=order, limit=1)
            .id
        )
        _debug.logic(
            "step_resolved",
            sections=section_ids,
            domain=domain,
            order=order,
            step=step_id,
        )
        return step_id

    @api.model
    def _get_view_cache_key(
        self,
        view_id: int | None = None,
        view_type: str = "form",
        **options: Any,
    ) -> tuple:
        key = super()._get_view_cache_key(view_id, view_type, **options)
        return key + (self.env.user._is_portal(),)

    @_debug.perf.timed
    @api.model
    def default_get(self, fields: list[str]) -> dict:
        vals = super().default_get(fields)

        if project_id := self.env.context.get("default_create_in_project_id"):
            _debug.logic(
                "default_project",
                project=project_id,
                source="default_create_in_project_id",
            )
            vals["project_id"] = project_id

        if "date_start_effective" in vals:
            date_start_effective = vals.pop("date_start_effective")
            if "date_start" in fields and not vals.get("date_start"):
                vals["date_start"] = date_start_effective

        if "state" in fields and vals.get("state") == "blocked":
            vals["state"] = "in_progress"

        if "repeat_until" in fields and not vals.get("repeat_until"):
            vals["repeat_until"] = Date.today() + timedelta(days=7)

        if "partner_id" in vals and not vals["partner_id"]:
            project_id = vals.get("project_id")
            parent_id = vals.get("parent_id", self.env.context.get("default_parent_id"))
            if project_id or parent_id:
                partner_id = self._get_default_partner_id(
                    project_id and self.env["project.project"].browse(project_id),
                    parent_id and self.env["project.task"].browse(parent_id),
                )
                if partner_id:
                    _debug.logic(
                        "default_partner",
                        partner=partner_id,
                        project=project_id,
                        parent=parent_id,
                    )
                    vals["partner_id"] = partner_id
        project_id = vals.get("project_id", self.env.context.get("default_project_id"))
        if project_id:
            project = self.env["project.project"].browse(project_id)
            if "company_id" in fields and "default_project_id" not in self.env.context:
                vals["company_id"] = project.sudo().company_id.id
        elif "default_user_ids" not in self.env.context and "user_ids" in fields:
            vals.update(self._prepare_assignment_vals(self.env.user))
            _debug.logic("default_private_user", user=self.env.user.id)

        composed_fields = (self._get_fields_assignment() - {"user_ids"}) & set(fields)
        if composed_fields and "default_user_ids" in self.env.context:
            users = self.env["res.users"].browse(
                self._fields["user_ids"].convert_to_cache(
                    self.env.context["default_user_ids"], self, validate=False
                )
            )
            _debug.logic(
                "default_users",
                users=users.ids,
                composed_fields=sorted(composed_fields),
            )
            vals.update(
                {
                    fname: value
                    for fname, value in self._prepare_assignment_vals(users).items()
                    if fname in composed_fields
                }
            )

        parent_id = vals.get("parent_id", self.env.context.get("default_parent_id"))
        if parent_id:
            parent = self.env["project.task"].browse(parent_id)
            if not vals.get("tag_ids"):
                vals["tag_ids"] = [Command.set(parent.tag_ids.ids)]

        if self.env.context.get("scale") in ("month", "year"):
            date_start = vals.get(
                "date_start", self.env.context.get("date_start", False)
            )
            date_end = vals.get("date_end", self.env.context.get("date_end", False))
            if date_start and date_end:
                user_ids = self.env.context.get("user_ids") or []
                date_start, date_end = self._get_planned_dates(
                    date_start, date_end, user_ids[0] if len(user_ids) == 1 else None
                )
                _debug.logic(
                    "default_planned_dates",
                    scale=self.env.context.get("scale"),
                    date_start=date_start,
                    date_end=date_end,
                )
                vals.update(date_start=date_start, date_end=date_end)

        _debug.lifecycle("default_get", fields=len(fields), keys=sorted(vals))
        return vals

    @api.model
    def _access_field_class(self, field: Any) -> str | None:
        # portal users read the fields listed readable and write those listed
        # writable; every other field is project.task_portal_hidden, the
        # automatic columns included (the whitelist names those portal reads)
        if field.name in self.TASK_PORTAL_WRITABLE_FIELDS:
            return None
        if field.name in self.TASK_PORTAL_READABLE_FIELDS:
            return "project.task_portal_readonly"
        return self._access_residual_class

    def _check_write_values_access(
        self, vals: dict[str, Any], defaults: bool = False
    ) -> None:
        _debug.logic(
            "write_values_access_checked",
            tasks=self,
            keys=sorted(vals),
            defaults=defaults,
        )
        if defaults:
            vals = {
                **{
                    key[8:]: value
                    for key, value in self.env.context.items()
                    if key.startswith("default_") and key[8:] in self._fields
                },
                **vals,
            }

        for fname, value in vals.items():
            field = self._fields.get(fname)
            if field and field.type == "many2one":
                self.env[field.comodel_name].browse(value).check_access("read")

    def _check_portal_move_access(self, vals: dict[str, Any]) -> None:
        moved = self.filtered(
            lambda task: (
                ("step_id" in vals and task.step_id.id != vals["step_id"])
                or ("priority" in vals and task.priority != vals["priority"])
            )
        )
        self._check_advanced_edit_access(moved.project_id)

    def _check_advanced_edit_access(self, projects: Any) -> None:
        if not projects:
            return
        advanced_projects = (
            self.env["project.collaborator"]
            .sudo()
            .search(
                [
                    ("project_id", "in", projects.ids),
                    ("is_current_user_collaboration", "=", True),
                    ("access_mode", "=", "advanced_edit"),
                ]
            )
            .project_id
        )
        if projects - advanced_projects:
            _debug.logic(
                "portal_move_refused",
                user=self.env.uid,
                projects=projects - advanced_projects,
            )
            raise AccessError(
                self.env._(
                    "Moving a task to another step or changing its priority "
                    "requires Advanced Edit access to the project."
                )
            )

    def _update_project_workflow_steps(self) -> None:
        step_ids_per_project = defaultdict(list)
        for task in self:
            if (
                task.step_id
                and task.step_id not in task.project_id.workflow_step_ids
                and task.step_id.id not in step_ids_per_project[task.project_id]
            ):
                step_ids_per_project[task.project_id].append(task.step_id.id)

        for project, step_ids in step_ids_per_project.items():
            _debug.pipeline("workflow_steps_linked", project=project.id, steps=step_ids)
            project.write(
                {"workflow_step_ids": [Command.link(step_id) for step_id in step_ids]}
            )

    def _load_records_create(self, vals_list: list[ValuesType]) -> Self:
        for vals in vals_list:
            if vals.get("recurring_task"):
                rec_fields = vals.keys() & self._get_fields_recurrence()
                if not vals.get("recurrence_id") and not rec_fields:
                    default_val = self.default_get(self._get_fields_recurrence())
                    vals.update(**default_val)
        return super()._load_records_create(vals_list)

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                count=len(vals_list),
                keys=sorted({k for vals in vals_list for k in vals}),
                uid=self.env.uid,
                portal=not self.env.su and self.env.user._is_portal(),
            )
        additional_vals_list = [{} for _ in vals_list]

        new_context = dict(self.env.context)
        default_triage = new_context.pop("default_triage_ids", False)
        default_project_id = new_context.pop("default_project_id", False)
        default_project_ids = self._get_default_project_ids(
            vals_list, default_project_id
        )
        new_context["default_create_in_project_id"] = default_project_id
        if not self._has_field_access(self._fields["user_ids"], "write"):
            new_context.pop("default_user_ids", False)
        self_ctx = self.with_context(new_context)

        self_ctx.browse().check_access("create")
        if self.env.su or not self.env.user._is_portal():
            # a project derived from the parent goes in the row itself, so the
            # batch is one create; a portal user may not write project_id
            for vals, derived_project_id in zip(
                vals_list, default_project_ids, strict=True
            ):
                if derived_project_id != default_project_id:
                    self_ctx._update_create_vals_derived_project(
                        vals, derived_project_id
                    )
            default_project_ids = [default_project_id] * len(vals_list)
        default_stage = {}
        for vals, additional_vals, vals_default_project_id in zip(
            vals_list, additional_vals_list, default_project_ids, strict=True
        ):
            self_ctx._update_create_vals(
                vals,
                additional_vals,
                default_project_id=vals_default_project_id,
                default_triage=default_triage,
                default_stage=default_stage,
            )

        for vals, computed_vals in zip(vals_list, additional_vals_list, strict=True):
            for field_name in list(computed_vals):
                if self_ctx._has_field_access(self_ctx._fields[field_name], "write"):
                    vals[field_name] = computed_vals.pop(field_name)
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "create_vals_prepared",
                sudo_only=sum(
                    1 for computed_vals in additional_vals_list if computed_vals
                ),
            )
        create_ctx = self_ctx.with_context(
            mail_create_nosubscribe=True,
            mail_notrack=not self_ctx.env.su and self_ctx.env.user._is_portal(),
        )
        indexes_per_project = defaultdict(list)
        for index, project_id in enumerate(default_project_ids):
            indexes_per_project[project_id].append(index)
        _debug.logic(
            "create_groups",
            default_projects=sorted(indexes_per_project, key=str),
        )
        task_ids = [0] * len(vals_list)
        with _debug.perf("super_create", cr=self.env.cr):
            for project_id, indexes in indexes_per_project.items():
                created = super(
                    ProjectTask,
                    create_ctx.with_context(default_create_in_project_id=project_id),
                ).create([vals_list[index] for index in indexes])
                for index, task_id in zip(indexes, created.ids, strict=True):
                    task_ids[index] = task_id
        tasks = self_ctx.browse(task_ids)
        _debug.lifecycle("created", tasks=tasks)
        grouped_tasks = defaultdict(self.env["project.task"].sudo)
        vals_by_key = {}
        for task, computed_vals in zip(tasks.sudo(), additional_vals_list, strict=True):
            if not computed_vals:
                continue
            key = repr(sorted(computed_vals.items(), key=lambda kv: kv[0]))
            grouped_tasks[key] |= task
            vals_by_key[key] = computed_vals
        _debug.pipeline(
            "create_sudo_write_groups", tasks=tasks, groups=len(grouped_tasks)
        )
        for key, group_tasks in grouped_tasks.items():
            _debug.logic(
                "create_sudo_write", keys=sorted(vals_by_key[key]), tasks=group_tasks
            )
            group_tasks.write(vals_by_key[key])
        _debug.pipeline("create_step", tasks=tasks, step="triages")
        privileged_tasks = tasks.sudo()
        privileged_tasks._create_missing_triages()
        if any(
            "predecessor_ids" in vals or "successor_ids" in vals for vals in vals_list
        ):
            tasks._invalidate_dependency_rows()
        _debug.pipeline("create_step", tasks=tasks, step="state_from_predecessors")
        privileged_tasks.filtered(
            lambda task: task.state in DELIVERED_STATES
        )._check_finish_dependencies()
        tasks._update_state_from_predecessors()
        _debug.pipeline("create_step", tasks=tasks, step="assignment_notify")
        self_ctx._task_message_auto_subscribe_notify(
            {task: task.user_ids - self_ctx.env.user for task in tasks}
        )

        current_partner = self_ctx.env.user.partner_id

        if tasks.project_id:
            _debug.pipeline("create_step", tasks=tasks, step="workflow_steps")
            tasks.sudo()._update_project_workflow_steps()
        _debug.pipeline("create_step", tasks=tasks, step="followers")
        self_ctx._subscribe_followers(tasks, current_partner)
        return tasks

    def _update_create_vals_derived_project(
        self, vals: dict[str, Any], project_id: int
    ) -> None:
        # what default_get gives a row whose project it knows: the parent's or
        # project's customer, and no assignee forced on a task that is not private
        project = self.env["project.project"].browse(project_id)
        vals["project_id"] = project_id
        if "partner_id" not in vals and "default_partner_id" not in self.env.context:
            partner_id = self._get_default_partner_id(
                project, self.browse(vals["parent_id"])
            )
            if partner_id:
                vals["partner_id"] = partner_id
        if "default_user_ids" not in self.env.context and (
            self._get_fields_assignment().isdisjoint(vals)
        ):
            vals["user_ids"] = [Command.set(self._default_user_ids())]
        _debug.logic(
            "create_project_derived",
            project=project_id,
            parent=vals["parent_id"],
            keys=sorted(vals),
        )

    def _get_default_project_ids(
        self, vals_list: list[ValuesType], default_project_id: int | bool
    ) -> list[int | bool]:
        if default_project_id:
            return [default_project_id] * len(vals_list)
        parents = self.browse(
            {
                vals["parent_id"]
                for vals in vals_list
                if vals.get("parent_id") and "project_id" not in vals
            }
        ).sudo()
        project_per_parent = {parent.id: parent.project_id.id for parent in parents}
        return [
            project_per_parent.get(vals.get("parent_id"), False)
            if "project_id" not in vals
            else False
            for vals in vals_list
        ]

    @_debug.perf.timed
    def _subscribe_followers(self, tasks: Self, current_partner: Any) -> None:
        tasks_sudo = tasks.sudo()
        # the creator first: a creator who also follows the parent then gets the
        # parent's subtypes, which replace the ones derived from the project
        tasks_sudo.message_subscribe(current_partner.ids)
        tasks_sudo._subscribe_parent_followers()
        emails_per_task = {
            task: tools.email_normalize_all(task.email_cc)
            for task in tasks_sudo
            if task.email_cc
        }
        if not emails_per_task:
            return
        partners = self.env["res.partner"].search(
            [
                (
                    "email_normalized",
                    "in",
                    list(
                        {
                            email
                            for emails in emails_per_task.values()
                            for email in emails
                        }
                    ),
                )
            ]
        )
        partner_per_email = defaultdict(lambda: self.env["res.partner"])
        for partner in partners:
            if not all(u.share for u in partner.user_ids):
                partner_per_email[partner.email_normalized] |= partner
        _debug.logic(
            "cc_partners_resolved",
            tasks=tasks,
            partners=len(partners),
            internal=len(partner_per_email),
        )
        for task, emails in emails_per_task.items():
            partners_with_internal_user = self.env["res.partner"].union(
                *(
                    partner_per_email[email]
                    for email in emails
                    if email in partner_per_email
                )
            )
            if not partners_with_internal_user:
                continue
            _debug.pipeline(
                "cc_partners_notified",
                task=task.id,
                partners=partners_with_internal_user,
            )
            task._send_email_notify_to_cc(partners_with_internal_user)
            task.message_subscribe(partners_with_internal_user.ids)

    def _subscribe_parent_followers(self) -> None:
        subtypes_per_task = {
            task.id: {
                follower.partner_id.id: follower.subtype_ids.ids
                for follower in task.parent_id.message_follower_ids
                if follower.partner_id.active
            }
            for task in self.filtered("parent_id")
        }
        subtypes_per_task = {k: v for k, v in subtypes_per_task.items() if v}
        _debug.logic(
            "parent_followers_propagated",
            tasks=self,
            with_parent_followers=len(subtypes_per_task),
        )
        if subtypes_per_task:
            self.env["mail.followers"]._add_followers_multi(
                self._name,
                subtypes_per_task,
                check_existing=True,
                existing_policy="replace",
            )

    def _write_split_by_default_planned_dates(
        self, vals: dict[str, Any]
    ) -> bool | None:
        if len(self) < 2 or not (vals.get("date_start") and vals.get("date_end")):
            return None
        if any(task.date_start or task.date_end for task in self):
            return None

        scoped = self.with_context(skip_default_planned_dates=True)
        result = True
        for calendar, tasks in (
            self.sudo()._get_tasks_by_resource_calendar_dict().items()
        ):
            date_start, date_stop = self._get_planned_dates(
                vals["date_start"], vals["date_end"], calendar=calendar
            )
            _debug.logic(
                "write_split_by_planned_dates",
                calendar=calendar.id,
                tasks=tasks,
                date_start=date_start,
                date_stop=date_stop,
            )
            result = (
                scoped.browse(tasks.ids).write(
                    {**vals, "date_start": date_start, "date_end": date_stop}
                )
                and result
            )
        return result

    @_debug.perf.timed
    def write(self, vals: dict[str, Any]) -> bool:
        _debug.lifecycle("write", tasks=self, keys=sorted(vals), uid=self.env.uid)
        vals = dict(vals)
        if "date_end" in vals and not vals["date_end"]:
            vals["date_start"] = False

        if not self.env.context.get("skip_default_planned_dates"):
            split = self._write_split_by_default_planned_dates(vals)
            if split is not None:
                _debug.pipeline("write_split_by_calendar", tasks=self)
                return split

        self.check_access("write")
        if len(self) == 1:
            handle_history_divergence(self, "description", vals)

        additional_vals = {}
        if self.env.user._is_portal() and not self.env.su:
            self._check_write_values_access(vals, defaults=False)
            self._check_portal_move_access(vals)

        self._write_propagate_milestone(vals)

        if vals.get("parent_id") in self.ids:
            raise UserError(
                self.env._("Sorry. You can't set a task as its parent task.")
            )
        self._check_no_self_dependency(vals)

        now = fields.Datetime.now()
        state_changed = (
            self.filtered(lambda task: task.state != vals["state"])
            if "state" in vals
            else self.browse()
        )
        self._write_apply_step_change(vals, additional_vals, now)

        assigns = not self._get_fields_assignment().isdisjoint(vals)
        task_ids_without_user_set = set()
        if assigns and "date_assign" not in vals:
            task_ids_without_user_set = {task.id for task in self if not task.user_ids}

        recurrence_scope = self._write_capture_recurrence_scope(vals)
        self._write_sync_recurrence(vals)

        old_user_ids = {t: t.user_ids for t in self.sudo()} if assigns else {}

        self._write_clear_triage(vals)
        partner_ids, project_link_per_task_id = self._write_prepare_transfer_notice(
            vals
        )

        if vals.get("parent_id") is False:
            additional_vals["display_in_project"] = True
        if "description" in vals:
            additional_vals["description"] = vals.pop("description")

        if self.env.su or not self.env.user._is_portal():
            vals.update(additional_vals)
        elif additional_vals:
            _debug.logic("portal_sudo_write", tasks=self, keys=sorted(additional_vals))
            super(ProjectTask, self.sudo()).write(additional_vals)
        step_tracked = self.browse()
        if "state" not in vals and ("step_id" in vals or "project_id" in vals):
            step_tracked = self
            if "project_id" in vals:
                # subtasks that follow their parent change project, and so step,
                # through the recompute rather than through a write of their own
                step_tracked |= self._get_all_subtasks().filtered(
                    lambda task: not task.display_in_project
                )
        step_before = {task.id: task.step_id for task in step_tracked}
        _debug.pipeline("write_step", tasks=self, step="super_write", keys=sorted(vals))
        with _debug.perf("super_write", cr=self.env.cr):
            result = super().write(vals)

        if "predecessor_ids" in vals or "successor_ids" in vals:
            self._invalidate_dependency_rows()

        self._write_propagate_recurrence(recurrence_scope, vals)

        self._write_apply_assignment(vals, now, task_ids_without_user_set, assigns)
        entered = step_tracked.filtered(
            lambda task: task.step_id != step_before[task.id]
        )
        entered._write_send_step_rating()
        entered._apply_entered_step_state()
        self._write_apply_state(vals, now, state_changed)

        if "parent_id" in vals:
            self.env.remove_to_compute(self._fields["state"], self)

        if old_user_ids:
            _debug.pipeline("write_step", tasks=self, step="assignment_notify")
            self._task_message_auto_subscribe_notify(
                {
                    task: task.user_ids - old_user_ids[task] - self.env.user
                    for task in self
                }
            )
        self._write_notify_transfer(partner_ids, project_link_per_task_id)
        return result

    def _update_create_vals(
        self,
        vals: dict[str, Any],
        additional_vals: dict[str, Any],
        *,
        default_project_id: int | bool,
        default_triage: Any,
        default_stage: dict[int, int | bool],
    ) -> None:
        project_id = vals.get("project_id", default_project_id)

        assignees = self._get_assigned_users(vals)
        # A task with no project is private to its assignees, so a creator who
        # is not one of them could not read back what they just created; given
        # no assignee at all, the creator is the one (default_get does the same
        # when the vals name none).
        if (
            not (vals.get("parent_id") or project_id)
            and not self._get_fields_assignment().isdisjoint(vals)
            and self.env.user
            not in (assignees | self.env["res.users"].browse(SUPERUSER_ID))
        ):
            assignees |= self.env.user
            additional_vals.update(
                self._prepare_assignment_vals_keeping(vals, assignees)
            )
        if assignees:
            additional_vals["date_assign"] = fields.Datetime.now()
        if default_triage and "triage_id" not in vals:
            additional_vals["triage_id"] = default_triage[0]
        if not vals.get("name") and vals.get("display_name"):
            vals["name"] = vals["display_name"]

        if self.env.user._is_portal() and not self.env.su:
            self._check_write_values_access(vals, defaults=True)
            if project_id and ("step_id" in vals or vals.get("priority", "0") != "0"):
                self._check_advanced_edit_access(
                    self.env["project.project"].browse(project_id)
                )

        if project_id and "company_id" not in vals:
            additional_vals["company_id"] = (
                self.env["project.project"].browse(project_id).company_id.id
            )
        if not project_id and (
            "step_id" in vals or self.env.context.get("default_step_id")
        ):
            vals["step_id"] = False

        if project_id and "step_id" not in vals:
            if project_id not in default_stage:
                default_stage[project_id] = (
                    self.with_context(default_project_id=project_id)
                    .default_get(["step_id"])
                    .get("step_id")
                )
            vals["step_id"] = default_stage[project_id]

        if vals.get("step_id"):
            additional_vals["date_last_status_change"] = fields.Datetime.now()
        rec_fields = vals.keys() & self._get_fields_recurrence()
        if rec_fields and vals.get("recurring_task") is True:
            rec_values = {rec_field: vals[rec_field] for rec_field in rec_fields}
            recurrence = self.env["project.task.recurrence"].create(rec_values)
            vals["recurrence_id"] = recurrence.id
            _debug.lifecycle(
                "recurrence_created", recurrence=recurrence.id, values=rec_values
            )
        _debug.logic(
            "create_vals_updated",
            project=project_id,
            step=vals.get("step_id"),
            additional=sorted(additional_vals),
        )

    def _write_propagate_milestone(self, vals: dict[str, Any]) -> None:
        if "milestone_id" in vals:
            milestone_id_val = vals["milestone_id"]
            milestone = self.env["project.milestone"].browse(milestone_id_val)

            if "project_id" not in vals:
                unvalid_milestone_tasks = (
                    self.filtered(lambda task: task.project_id != milestone.project_id)
                    if vals["milestone_id"]
                    else self.env["project.task"]
                )
            else:
                unvalid_milestone_tasks = (
                    self
                    if not vals["milestone_id"]
                    or milestone.project_id.id != vals["project_id"]
                    else self.env["project.task"]
                )
            valid_milestone_tasks = self - unvalid_milestone_tasks
            _debug.logic(
                "milestone_propagated",
                tasks=self,
                milestone=milestone_id_val,
                valid=valid_milestone_tasks,
                invalid=unvalid_milestone_tasks,
            )
            if unvalid_milestone_tasks:
                unvalid_milestone_tasks.sudo().write({"milestone_id": False})
                if valid_milestone_tasks:
                    valid_milestone_tasks.sudo().write(
                        {"milestone_id": milestone_id_val}
                    )
                del vals["milestone_id"]

            subtasks_to_update = valid_milestone_tasks.child_ids.filtered(
                lambda task: (
                    task not in self
                    and not task.milestone_id
                    and task.project_id == milestone.project_id
                    and task.state not in CLOSED_STATES
                )
            )

            if "project_id" not in vals:
                subtasks_to_update |= valid_milestone_tasks.child_ids.filtered(
                    lambda task: (
                        task not in self
                        and task.milestone_id == task.parent_id.milestone_id
                        and task.state not in CLOSED_STATES
                    )
                )
            else:
                subtasks_to_update |= valid_milestone_tasks.child_ids.filtered(
                    lambda task: (
                        task not in self
                        and (
                            not task.display_in_project
                            or task.project_id.id == vals["project_id"]
                        )
                        and task.milestone_id == task.parent_id.milestone_id
                        and task.state not in CLOSED_STATES
                    )
                )
            if subtasks_to_update:
                _debug.pipeline(
                    "milestone_propagated_to_subtasks",
                    tasks=self,
                    subtasks=subtasks_to_update,
                )
                subtasks_to_update.sudo().write({"milestone_id": milestone_id_val})

    def _write_apply_step_change(
        self, vals: dict[str, Any], additional_vals: dict[str, Any], now: Any
    ) -> None:
        if "step_id" in vals:
            if (
                vals["step_id"]
                and "project_id" not in vals
                and self.filtered(lambda t: not t.project_id)
            ):
                raise UserError(
                    self.env._(
                        "A private task has no workflow step — steps belong to a "
                        "project's board. Move the task into a project first, or "
                        "use a personal triage bucket to organise it."
                    )
                )

            moving = self.filtered(lambda task: task.step_id.id != vals["step_id"])
            _debug.logic(
                "step_changed", tasks=self, step=vals["step_id"], moving=moving
            )
            if moving == self:
                additional_vals["date_last_status_change"] = now
            elif moving:
                moving.sudo().date_last_status_change = now

    def _get_recurrence_sort_key(self) -> tuple:
        self.check_singleton()
        dated = bool(self.date_end)
        return (not dated, self.date_end if dated else None, self.id)

    def _write_capture_recurrence_scope(self, vals: dict[str, Any]) -> dict | None:
        if "recurrence_update" in vals:
            field = self._fields["recurrence_update"]
            if not self._has_field_access(field, "write"):
                raise AccessError(
                    self.env._(
                        "You are not allowed to update all tasks of a recurrence."
                    )
                )

        scope = vals.pop("recurrence_update", "this")
        if scope == "this" or not self.recurrence_id:
            return None
        self.check_singleton()

        rule_fields = vals.keys() & set(self._get_fields_recurrence())
        if rule_fields and scope != "all":
            raise UserError(
                self.env._(
                    "Changing how often a task repeats applies to the whole "
                    "recurrence. Select 'All tasks' to confirm."
                )
            )

        siblings = self.recurrence_id.task_ids - self
        if scope == "subsequent":
            mine = self._get_recurrence_sort_key()
            siblings = siblings.filtered(lambda t: t._get_recurrence_sort_key() > mine)
        _debug.logic(
            "recurrence_scope_captured",
            tasks=self,
            scope=scope,
            recurrence=self.recurrence_id.id,
            targets=siblings,
        )
        postponed = set(self.recurrence_id._get_recurring_fields_to_postpone())
        return {
            "targets": siblings,
            "shift_from": {fname: self[fname] for fname in postponed & vals.keys()},
        }

    def _write_propagate_recurrence(
        self, scope: dict | None, vals: dict[str, Any]
    ) -> None:
        if not scope:
            return
        shifted = scope["shift_from"]
        if shifted:
            self.recurrence_id.sudo().write(
                {"date_recurrence_origin": False, "recurrence_anchor_field": False}
            )
        targets = scope["targets"].exists()
        if not targets:
            return

        plain = {
            fname: value
            for fname, value in vals.items()
            if fname not in shifted and fname not in self._get_fields_recurrence()
        }
        _debug.pipeline(
            "recurrence_propagated",
            tasks=self,
            targets=targets,
            plain=sorted(plain),
            shifted=sorted(shifted),
        )
        if plain:
            targets.write(plain)

        deltas = {
            fname: new_value - old_value
            for fname, old_value in shifted.items()
            if old_value and (new_value := fields.Datetime.to_datetime(vals[fname]))
        }
        if not deltas:
            return
        for task in targets:
            if shifted_vals := {
                fname: task[fname] + delta
                for fname, delta in deltas.items()
                if task[fname]
            }:
                task.write(shifted_vals)

    def _write_sync_recurrence(self, vals: dict[str, Any]) -> None:
        rec_fields = vals.keys() & self._get_fields_recurrence()
        if rec_fields:
            rec_values = {rec_field: vals[rec_field] for rec_field in rec_fields}
            if recurrences := self.recurrence_id:
                _debug.lifecycle(
                    "recurrence_updated", recurrences=recurrences, values=rec_values
                )
                recurrences.write(rec_values)
            if vals.get("recurring_task"):
                for task in self.filtered(lambda t: not t.recurrence_id):
                    recurrence = self.env["project.task.recurrence"].create(rec_values)
                    _debug.lifecycle(
                        "recurrence_created", task=task, recurrence=recurrence.id
                    )
                    task.recurrence_id = recurrence.id

        if not vals.get("recurring_task", True) and self.recurrence_id:
            recurrences = self.recurrence_id
            recurrences._end()

    def _write_clear_triage(self, vals: dict[str, Any]) -> None:
        if "triage_id" in vals and not vals["triage_id"]:
            del vals["triage_id"]
            self.env["project.task.triage"].sudo().search(
                [("task_id", "in", self.ids), ("user_id", "=", self.env.uid)]
            ).triage_id = False

    def _write_prepare_transfer_notice(
        self, vals: dict[str, Any]
    ) -> tuple[list[int], dict[int, Any]]:
        partner_ids = []
        project_link_per_task_id = {}
        if vals.get("project_id"):
            project = self.env["project.project"].browse(vals.get("project_id"))
            notification_subtype_id = self.env["ir.model.data"]._xmlid_to_res_id(
                "project.mt_project_task_new"
            )
            partner_ids = project.message_follower_ids.filtered(
                lambda follower: notification_subtype_id in follower.subtype_ids.ids
            ).partner_id.ids
            _debug.logic(
                "transfer_notice_prepared",
                tasks=self,
                project=project.id,
                followers=len(partner_ids),
            )
            if partner_ids:
                link_per_project = {
                    source: source and source._get_html_link(title=source.display_name)
                    for source in self.project_id
                }
                link_per_project[self.env["project.project"]] = None
                project_link_per_task_id = {
                    task.id: link_per_project[task.project_id]
                    for task in self
                    if task.project_id != project
                }
        return partner_ids, project_link_per_task_id

    def _copy_data_assignment(self, vals, default, has_default_users) -> None:
        """Who the copy is for.

        A caller naming `user_ids` names the assignees outright, so the fields a
        layer composes it from are dropped rather than left to contradict it.
        Otherwise the copy carries this task's assignees, minus whoever can no
        longer work on it -- an archived assignee used to disappear only because
        reading the composed fields hid them, which is a read's business, not a
        copy's.
        """
        self.check_singleton()
        composed = self._get_fields_assignment() - {"user_ids"}
        if has_default_users:
            for fname in composed:
                vals.pop(fname, None)
            return
        for fname in self._get_fields_assignment():
            if fname in default or not vals.get(fname):
                continue
            vals[fname] = [Command.set(self._filter_active_assignees(self[fname]).ids)]

    @api.model
    def _prepare_assignment_vals(self, users) -> dict[str, Any]:
        """The vals that assign `users`, through the fields this layer carries
        assignment on: writing `user_ids` is not enough where it is composed."""
        return {"user_ids": [Command.set(users.ids)]}

    @api.model
    def _prepare_assignment_vals_keeping(
        self, vals: dict[str, Any], users
    ) -> dict[str, Any]:
        # the assignment is rebuilt from users, so a given assignee that stands
        # for no user (project_hr's employee without one) is carried over
        assignment = self._prepare_assignment_vals(users)
        for fname, value in assignment.items():
            if fname not in vals:
                continue
            given_ids = self._fields[fname].convert_to_cache(
                vals[fname], self.browse(), validate=False
            )
            kept_ids = [
                record_id
                for record_id in given_ids
                if not self._get_assigned_users({fname: [Command.set([record_id])]})
            ]
            if kept_ids:
                prepared_ids = self._fields[fname].convert_to_cache(
                    value, self.browse(), validate=False
                )
                _debug.logic("assignees_without_user_kept", field=fname, kept=kept_ids)
                assignment[fname] = [Command.set([*prepared_ids, *kept_ids])]
        return assignment

    def _filter_active_assignees(self, assignees):
        return assignees.filtered("active")

    def _get_fields_assignment(self) -> set[str]:
        """The fields a write changes the assignees through.

        `user_ids` is the assignment everything downstream reads, but it is not
        always what a write carries: project_hr composes it from employees and from
        users without one, and a layer that does that must name its own fields here
        or every hook keyed on an assignment change stops firing.
        """
        return {"user_ids"}

    def _write_apply_assignment(
        self,
        vals: dict[str, Any],
        now: Any,
        task_ids_without_user_set: set[int],
        assigns: bool = False,
    ) -> None:
        if assigns:
            self._create_missing_triages()
            self._remove_orphan_triages()
            tasks = self.sudo()
            unassigned = tasks.filtered(lambda t: not t.user_ids and t.date_assign)
            if unassigned:
                unassigned.date_assign = False
            newly_assigned = self.browse()
            if "date_assign" not in vals:
                newly_assigned = (tasks - unassigned).filtered(
                    lambda t: t.id in task_ids_without_user_set and t.user_ids
                )
                if newly_assigned:
                    newly_assigned.date_assign = now
            _debug.logic(
                "assignment_changed",
                tasks=self,
                unassigned=unassigned,
                newly_assigned=newly_assigned,
            )

    def _write_send_step_rating(self) -> None:
        rated = self.sudo().filtered(
            lambda x: x.step_id.rating_active and x.step_id.rating_status == "stage"
        )
        if rated:
            _debug.pipeline(
                "write_step", tasks=self, step="step_rating_mail", rated=rated
            )
            rated._send_task_rating_mail(force_send=True)

    def _apply_entered_step_state(self) -> None:
        task_ids_per_state = defaultdict(list)
        privileged = self.sudo()
        for task in privileged:
            state = task._resolve_entered_step_state(task.state)
            if state and state != task.state:
                task_ids_per_state[state].append(task.id)
        for state, task_ids in task_ids_per_state.items():
            changed = privileged.browse(task_ids)
            _debug.logic(
                "entered_step_state",
                steps=changed.step_id,
                tasks=changed,
                state=state,
                closed_waiting=changed.filtered(lambda t: t.state == "blocked"),
            )
            changed.state = state

    def _write_apply_state(
        self, vals: dict[str, Any], now: Any, state_changed: Self
    ) -> None:
        if "state" in vals:
            _debug.lifecycle(
                "state_changed", tasks=self, state=vals["state"], changed=state_changed
            )
            if state_changed:
                changed = state_changed.sudo()
                if vals["state"] in DELIVERED_STATES:
                    changed._check_finish_dependencies()
                changed.date_last_status_change = now
            if vals["state"] not in CLOSED_STATES and vals["state"] != "blocked":
                for task in self.sudo():
                    if task.allow_dependencies and task.is_blocked_by_predecessors():
                        _debug.logic(
                            "state_reblocked", task=task, reason="predecessors"
                        )
                        task.state = "blocked"

    def _write_notify_transfer(
        self, partner_ids: list[int], project_link_per_task_id: dict[int, Any]
    ) -> None:
        if not partner_ids:
            return
        _debug.pipeline(
            "write_step", tasks=self, step="transfer_notice", partners=len(partner_ids)
        )
        for task in self.filtered(lambda t: t.id in project_link_per_task_id):
            project_link = project_link_per_task_id[task.id]
            if project_link:
                body = self.env._(
                    "Task Transferred from Project %(source_project)s to %(destination_project)s",
                    source_project=project_link,
                    destination_project=task.project_id._get_html_link(
                        title=task.project_id.display_name
                    ),
                )
            else:
                body = self.env._("Task Converted from To-Do")
            task.message_notify(
                body=body,
                partner_ids=partner_ids,
                email_layout_xmlid="mail.mail_notification_layout",
                notify_author_mention=False,
            )

    @_debug.perf.timed
    def unlink(self) -> bool:
        requested = self
        self |= self.with_context(active_test=False)._get_all_subtasks()
        _debug.lifecycle("unlink", tasks=requested, subtasks=len(self) - len(requested))
        last_task_id_per_recurrence_id = (
            self.recurrence_id._get_last_task_id_per_recurrence_id()
        )
        self.recurrence_id.filtered(
            lambda recurrence: (
                last_task_id_per_recurrence_id.get(recurrence.id) in self.ids
            )
        )._end(deleted_tasks=self)
        return super().unlink()

    def _get_fields_reservation_date(self) -> tuple:
        return ("date_start", "date_end")

    def _prepare_reservation_vals_list(self):
        self.check_singleton()
        start_field, end_field = self._get_fields_reservation_date()
        if not start_field or not end_field:
            return []
        date_start = self[start_field]
        date_end = self[end_field]
        if not date_start or not date_end:
            return []

        vals_list = []
        for user in self.user_ids:
            get_resource = getattr(user, "_get_project_task_resource", None)
            if not get_resource:
                continue
            scoped = user.with_company(user.company_id) if user.company_id else user
            resource = scoped._get_project_task_resource()
            if not resource:
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
        _debug.logic(
            "reservation_vals_prepared",
            tasks=self,
            users=len(self.user_ids),
            reservations=len(vals_list),
        )
        return vals_list

    def _get_fields_sync_trigger(self):
        triggers = super()._get_fields_sync_trigger()
        triggers |= {"user_ids", "allocated_percentage", "name"}
        return triggers

    @api.onchange("date_end", "date_start")
    def _onchange_planned_dates(self):
        if not self.date_end:
            self.date_start = False

    def action_unschedule_task(self) -> None:
        _debug.lifecycle("unscheduled", tasks=self)
        self.write(
            {
                "date_start": False,
                "date_end": False,
            }
        )

    @api.model
    def _get_planned_dates(
        self, date_start, date_stop, user_id=None, calendar=None
    ) -> tuple:
        if not (date_start and date_stop):
            raise UserError(
                self.env._(
                    "One parameter is missing to use this method. "
                    "You should give a start and end dates."
                )
            )
        start, stop = date_start, date_stop
        if isinstance(start, str):
            start = fields.Datetime.from_string(start)
        if isinstance(stop, str):
            stop = fields.Datetime.from_string(stop)

        if not calendar:
            user = (
                self.env["res.users"].sudo().browse(user_id)
                if user_id and user_id != self.env.user.id
                else self.env.user
            )
            calendar = (
                user.resource_calendar_id or self.env.company.resource_calendar_id
            )
            if not calendar:
                _debug.logic(
                    "planned_dates_unchanged", user=user.id, reason="no_calendar"
                )
                return date_start, date_stop

        if not start.tzinfo:
            start = start.replace(tzinfo=UTC)
        if not stop.tzinfo:
            stop = stop.replace(tzinfo=UTC)

        with _debug.perf("planned_dates_work_intervals", cr=self.env.cr):
            intervals = calendar._work_intervals_batch(start, stop)[False]
        if not intervals:
            _debug.logic(
                "planned_dates_unchanged",
                start=start,
                stop=stop,
                calendar=calendar.id,
                reason="no_work_interval",
            )
            return date_start, date_stop
        list_intervals = [(s, e) for s, e, _records in intervals]
        start = list_intervals[0][0].astimezone(UTC).replace(tzinfo=None)
        stop = list_intervals[-1][1].astimezone(UTC).replace(tzinfo=None)
        _debug.logic(
            "planned_dates_computed",
            date_start=date_start,
            date_stop=date_stop,
            start=start,
            stop=stop,
            calendar=calendar.id,
        )
        return start, stop

    def action_view_schedule(self) -> dict:
        self.check_singleton()
        resources = self.env["resource.resource"]
        for user in self.user_ids:
            get_resource = getattr(user, "_get_project_task_resource", None)
            if get_resource:
                resource = get_resource()
                if resource:
                    resources |= resource

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

    def _search_on_comodel(
        self,
        domain: list,
        field_name: str,
        comodel: str,
        additional_domain: list | None = None,
    ) -> list | bool:
        def get_domain_on_id_and_name(domain) -> Domain:
            new_domain = []
            for dom in domain:
                if len(dom) == 3:
                    _, op, value = dom
                    if op in ("any", "not any"):
                        new_op = "in" if op == "any" else "not in"
                        ids = [
                            val[2]
                            for val in value
                            if isinstance(val, (tuple, list))
                            and isinstance(val[2], int)
                        ]
                        new_domain.append(("id", new_op, ids))
                        continue
                    op = "ilike" if op == "child_of" else op
                    if isinstance(value, (list, tuple)):
                        ids = [val for val in value if isinstance(val, int)]
                        names = [val for val in value if isinstance(val, str)]
                        if ids and names:
                            negative = op == "!=" or op.startswith("not ")
                            new_domain.append("&" if negative else "|")
                        if ids:
                            new_domain.append(("id", op, ids))
                        if names:
                            new_domain.append(("name", op, names))
                    elif isinstance(value, str):
                        new_domain.append(("name", op, value))
                    if isinstance(value, int):
                        if op == "=":
                            op = "in"
                        if op == "!=":
                            op = "not in"
                        new_domain.append(("id", op, [value]))
                else:
                    new_domain.append(dom)
            return Domain(new_domain)

        filtered_domain = filter_domain_leaf(
            domain,
            lambda field_to_check: (
                field_to_check
                in [
                    field_name,
                    f"{field_name}.id",
                    f"{field_name}.name",
                ]
            ),
            {
                field_name: "name",
                f"{field_name}.id": "id",
                f"{field_name}.name": "name",
            },
        )
        if filtered_domain.is_true():
            return self.env[comodel]
        filtered_domain = get_domain_on_id_and_name(filtered_domain)
        if additional_domain:
            filtered_domain &= Domain(additional_domain)
        return self.env[comodel].search(filtered_domain)

    @api.depends(
        "parent_id",
        "parent_id.partner_id",
        "project_id",
        "project_id.partner_id",
        "has_template_ancestor",
    )
    def _compute_partner_id(self) -> None:
        for task in self:
            if task.has_template_ancestor:
                continue
            if task.partner_id and not (task.project_id or task.parent_id):
                _debug.logic(
                    "partner_cleared",
                    task=task,
                    partner=task.partner_id.id,
                    reason="private",
                )
                task.partner_id = False
                continue
            if not task.partner_id:
                task.partner_id = self._get_default_partner_id(
                    task.project_id, task.parent_id
                )

    @api.depends("project_id")
    def _compute_milestone_id(self) -> None:
        for task in self:
            if task.project_id != task.milestone_id.project_id:
                task.milestone_id = (
                    task.parent_id.project_id == task.project_id
                    and task.parent_id.milestone_id
                )

    @_debug.perf.timed
    @api.depends(
        "allow_milestones",
        "milestone_id",
        "milestone_id.is_reached",
        "milestone_id.date_deadline",
    )
    def _compute_has_late_and_unreached_milestone(self) -> None:
        if all(not task.allow_milestones for task in self):
            self.has_late_and_unreached_milestone = False
            return
        late_milestones = (
            self.env["project.milestone"]
            .sudo()
            ._search(
                [
                    ("id", "in", self.milestone_id.ids),
                    ("is_reached", "=", False),
                    ("date_deadline", "<", fields.Date.today()),
                ]
            )
        )
        for task in self:
            task.has_late_and_unreached_milestone = (
                task.allow_milestones and task.milestone_id.id in late_milestones
            )

    def _search_has_late_and_unreached_milestone(
        self, operator: str, value: Any
    ) -> list:
        if operator != "in":
            return NotImplemented
        return [
            ("allow_milestones", "=", True),
            (
                "milestone_id",
                "any",
                [
                    ("is_reached", "=", False),
                    ("date_deadline", "<", fields.Date.today()),
                ],
            ),
        ]

    def _notify_by_email_prepare_rendering_context(
        self,
        message: Any,
        msg_vals: dict | Literal[False] = False,
        model_description: str | Literal[False] = False,
        force_email_company: Any = False,
        force_email_lang: str | Literal[False] = False,
        force_record_name: str | Literal[False] = False,
        tracking_values: Any = None,
    ) -> dict:
        render_context = super()._notify_by_email_prepare_rendering_context(
            message,
            msg_vals=msg_vals,
            model_description=model_description,
            force_email_company=force_email_company,
            force_email_lang=force_email_lang,
            force_record_name=force_record_name,
            tracking_values=tracking_values,
        )
        project_name = self.project_id.sudo().name
        stage_name = self.step_id.name
        subtitles = ""
        if project_name and stage_name:
            subtitles = self.env._(
                "Project: %(project_name)s, Stage: %(stage_name)s",
                project_name=project_name,
                stage_name=stage_name,
            )
        elif project_name:
            subtitles = self.env._(
                "Project: %(project_name)s", project_name=project_name
            )
        elif stage_name:
            subtitles = self.env._("Stage: %(stage_name)s", stage_name=stage_name)
        if subtitles:
            render_context["subtitles"].append(subtitles)
        return render_context

    def _send_email_notify_to_cc(self, partners_to_notify: Self) -> None:
        self.check_singleton()
        template_id = self.env["ir.model.data"]._xmlid_to_res_id(
            "project.task_invitation_follower", raise_if_not_found=False
        )
        if not template_id:
            return
        task_model_description = self.env["ir.model"]._get(self._name).display_name
        values = {
            "object": self,
        }
        _debug.pipeline("cc_notified", task=self.id, partners=partners_to_notify)
        for partner in partners_to_notify:
            values["partner_name"] = partner.name
            assignation_msg = self.env["ir.qweb"]._render(
                "project.task_invitation_follower",
                values,
                minimal_qcontext=True,
            )
            self.message_notify(
                subject=self.env._(
                    "You have been invited to follow %s", self.display_name
                ),
                body=assignation_msg,
                partner_ids=partner.ids,
                email_layout_xmlid="mail.mail_notification_layout",
                model_description=task_model_description,
                mail_auto_delete=True,
            )

    @_debug.perf.timed
    @api.model
    def _task_message_auto_subscribe_notify(self, users_per_task: dict) -> None:
        if self.env.context.get("mail_auto_subscribe_no_notify"):
            _debug.logic(
                "assignment_notify_skipped", reason="mail_auto_subscribe_no_notify"
            )
            return
        template_id = self.env["ir.model.data"]._xmlid_to_res_id(
            "project.project_message_user_assigned", raise_if_not_found=False
        )
        if not template_id:
            return
        task_model_description = self.env["ir.model"]._get(self._name).display_name
        for task, users in users_per_task.items():
            if not users:
                continue
            _debug.pipeline("assignment_notified", task=task.id, users=users)
            values = {
                "object": task,
                "model_description": task_model_description,
                "access_link": task._notify_get_action_link("view"),
            }
            for user in users:
                values.update(assignee_name=user.sudo().name)
                assignation_msg = self.env["ir.qweb"]._render(
                    "project.project_message_user_assigned",
                    values,
                    minimal_qcontext=True,
                )
                assignation_msg = self.env["mixin.mail.render"]._replace_local_links(
                    assignation_msg
                )
                task.message_notify(
                    subject=self.env._(
                        "You have been assigned to %s", task.display_name
                    ),
                    body=assignation_msg,
                    partner_ids=user.partner_id.ids,
                    email_layout_xmlid="mail.mail_notification_layout",
                    model_description=task_model_description,
                    mail_auto_delete=True,
                )

    def _get_assigned_users(self, values: dict[str, Any]):
        """The users an assignment reaches, whatever field carried it.

        A layer that composes `user_ids` from fields of its own answers for the
        users behind them: values are read before the write, so the composed field
        cannot be read back from the record yet.
        """
        if "user_ids" not in values:
            return self.env["res.users"]
        return self.env["res.users"].browse(
            self._fields["user_ids"].convert_to_cache(
                values.get("user_ids", []),
                self.env["project.task"],
                validate=False,
            )
        )

    def _message_auto_subscribe_followers(
        self, updated_values: dict[str, Any], default_subtype_ids: list[int]
    ) -> list:
        return [
            (partner.id, default_subtype_ids, False)
            for partner in self._get_assigned_users(updated_values).partner_id
        ]

    def _mail_warm_auto_subscribe_users(self, vals_per_record: dict) -> None:
        super()._mail_warm_auto_subscribe_users(vals_per_record)
        users = self.env["res.users"].union(
            *(self._get_assigned_users(values) for values in vals_per_record.values())
        )
        if len(users) > 1:
            users.sudo().fetch(["partner_id"])

    def _track_template(self, changes: Collection[str]) -> dict:
        res = super()._track_template(changes)
        test_task = self[0]
        if (
            "step_id" in changes
            and test_task.step_id.mail_template_id
            and not test_task.is_template
        ):
            res["step_id"] = (
                test_task.step_id.mail_template_id,
                {
                    "auto_delete_keep_log": False,
                    "subtype_id": self.env["ir.model.data"]._xmlid_to_res_id(
                        "mail.mt_note"
                    ),
                    "email_layout_xmlid": "mail.mail_notification_light",
                },
            )
        return res

    def _creation_subtype(self) -> Self:
        return self.env.ref("project.mt_task_new")

    def _creation_message(self) -> str:
        self.check_singleton()
        if self.project_id:
            return self.env._(
                'A new task has been created in the "%(project_name)s" project.',
                project_name=self.project_id.display_name,
            )
        return self.env._("A new task has been created and is not part of any project.")

    def _track_subtype(self, init_values: dict[str, Any]) -> Self:
        self.check_singleton()
        mail_message_subtype_per_state = {
            "done": "project.mt_task_done",
            "canceled": "project.mt_task_canceled",
            "in_progress": "project.mt_task_in_progress",
            "approved": "project.mt_task_approved",
            "changes_requested": "project.mt_task_changes_requested",
            "blocked": "project.mt_task_waiting",
        }

        if "step_id" in init_values:
            return self.env.ref("project.mt_task_stage")
        elif "state" in init_values and self.state in mail_message_subtype_per_state:
            return self.env.ref(mail_message_subtype_per_state[self.state])
        return super()._track_subtype(init_values)

    def _mail_get_governing_alias(self):
        self.check_singleton()
        return self.project_id.alias_id

    def _mail_get_message_subtypes(self) -> Self:
        res = super()._mail_get_message_subtypes()
        if not self.step_id.rating_active:
            res -= self.env.ref("project.mt_task_rating")
        if len(self) == 1:
            waiting_subtype = self.env.ref("project.mt_task_waiting")
            if (
                (self.project_id and not self.project_id.allow_dependencies)
                or (
                    not self.project_id
                    and not self.env.user.has_group(
                        "project.group_project_task_dependencies"
                    )
                )
            ) and waiting_subtype in res:
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

        project_user_group_id = self.env.ref("project.group_project_user").id
        new_group = (
            "group_project_user",
            lambda pdata: (
                pdata["type"] == "user" and project_user_group_id in pdata["groups"]
            ),
            {},
        )
        groups = [new_group] + groups

        if self.project_privacy_visibility in ["invited_users", "portal"]:
            groups.insert(
                0,
                (
                    "allowed_portal_users",
                    lambda pdata: pdata["type"] in ["invited_users", "portal"],
                    {
                        "active": True,
                        "has_button_access": True,
                    },
                ),
            )
        portal_privacy = self.project_id.privacy_visibility in [
            "invited_users",
            "portal",
        ]
        for group_name, _group_method, group_data in groups:
            if group_name in ("customer", "user") or (
                group_name == "portal_customer" and not portal_privacy
            ):
                group_data["has_button_access"] = False
            elif group_name == "portal_customer" and portal_privacy:
                group_data["has_button_access"] = True

        return groups

    def _notify_get_reply_to_addresses(self) -> dict:
        addresses = self.sudo().mapped("project_id")._notify_get_reply_to_addresses()
        res = {
            task.id: addresses[task.project_id.id]
            for task in self
            if task.project_id and task.project_id.id in addresses
        }
        leftover = self.filtered(lambda rec: not rec.project_id)
        if leftover:
            res.update(super(ProjectTask, leftover)._notify_get_reply_to_addresses())
        return res

    def _get_internal_users_from_address_mail(
        self, emails: list[str], project_id: int | bool = False
    ) -> tuple[list[int], list[str], list[str]]:
        sanitized_email_dict = self._mail_cc_sanitized_raw_dict(emails)
        matched_partners = self.env["res.partner"]._get_or_create_from_emails(
            sanitized_email_dict.keys(), no_create=True
        )
        partners = self.env["res.partner"].concat(*matched_partners)
        unresolved_emails = set(sanitized_email_dict) - set(
            partners.mapped("email_normalized")
        )
        if project_id:
            alias = self.env["project.project"].browse(project_id).alias_id
            if alias.alias_full_name:
                unresolved_emails.discard(tools.email_normalize(alias.alias_full_name))
        unmatched_partner_emails = [
            sanitized_email_dict.get(email) for email in unresolved_emails
        ]

        users = partners.user_ids
        internal_user_ids = users.filtered(lambda u: not u.share).ids

        partner_emails_without_internal_users = (partners - users.partner_id).mapped(
            "email_formatted"
        )

        return (
            internal_user_ids,
            partner_emails_without_internal_users,
            unmatched_partner_emails,
        )

    @_debug.perf.timed
    @api.model
    def message_new(
        self,
        msg_dict: dict,
        custom_values: dict | None = None,
    ) -> Self:
        _debug.lifecycle(
            "message_new",
            email_from=msg_dict.get("email_from"),
            subject=msg_dict.get("subject"),
            custom=sorted(custom_values or {}),
        )
        create_context = dict(self.env.context or {})
        create_context["default_user_ids"] = False
        if custom_values is None:
            custom_values = {}
        if not msg_dict.get("author_id") and msg_dict.get("email_from"):
            author = self.env[
                "mixin.mail.thread"
            ]._partner_get_or_create_from_emails_single(
                [msg_dict["email_from"]], no_create=False
            )
            msg_dict["author_id"] = author.id

        defaults = {
            "name": msg_dict.get("subject") or self.env._("No Subject"),
            "partner_id": msg_dict.get("author_id"),
            "email_cc": (
                ", ".join(self._mail_cc_sanitized_raw_dict(msg_dict.get("cc")).values())
                if custom_values.get("project_id")
                else ""
            ),
        }
        defaults.update(custom_values)

        if msg_dict.get("to"):
            (
                internal_users,
                partner_emails_without_users,
                unmatched_partner_emails,
            ) = self._get_internal_users_from_address_mail(
                msg_dict.get("to"), defaults.get("project_id")
            )
            _debug.logic(
                "message_new_recipients",
                to=msg_dict.get("to"),
                internal_users=internal_users,
                no_user_emails=partner_emails_without_users,
                unmatched=unmatched_partner_emails,
            )
            defaults["user_ids"] = defaults.get("user_ids", []) + internal_users
            if custom_values.get("project_id") and (
                partner_emails_without_users or unmatched_partner_emails
            ):
                defaults["email_cc"] = ", ".join(
                    filter(
                        None,
                        [
                            defaults.get("email_cc"),
                            *partner_emails_without_users,
                            *unmatched_partner_emails,
                        ],
                    )
                )
        task = super(ProjectTask, self.with_context(create_context)).message_new(
            msg_dict, custom_values=defaults
        )
        partners = task._partner_get_or_create_from_emails_single(
            tools.email_split(
                (msg_dict.get("to") or "") + "," + (msg_dict.get("cc") or "")
            ),
            no_create=True,
        )
        _debug.pipeline(
            "message_new_task_created",
            task=task.id,
            project=task.project_id.id,
            subscribing=partners if task.project_id else "nobody_private",
        )
        if task.project_id:
            task.message_subscribe(partners.ids)
        return task

    def message_update(
        self,
        msg_dict: dict,
        update_vals: ValuesType | None = None,
    ) -> bool:
        shared = self.filtered("project_id")
        emails = tools.email_split(
            (msg_dict.get("to") or "") + "," + (msg_dict.get("cc") or "")
        )
        if shared and emails:
            partners_per_task = self._partner_get_or_create_from_emails(
                dict.fromkeys(shared, emails), no_create=True
            )
            for task in shared:
                task.message_subscribe(partners_per_task[task.id].ids)
        return super().message_update(msg_dict, update_vals=update_vals)

    def _notify_by_email_get_headers(self, headers=None) -> dict:
        headers = super()._notify_by_email_get_headers(headers=headers)
        if self.project_id:
            current_objects = [
                h for h in headers.get("X-Odoo-Objects", "").split(",") if h.strip()
            ]
            current_objects.insert(0, "project.project-%s" % self.project_id.id)
            headers["X-Odoo-Objects"] = ",".join(current_objects)
        if self.tag_ids:
            headers["X-Odoo-Tags"] = ",".join(self.tag_ids.mapped("name"))
        return headers

    def _message_post_after_hook(self, message: Any, msg_vals: dict[str, Any]) -> bool:
        if message.attachment_ids and not self.displayed_image_id:
            image_attachments = message.attachment_ids.filtered(
                lambda a: a.mimetype and a.mimetype.startswith("image/")
            )
            if image_attachments:
                _debug.logic(
                    "displayed_image_set",
                    tasks=self,
                    attachment=image_attachments[0].id,
                )
                self.displayed_image_id = image_attachments[0]

        if (
            not self.description
            and message.subtype_id == self._creation_subtype()
            and self.partner_id == message.author_id
            and msg_vals["message_type"] == "email"
            and msg_vals.get("body")
        ):
            source_html = msg_vals.get("body")
            doc = html.fromstring(source_html)

            signature_xpath = '//*[@id="Signature"] | //*[@data-smartmail="gmail_signature"] | //span[normalize-space(.) = "--"]'

            for element in doc.xpath(signature_xpath):
                element.getparent().remove(element)

            cleaned_html = html.tostring(doc, encoding="unicode").strip()
            _debug.logic("description_from_email", tasks=self, chars=len(cleaned_html))
            self.description = html_sanitize(cleaned_html)

        return super()._message_post_after_hook(message, msg_vals)

    def _get_domain_projects_to_make_billable(self, additional_domain=None) -> list:
        return Domain("partner_id", "!=", False) & Domain(
            additional_domain or Domain.TRUE
        )

    def _get_all_subtasks(self) -> Self:
        return self.browse(
            set.union(set(), *self._get_subtask_ids_per_task_id().values())
        )

    @_debug.perf.timed
    def _get_subtask_ids_per_task_id(self) -> dict:
        if not self:
            return {}

        res = {id_: [] for id_ in self._ids}
        if all(self._ids):
            self.env.cr.execute(
                """
         WITH RECURSIVE task_tree
                     AS (
                     SELECT id, id as supertask_id
                       FROM project_task
                      WHERE id = ANY(%(ancestor_ids)s)
                      UNION
                         SELECT t.id, tree.supertask_id
                           FROM project_task t
                           JOIN task_tree tree
                             ON tree.id = t.parent_id
                            AND t.active in (TRUE, %(active)s)
                          WHERE t.parent_id IS NOT NULL
               ) SELECT supertask_id, ARRAY_AGG(id)
                   FROM task_tree
                  WHERE id != supertask_id
               GROUP BY supertask_id
                """,
                {
                    "ancestor_ids": list(self.ids),
                    "active": self.env.context.get("active_test", True),
                },
            )
            res.update(dict(self.env.cr.fetchall()))
        else:
            _debug.logic(
                "subtask_ids_walked", mode="recursive_orm", reason="new_records"
            )
            res.update({task.id: task._get_subtasks_recursively().ids for task in self})
        return res

    def _get_subtasks_recursively(self) -> Self:
        children = self.child_ids
        if not children:
            return self.env["project.task"]
        return children + children._get_subtasks_recursively()

    def action_view_parent_task(self) -> dict:
        return {
            "name": self.env._("Parent Task"),
            "view_mode": "form",
            "res_model": "project.task",
            "res_id": self.parent_id.id,
            "type": "ir.actions.act_window",
            "context": self.env.context,
        }

    def action_project_sharing_view_parent_task(self) -> dict:
        if self.parent_id.project_id != self.project_id and self.env.user._is_portal():
            project = self.parent_id.project_id._filtered_access("read")
            if project:
                url = f"/my/projects/{self.parent_id.project_id.id}/task/{self.parent_id.id}"
                if project._is_project_sharing_accessible():
                    url = f"/my/projects/{self.parent_id.project_id.id}?task_id={self.parent_id.id}"
                return {
                    "name": "Portal Parent Task",
                    "type": "ir.actions.act_url",
                    "url": url,
                }
            elif self.display_parent_task_button:
                return {
                    "name": "Portal Parent Task",
                    "type": "ir.actions.act_url",
                    "url": self.parent_id.access_url,
                }
            return {}
        action = self.with_context(
            {
                "search_view_ref": "project.project_sharing_project_task_view_search",
            }
        ).action_view_parent_task()
        action["views"] = [
            (
                self.env.ref("project.project_sharing_project_task_view_form").id,
                "form",
            )
        ]
        action["search_view_id"] = self.env.ref(
            "project.project_sharing_project_task_view_search"
        ).id
        return action

    def action_view_task(self) -> dict:
        return {
            "view_mode": "form",
            "res_model": "project.task",
            "res_id": self.id,
            "type": "ir.actions.act_window",
            "context": self.env.context,
        }

    def action_project_sharing_open_task(self) -> dict:
        action = self.action_view_task()
        action["views"] = [
            [
                self.env.ref("project.project_sharing_project_task_view_form").id,
                "form",
            ]
        ]
        return action

    def action_project_sharing_open_subtasks(self) -> dict:
        self.check_singleton()
        subtasks = self.env["project.task"].search(
            [("id", "child_of", self.id), ("id", "!=", self.id)]
        )
        if subtasks.project_id == self.project_id:
            action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
                "project.project_sharing_project_task_action_sub_task"
            )
            if len(subtasks) == 1:
                action["view_mode"] = "form"
                action["views"] = [
                    (view_id, view_type)
                    for view_id, view_type in action["views"]
                    if view_type == "form"
                ]
                action["res_id"] = subtasks.id
            return action
        return {
            "name": "Portal Sub-tasks",
            "type": "ir.actions.act_url",
            "url": (
                f"/my/projects/{self.project_id.id}/task/{self.id}/subtasks"
                if len(subtasks) > 1
                else subtasks.get_portal_url(query_string="project_sharing=1")
            ),
        }

    def action_project_sharing_open_blocking(self) -> dict:
        self.check_singleton()
        blockings = self.successor_ids
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.project_sharing_project_task_action_blocking_tasks"
        )
        if len(blockings) == 1:
            action["view_mode"] = "form"
            action["views"] = [
                (view_id, view_type)
                for view_id, view_type in action["views"]
                if view_type == "form"
            ]
            action["res_id"] = blockings.id
        return action

    def action_dependent_tasks(self) -> dict:
        self.check_singleton()
        return {
            "res_model": "project.task",
            "type": "ir.actions.act_window",
            "context": {
                **self.env.context,
                "default_predecessor_ids": [Command.link(self.id)],
                "search_default_open_tasks": True,
            },
            "domain": [("predecessor_ids", "=", self.id)],
            "name": self.env._("Dependent Tasks"),
            "view_mode": "list,form,kanban,calendar,pivot,graph,activity",
        }

    def action_recurring_tasks(self) -> dict:
        return {
            "name": self.env._("Tasks in Recurrence"),
            "type": "ir.actions.act_window",
            "res_model": "project.task",
            "view_mode": "list,form,kanban,calendar,pivot,graph,activity",
            "context": {"create": False},
            "domain": [("recurrence_id", "in", self.recurrence_id.ids)],
        }

    def action_project_sharing_recurring_tasks(self) -> dict:
        self.check_singleton()
        recurrent_tasks = self.env["project.task"].search(
            [("recurrence_id", "in", self.recurrence_id.ids)]
        )
        if recurrent_tasks.project_id == self.project_id:
            action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
                "project.project_sharing_project_task_recurring_tasks_action"
            )
            action.update(
                {
                    "context": {"default_project_id": self.project_id.id},
                    "domain": [
                        ("project_id", "=", self.project_id.id),
                        ("recurrence_id", "in", self.recurrence_id.ids),
                    ],
                }
            )
            return action
        return {
            "name": "Portal Recurrent Tasks",
            "type": "ir.actions.act_url",
            "url": f"/my/projects/{self.project_id.id}/task/{self.id}/recurrent_tasks",
        }

    def action_view_ratings(self) -> dict:
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.rating_rating_action_task"
        )
        if self.rating_count == 1:
            action["view_mode"] = "form"
            action["res_id"] = self.rating_ids[0].id
            action["views"] = [
                [
                    self.env.ref("project.rating_rating_view_form_project").id,
                    "form",
                ]
            ]
            return action
        else:
            return action

    def action_unlink_recurrence(self) -> None:
        recurrences = self.recurrence_id
        recurrences._end()

    def action_convert_to_subtask(self) -> dict | None:
        self.check_singleton()
        if self.project_id:
            return {
                "name": self.env._("Convert to Task/Sub-Task"),
                "type": "ir.actions.act_window",
                "res_model": "project.task",
                "res_id": self.id,
                "views": [
                    (
                        self.env.ref(
                            "project.project_task_convert_to_subtask_view_form",
                            False,
                        ).id,
                        "form",
                    )
                ],
                "target": "new",
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "danger",
                "message": self.env._(
                    "Private tasks cannot be converted into sub-tasks. Please set a project on the task to gain access to this feature."
                ),
            },
        }

    def action_convert_to_template(self) -> dict:
        self.check_singleton()
        if not self.project_id:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "danger",
                    "message": self.env._(
                        "Private tasks cannot be converted into templates"
                    ),
                },
            }
        if self.is_template:
            return {
                "type": "ir.actions.client",
                "tag": "project_show_template_undo_confirmation_dialog",
                "params": {
                    "task_id": self.id,
                },
            }
        _debug.lifecycle("converted_to_template", tasks=self)
        self.is_template = True
        self.role_ids = False
        self.message_post(body=self.env._("Task converted to template"))
        return {
            "type": "ir.actions.client",
            "tag": "project_show_template_notification",
            "params": {
                "task_id": self.id,
                "next": {
                    "type": "ir.actions.client",
                    "tag": "soft_reload",
                },
            },
        }

    def action_undo_convert_to_template(self) -> dict:
        self.check_singleton()
        _debug.lifecycle("template_conversion_undone", tasks=self)
        self.is_template = False
        self.message_post(body=self.env._("Template converted back to regular task"))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Template converted back to regular task"),
                "next": {
                    "type": "ir.actions.client",
                    "tag": "soft_reload",
                },
            },
        }

    @_debug.perf.timed
    def plan_task_in_calendar(self, vals: dict[str, Any]) -> bool:
        self.check_singleton()
        _debug.logic(
            "calendar_plan_requested",
            tasks=self,
            vals=vals,
            planned_hours=self.planned_hours,
            full_day=self.env.context.get("task_calendar_plan_full_day"),
        )
        if date_start := vals.get("date_start"):
            tz_info = self.env.context.get("tz") or self.env.user.tz or "UTC"
            date_start = datetime.strptime(date_start, "%Y-%m-%d %H:%M:%S").astimezone(
                timezone(tz_info)
            )
            if self.planned_hours:
                max_date_end = date_start + relativedelta(
                    days=self.planned_hours / 8, months=1
                )
                available_work_intervals = self._get_users_available_work_intervals(
                    date_start, max_date_end
                )
                hours_to_plan = self.planned_hours
                compute_date_end = None
                for start_date, end_date, _dummy in available_work_intervals:
                    hours_to_plan -= (end_date - start_date).total_seconds() / 3600
                    if hours_to_plan <= 0:
                        compute_date_end = end_date + relativedelta(
                            seconds=hours_to_plan * 3600
                        )
                        break
                if available_work_intervals:
                    if not compute_date_end:
                        compute_date_end = available_work_intervals._items[-1][1]
                    if self.env.context.get("task_calendar_plan_full_day"):
                        vals["date_start"] = (
                            available_work_intervals._items[0][0]
                            .astimezone(UTC)
                            .replace(tzinfo=None)
                        )
                if compute_date_end:
                    vals["date_end"] = compute_date_end.astimezone(UTC).replace(
                        tzinfo=None
                    )
            elif self.env.context.get("task_calendar_plan_full_day"):
                date_start += relativedelta(hour=0, minute=0, second=0, microsecond=0)
                planned_date_end = datetime.strptime(
                    vals["date_end"], "%Y-%m-%d %H:%M:%S"
                ).astimezone(timezone(tz_info))
                planned_date_end += relativedelta(
                    days=1, hour=0, minute=0, second=0, microsecond=0
                )
                available_work_intervals = self._get_users_available_work_intervals(
                    date_start, planned_date_end
                )
                if available_work_intervals:
                    vals["date_start"] = (
                        available_work_intervals._items[0][0]
                        .astimezone(UTC)
                        .replace(tzinfo=None)
                    )
                    vals["date_end"] = (
                        available_work_intervals._items[-1][1]
                        .astimezone(UTC)
                        .replace(tzinfo=None)
                    )
        _debug.logic(
            "calendar_plan_written",
            tasks=self,
            date_start=vals.get("date_start"),
            date_end=vals.get("date_end"),
        )
        return self.write(vals)

    @api.model
    def _get_template_default_context_whitelist(self) -> list[str]:
        return [
            "parent_id",
            "date_start",
            "date_end",
        ]

    @api.model
    def _get_template_field_blacklist(self) -> list[str]:
        return [
            "partner_id",
        ]

    def action_create_from_template(self, values=None) -> int:
        self.check_singleton()
        values = values or {}
        default = (
            {
                key[8:]: value
                for key, value in self.env.context.items()
                if key.startswith("default_")
                and key[8:] in self._get_template_default_context_whitelist()
            }
            | dict.fromkeys(self._get_template_field_blacklist(), False)
            | values
        )
        _debug.lifecycle("created_from_template", tasks=self, default=sorted(default))
        return self.with_context(copy_from_template=True).copy(default=default).id

    def action_archive(self) -> dict | None:
        child_tasks = self.child_ids.filtered(
            lambda child_task: not child_task.display_in_project
        )
        _debug.lifecycle("archived", tasks=self, hidden_subtasks=child_tasks)
        if child_tasks:
            child_tasks.action_archive()
        return super().action_archive()

    def action_unarchive(self) -> dict | None:
        result = super().action_unarchive()
        child_tasks = self.with_context(active_test=False).child_ids.filtered(
            lambda child_task: (
                not child_task.active and not child_task.display_in_project
            )
        )
        _debug.lifecycle("unarchived", tasks=self, hidden_subtasks=child_tasks)
        if child_tasks:
            child_tasks.action_unarchive()
        return result

    def _get_access_action(self, access_uid=None, force_website=False):
        self.check_singleton()
        user = (
            self.env["res.users"].sudo().browse(access_uid)
            if access_uid
            else self.env.user
        )
        if (
            user
            and user._is_portal()
            and self.with_user(user).has_access("read")
            and self.project_id
            and self.project_id.with_user(user).has_access("read")
            and self.project_id._is_project_sharing_accessible()
        ):
            _debug.logic("access_action_project_sharing", tasks=self, user=user.id)
            return {
                "type": "ir.actions.act_url",
                "url": f"/my/projects/{self.project_id.id}/project_sharing/{self.id}",
                "target": "self",
            }
        if user and user.share and self.with_user(user).has_access("read"):
            # the session opens the task; a share URL would carry the customer's
            # token to whoever reads it
            _debug.logic("access_action_portal_session", tasks=self, user=user.id)
            return {
                "type": "ir.actions.act_url",
                "url": self.access_url,
                "target": "self",
                "res_id": self.id,
            }
        return super()._get_access_action(access_uid, force_website)

    def _send_task_rating_mail(self, force_send=False) -> None:
        for task in self:
            rating_template = task.step_id.rating_template_id
            partner = task.partner_id
            if (
                rating_template
                and partner
                and partner != self.env.user.partner_id
                and not task.is_template
            ):
                _debug.pipeline(
                    "rating_requested",
                    task=task.id,
                    partner=partner.id,
                    template=rating_template.id,
                    force_send=force_send,
                )
                task.rating_send_request(
                    rating_template,
                    lang=task.partner_id.lang,
                    force_send=force_send,
                )

    def _rating_get_partner(self) -> Self:
        res = super()._rating_get_partner()
        if not res and self.project_id.partner_id:
            return self.project_id.partner_id
        return res

    def rating_apply(
        self,
        rate,
        token=None,
        rating=None,
        feedback=None,
        subtype_xmlid=None,
        notify_delay_send=False,
    ) -> Self:
        rating = super().rating_apply(
            rate,
            token=token,
            rating=rating,
            feedback=feedback,
            subtype_xmlid=subtype_xmlid,
            notify_delay_send=notify_delay_send,
        )
        if self.step_id and self.step_id.auto_update_state:
            state = (
                "approved"
                if rating.rating >= rating_data.RATING_LIMIT_SATISFIED
                else "changes_requested"
            )
            _debug.logic(
                "rating_state_applied", tasks=self, rating=rating.rating, state=state
            )
            self.write({"state": state})
        return rating

    def _rating_apply_get_default_subtype_id(self) -> Self:
        return self.env["ir.model.data"]._xmlid_to_res_id("project.mt_task_rating")

    def _rating_get_parent_field_name(self) -> str:
        return "project_id"

    def _rating_get_operator(self) -> Self:
        tasks_with_one_user = self.filtered(
            lambda task: len(task.user_ids) == 1 and task.user_ids.partner_id
        )
        return tasks_with_one_user.user_ids.partner_id or self.env["res.partner"]

    def _unsubscribe_portal_users(self) -> None:
        self.message_unsubscribe(
            partner_ids=self.message_partner_ids.filtered("user_ids.share").ids
        )

    @api.model
    def get_unusual_days(self, date_from: str, date_to: str | None = None) -> dict:
        calendar = self.env.company.resource_calendar_id
        if not calendar:
            return {}
        return calendar._get_unusual_days(
            datetime.combine(fields.Date.from_string(date_from), time.min).replace(
                tzinfo=UTC
            ),
            datetime.combine(
                fields.Date.from_string(date_to or date_from), time.max
            ).replace(tzinfo=UTC),
        )

    def action_redirect_to_project_task_form(self) -> dict:
        menu_id = self.env.ref("project.menu_project_management_all_tasks").id
        return {
            "type": "ir.actions.act_url",
            "url": f"/odoo/{self.project_id.id}/action-project.act_project_project_2_project_task_all/{self.id}?menu_id={menu_id}",
            "target": "new",
        }

    def project_sharing_toggle_is_follower(self) -> bool:
        self.check_singleton()
        self.check_access("read")
        is_follower = self.message_is_follower
        _debug.lifecycle(
            "sharing_follower_toggled",
            tasks=self,
            user=self.env.uid,
            was_follower=is_follower,
            follower=not is_follower,
        )
        if is_follower:
            self.sudo().message_unsubscribe(self.env.user.partner_id.ids)
        else:
            self.sudo().message_subscribe(self.env.user.partner_id.ids)
        return not is_follower

    @api.depends("subtask_count", "closed_subtask_count")
    def _compute_subtask_completion_percentage(self) -> None:
        for task in self:
            task.subtask_completion_percentage = (
                task.subtask_count and task.closed_subtask_count / task.subtask_count
            )

    @api.model
    def _get_allowed_access_params(self) -> set[str]:
        return super()._get_allowed_access_params() | {"project_sharing_id"}

    @api.model
    def _get_thread_with_access(
        self, thread_id, *, project_sharing_id=None, **kwargs
    ) -> Self:
        thread = super()._get_thread_with_access(
            thread_id, project_sharing_id=project_sharing_id, **kwargs
        )
        if thread or not project_sharing_id:
            return thread
        project = self.env["project.project"].browse(project_sharing_id).exists()
        shared = bool(project) and project._is_project_sharing_accessible()
        _debug.logic(
            "sharing_thread_access",
            task=thread_id,
            project=project_sharing_id,
            shared=shared,
        )
        if not shared:
            return self.browse()
        return (
            self.sudo()
            .with_context(active_test=False)
            .search([("id", "=", thread_id), ("project_id", "=", project.id)])
        )

    @_debug.perf.timed
    def get_mention_suggestions(self, search: str, limit: int = 8) -> dict:
        self.check_singleton()
        project = self.project_id
        if not (
            project
            and project._is_project_sharing_accessible()
            and project._get_thread_with_access(project.id)
        ):
            _debug.logic(
                "mention_suggestions_refused",
                tasks=self,
                project=project.id,
                reason="not_sharing_accessible",
            )
            return {}
        participants = (
            project.sudo().message_follower_ids.partner_id
            | self.sudo().message_follower_ids.partner_id
            | project.sudo().collaborator_ids.partner_id
        )
        domain = Domain(
            self.env["res.partner"]._get_domain_mention_suggestions(search)
        ) & Domain("id", "in", participants.ids)
        partners = (
            self.env["res.partner"].sudo()._search_mention_suggestions(domain, limit)
        )
        return (
            Store()
            .add(
                partners,
                [
                    "email",
                    "im_status",
                    "name",
                    *partners._get_fields_store_mention(),
                ],
            )
            .get_result()
        )

    @api.model
    def get_import_templates(self) -> list[dict]:
        return [
            {
                "label": self.env._("Import Template for Tasks"),
                "template": "/project/static/xls/tasks_import_template.xlsx",
            }
        ]

    @_debug.perf.timed
    def _get_planning_overlap_rows(self, additional_domain=None):
        # each task is compared with its values in memory, so that a form shows
        # the overlap of the dates being edited; the tasks it overlaps are read
        # from the database
        domain = Domain(
            [
                ("active", "=", True),
                ("is_closed", "=", False),
                ("date_start", "!=", False),
                ("date_end", "!=", False),
                ("date_end", ">", fields.Datetime.now()),
                ("project_id", "!=", False),
            ]
        )
        if additional_domain:
            domain &= Domain(additional_domain)
        candidates = list(self.filtered_domain(domain))
        slots = [
            (index, task._origin.id or 0, task.date_start, task.date_end, user_id)
            for index, task in enumerate(candidates)
            for user_id in task.user_ids._origin.ids
        ]
        _debug.logic(
            "planning_overlap_slots",
            tasks=len(self),
            candidates=len(candidates),
            slots=len(slots),
        )
        if not slots:
            return []

        query = self._search(domain.optimize_full(self), bypass_access=True)
        other = self._table
        slot = "slot"
        query.add_join(
            "JOIN",
            slot,
            SQL(
                "(SELECT * FROM unnest(%s::int[], %s::int[], %s::timestamp[], "
                "%s::timestamp[], %s::int[]) AS u(idx, origin_id, date_start, "
                "date_end, user_id))",
                *(list(column) for column in zip(*slots, strict=True)),
            ),
            SQL(
                "%s != %s AND (%s, %s) OVERLAPS (%s::TIMESTAMP, %s::TIMESTAMP)",
                SQL.identifier(slot, "origin_id"),
                SQL.identifier(other, "id"),
                SQL.identifier(slot, "date_start"),
                SQL.identifier(slot, "date_end"),
                SQL.identifier(other, "date_start"),
                SQL.identifier(other, "date_end"),
            ),
        )
        other_user_rel = query.join(
            other, "id", "project_task_user_rel", "task_id", "TU2"
        )
        query.add_where(
            SQL(
                "%s = %s",
                SQL.identifier(other_user_rel, "user_id"),
                SQL.identifier(slot, "user_id"),
            )
        )
        slot_user = query.join(slot, "user_id", "res_users", "id", "U")
        slot_partner = query.join(slot_user, "partner_id", "res_partner", "id", "P")
        slot_partner_name = self.env["res.partner"]._field_to_sql(
            slot_partner, "name", query
        )
        query.groupby = SQL(", ").join(
            [
                SQL.identifier(slot, "idx"),
                SQL.identifier(slot, "user_id"),
                slot_partner_name,
            ]
        )
        query.order = slot_partner_name

        sql = query.select(
            SQL("%s AS idx", SQL.identifier(slot, "idx")),
            SQL("ARRAY_AGG(%s) AS task_ids", SQL.identifier(other, "id")),
            SQL("MIN(%s)", SQL.identifier(other, "date_start")),
            SQL("MAX(%s)", SQL.identifier(other, "date_end")),
            SQL("%s AS user_id", SQL.identifier(slot, "user_id")),
            SQL("%s AS partner_name", slot_partner_name),
            SQL("SUM(%s)", self._field_to_sql(other, "planned_hours", query)),
        )
        rows = self.env.execute_query_dict(sql)
        for row in rows:
            task = candidates[row.pop("idx")]
            row.update(
                id=task.id,
                date_start=task.date_start,
                date_end=task.date_end,
                planned_hours=task.planned_hours,
            )
        return rows

    def _get_planning_overlap_per_task(self):
        if not self:
            return {}
        self.flush_model(
            [
                "active",
                "date_start",
                "date_end",
                "user_ids",
                "project_id",
                "is_closed",
                "planned_hours",
            ]
        )

        res = defaultdict(dict)
        for row in self._get_planning_overlap_rows([("planned_hours", ">", 0)]):
            res[row["id"]][row["user_id"]] = {
                "partner_name": row["partner_name"],
                "overlapping_tasks_ids": row["task_ids"],
                "sum_planned_hours": row["sum"] + row["planned_hours"],
                "min_date_start": min(row["min"], row["date_start"]),
                "max_date_end": max(row["max"], row["date_end"]),
            }
        return res

    @_debug.perf.timed
    @api.depends("date_start", "date_end", "user_ids", "planned_hours")
    def _compute_planning_overlap(self):
        overlap_mapping = self._get_planning_overlap_per_task()
        _debug.logic(
            "planning_overlap_computed", tasks=self, overlapping=len(overlap_mapping)
        )
        if not overlap_mapping:
            self.planning_overlap = False
            return overlap_mapping
        user_ids = set()
        absolute_min_start = (
            self[0].date_start.replace(tzinfo=UTC)
            if self[0].date_start
            else datetime.now(UTC)
        )
        absolute_max_end = (
            self[0].date_end.replace(tzinfo=UTC)
            if self[0].date_end
            else datetime.now(UTC)
        )
        for task in self:
            for user_id, task_mapping in overlap_mapping.get(task.id, {}).items():
                absolute_min_start = min(
                    absolute_min_start,
                    task_mapping["min_date_start"].replace(tzinfo=UTC),
                )
                absolute_max_end = max(
                    absolute_max_end,
                    task_mapping["max_date_end"].replace(tzinfo=UTC),
                )
                user_ids.add(user_id)
        users = self.env["res.users"].browse(list(user_ids))

        regular_users_ids = []
        flexible_resources_ids = []
        flex_user_resource = {}
        flex_resource_user_id = {}
        for user in users:
            resource = user._get_project_task_resource()
            if resource and resource._is_flexible():
                flexible_resources_ids.append(resource.id)
                flex_user_resource[user.id] = resource
                flex_resource_user_id[resource.id] = user.id
            else:
                regular_users_ids.append(user.id)

        users_work_intervals, _dummy = (
            self.env["res.users"]
            .browse(regular_users_ids)
            .sudo()
            ._get_valid_work_intervals(absolute_min_start, absolute_max_end)
        )
        (
            flex_resources_work_intervals,
            flex_user_work_hours_per_day,
            flex_user_work_hours_per_week,
        ) = (
            self.env["resource.resource"]
            .browse(flexible_resources_ids)
            ._get_flexible_resource_valid_work_intervals(
                absolute_min_start, absolute_max_end
            )
        )

        for resource_id, intervals in flex_resources_work_intervals.items():
            users_work_intervals[flex_resource_user_id[resource_id]] = intervals

        res = {}
        for task in self:
            overlap_messages = []
            for user_id, task_mapping in overlap_mapping.get(task.id, {}).items():
                task_intervals_start = task_mapping["min_date_start"].replace(
                    tzinfo=UTC
                )
                task_intervals_end = task_mapping["max_date_end"].replace(tzinfo=UTC)
                task_intervals = Intervals(
                    [
                        (
                            task_intervals_start,
                            task_intervals_end,
                            self.env["resource.calendar.attendance"],
                        )
                    ]
                )
                work_intervals = users_work_intervals[user_id] & task_intervals
                if resource := flex_user_resource.get(user_id):
                    work_hours = resource._get_flexible_resource_work_hours(
                        work_intervals,
                        flex_user_work_hours_per_day[resource.id],
                        flex_user_work_hours_per_week[resource.id],
                    )
                else:
                    work_hours = get_intervals_hours(work_intervals)

                if task_mapping["sum_planned_hours"] > work_hours:
                    overlap_messages.append(
                        self.env._(
                            "%(partner)s has %(amount)s tasks at the same time.",
                            partner=task_mapping["partner_name"],
                            amount=len(task_mapping["overlapping_tasks_ids"]),
                        )
                    )
                    if task.id not in res:
                        res[task.id] = {}
                    res[task.id][user_id] = task_mapping
            task.planning_overlap = " ".join(overlap_messages) or False
        return res

    @api.model
    def _search_planning_overlap(self, operator, value):
        if operator != "in":
            return NotImplemented
        if not all(isinstance(v, bool) for v in value):
            return NotImplemented

        sql = SQL("""(
            SELECT T1.id
            FROM project_task T1
            INNER JOIN project_task T2 ON T1.id <> T2.id
            INNER JOIN project_task_user_rel U1 ON T1.id = U1.task_id
            INNER JOIN project_task_user_rel U2 ON T2.id = U2.task_id
                AND U1.user_id = U2.user_id
            WHERE
                T1.date_start < T2.date_end
                AND T1.date_end > T2.date_start
                AND T1.date_start IS NOT NULL
                AND T1.date_end IS NOT NULL
                AND T1.date_end > NOW() AT TIME ZONE 'UTC'
                AND T1.active = 't'
                AND T1.state NOT IN ('done', 'canceled')
                AND T1.project_id IS NOT NULL
                AND T2.date_start IS NOT NULL
                AND T2.date_end IS NOT NULL
                AND T2.date_end > NOW() AT TIME ZONE 'UTC'
                AND T2.project_id IS NOT NULL
                AND T2.active = 't'
                AND T2.state NOT IN ('done', 'canceled')
        )""")
        if True in value and False in value:
            return Domain.TRUE
        operator_new = "in" if any(value) else "not in"
        return [("id", operator_new, sql)]

    def _get_tasks_by_resource_calendar_dict(self):
        default_calendar = self.env.company.resource_calendar_id

        calendar_by_user_dict = {
            user.id: user.resource_calendar_id or default_calendar
            for user in self.mapped("user_ids")
        }

        tasks_by_resource_calendar_dict = defaultdict(lambda: self.env[self._name])
        for task in self:
            if len(task.user_ids) == 1:
                tasks_by_resource_calendar_dict[
                    calendar_by_user_dict[task.user_ids.id]
                ] |= task
            else:
                tasks_by_resource_calendar_dict[default_calendar] |= task

        return tasks_by_resource_calendar_dict

    @_debug.perf.timed
    @api.depends(
        "allow_dependencies",
        "date_start",
        "date_end",
        "predecessor_ids.date_start",
        "predecessor_ids.date_end",
        "dependency_ids.dependency_type",
        "dependency_ids.lag_hours",
    )
    def _compute_dependency_warning(self) -> None:
        for task in self:
            if not task.allow_dependencies:
                task.dependency_warning = False
                continue
            # the same predecessors the search counts, named only when readable
            late = task.browse().union(
                *(
                    dependency.depends_on_id
                    for dependency in task._get_predecessor_dependencies()
                    if task._is_dependency_date_violated(dependency)
                )
            )
            if not late:
                task.dependency_warning = False
                continue
            names = late.sudo(False)._filtered_access("read").mapped("name")
            hidden = len(late) - len(names)
            if hidden:
                names.append(self.env._("%(count)s other task(s)", count=hidden))
            task.dependency_warning = self.env._(
                "This task cannot be planned before the following tasks on which it depends: %(task_list)s",
                task_list=format_list(self.env, names),
            )

    def _is_dependency_date_violated(self, dependency) -> bool:
        self.check_singleton()
        planned = self[dependency._get_constrained_date_field()]
        bound = dependency._get_date_bound()
        return bool(planned and bound and planned < bound)

    def _search_dependency_warning(self, operator, value):
        if operator != "in":
            return NotImplemented
        if not all(isinstance(v, bool) for v in value):
            return NotImplemented

        self.flush_model(["active", "date_start", "date_end", "project_id"])
        self.env["project.project"].flush_model(["allow_dependencies"])
        self.env["project.task.dependency"].flush_model()
        sql = SQL("""
            SELECT t1.id
              FROM project_task t1
              JOIN project_project p
                ON p.id = t1.project_id
              JOIN project_task_dependency d
                ON d.task_id = t1.id
              JOIN project_task t2
                ON d.depends_on_id = t2.id
             WHERE p.allow_dependencies
               AND t2.active
               AND CASE WHEN d.dependency_type IN ('fs', 'ss')
                        THEN t1.date_start
                        ELSE t1.date_end
                   END
                   < CASE WHEN d.dependency_type IN ('fs', 'ff')
                          THEN t2.date_end
                          ELSE t2.date_start
                     END + make_interval(secs => d.lag_hours * 3600)
        """)
        if True in value and False in value:
            return Domain.TRUE
        operator_new = "in" if any(value) else "not in"
        return [("id", operator_new, sql)]

    @api.depends("date_start", "date_end")
    def _compute_date_start_effective(self) -> None:
        for task in self:
            task.date_start_effective = task.date_start or task.date_end

    def _inverse_date_start_effective(self) -> None:
        for task in self:
            if task.date_start:
                task.date_start = task.date_start_effective
            else:
                task.date_end = task.date_start_effective

    def _search_date_start_effective(self, operator, value) -> Domain:
        if operator not in ("in", "not in"):
            return self._get_date_start_effective_domain(operator, value)
        dates = [date for date in value if date is not False]
        domain = Domain.FALSE
        if len(dates) < len(value):
            domain |= Domain("date_start", "=", False) & Domain("date_end", "=", False)
        if dates:
            domain |= self._get_date_start_effective_domain("in", dates)
        return domain if operator == "in" else ~domain

    def _get_date_start_effective_domain(self, operator, value) -> Domain:
        return (
            Domain("date_start", "!=", False) & Domain("date_start", operator, value)
        ) | (
            Domain("date_start", "=", False)
            & Domain("date_end", "!=", False)
            & Domain("date_end", operator, value)
        )

    @_debug.perf.timed
    def _get_users_available_work_intervals(self, start_datetime, end_datetime):
        users_work_intervals, calendar_work_intervals = (
            self.user_ids._get_valid_work_intervals(start_datetime, end_datetime)
        )
        company = (
            self.user_ids.company_id
            if self.user_ids.company_id.id
            else self.env.company
        )
        company_work_intervals = calendar_work_intervals.get(
            company.resource_calendar_id.id,
            company.resource_calendar_id._work_intervals_batch(
                start_datetime, end_datetime
            )[False],
        )
        available_work_intervals = None
        for user in self.user_ids:
            work_intervals = users_work_intervals.get(user.id)
            if not work_intervals:
                continue
            if available_work_intervals is None:
                available_work_intervals = work_intervals
            else:
                available_work_intervals &= work_intervals

        if not available_work_intervals:
            _debug.logic(
                "company_calendar_fallback",
                tasks=self,
                calendar=company.resource_calendar_id.id,
                reason="no_user_intervals",
            )
            available_work_intervals = company_work_intervals
        return available_work_intervals

    def _get_dependencies_dict(self) -> dict:
        return {
            task: [t for t in task.predecessor_ids if t != task and t in self]
            if task.predecessor_ids
            else []
            for task in self
        }

    @_debug.perf.timed
    def _schedule_tasks(self, vals, max_date_start, first_possible_date_per_task=None):
        _debug.pipeline(
            "schedule_requested", tasks=self, vals=vals, max_date_start=max_date_start
        )
        if first_possible_date_per_task is None:
            first_possible_date_per_task = {}

        tasks_to_write = {}
        warnings = {}
        old_vals_per_task_id = {}

        company = self.company_id if len(self.company_id) == 1 else self.env.company
        tz_info = self.env.context.get("tz") or "UTC"

        user_to_assign = self.env["res.users"]

        users = self.user_ids
        if vals.get("user_ids") and len(vals["user_ids"]) == 1:
            user_to_assign = self.env["res.users"].browse(vals["user_ids"])
            if user_to_assign not in users:
                users |= user_to_assign
            tz_info = user_to_assign.tz or tz_info
        else:
            if self.env.context.get("default_project_id"):
                project = self.env["project.project"].browse(
                    self.env.context["default_project_id"]
                )
                company = project.company_id or company
                calendar = project.resource_calendar_id
            else:
                calendar = company.resource_calendar_id
            tz_info = calendar.tz or tz_info

        date_start = datetime.strptime(
            vals["date_start"], "%Y-%m-%d %H:%M:%S"
        ).astimezone(timezone(tz_info))
        fetch_date_end = max_date_start.astimezone(timezone(tz_info))
        end_loop = date_start + relativedelta(day=31, month=12, years=1)

        (
            valid_intervals_per_user,
            flex_user_work_hours_per_day,
            flex_user_work_hours_per_week,
        ) = self._scheduling_get_valid_intervals(
            date_start, fetch_date_end, users, [], True
        )
        dependency_rows = self._get_dependency_rows()
        dependency_bounds = self._get_dependency_bounds_per_task()
        start_bounds = {
            task_id: bounds["date_start"]
            for task_id, bounds in dependency_bounds.items()
            if "date_start" in bounds
        }
        end_bound_per_task = {
            task_id: bounds["date_end"].astimezone(timezone(tz_info))
            for task_id, bounds in dependency_bounds.items()
            if "date_end" in bounds
        }
        successor_rows_per_task = defaultdict(list)
        for row in dependency_rows:
            if row["depends_on_id"] in self._ids:
                successor_rows_per_task[row["depends_on_id"]].append(row)

        first_possible_date_per_task = {
            key: max(
                first_possible_date_per_task.get(key, datetime.min),  # noqa: DTZ901  sentinel, not an instant
                start_bounds.get(key, datetime.min),  # noqa: DTZ901  sentinel, not an instant
            ).astimezone(timezone(tz_info))
            for key in first_possible_date_per_task.keys() | start_bounds.keys()
        }

        scale = self.env.context.get("gantt_scale", "week")
        cell_part_from_context = self.env.context.get("cell_part")
        cell_part = (
            cell_part_from_context
            if scale in ["week", "month"] and cell_part_from_context in [1, 2, 4]
            else 2
        )
        delta_hours = 160 if scale == "year" else 24 / cell_part

        sorted_tasks = topological_sort(self._get_dependencies_dict())
        if _debug.logic.enabled:
            _debug.logic(
                "schedule_prepared",
                tz=tz_info,
                scale=scale,
                cell_part=cell_part,
                delta_hours=delta_hours,
                users=users.ids,
                assign=user_to_assign.ids,
                order=[t.id for t in sorted_tasks],
            )

        resource_of_user = {}

        def week_of_user(user_id, day):
            if user_id not in resource_of_user:
                resource_of_user[user_id] = (
                    self.env["res.users"].browse(user_id)._get_project_task_resource()
                )
            return resource_of_user[user_id]._get_week_of(day)

        def update_used_intervals(valid_intervals_per_user, intervals, user_ids):
            used_intervals = Intervals(intervals)
            if not user_ids:
                valid_intervals_per_user[False] -= used_intervals
            else:
                for user_id in valid_intervals_per_user:
                    if not user_id:
                        continue

                    if set(user_id) & set(user_ids):
                        valid_intervals_per_user[user_id] -= used_intervals

        for task in sorted_tasks:
            hours_to_plan = task._get_hours_to_plan()

            compute_date_start = compute_date_end = False
            first_possible_start_date = first_possible_date_per_task.get(task.id)

            user_ids = False
            if user_to_assign and user_to_assign not in task.user_ids:
                user_ids = tuple(user_to_assign.ids)
            elif task.user_ids:
                user_ids = tuple(task.user_ids.ids)

            if user_ids not in valid_intervals_per_user:
                _debug.logic(
                    "task_not_scheduled",
                    task=task,
                    users=user_ids,
                    reason="no_valid_intervals",
                )
                if "no_intervals" not in warnings:
                    warnings["no_intervals"] = self.env._(
                        "Some tasks weren't planned because the closest available starting date was too far ahead in the future"
                    )
                continue

            if hours_to_plan <= 0:
                hours_to_plan = delta_hours

            if user_ids:
                hours_to_plan /= len(user_ids)

            temp_valid_intervals_per_user = valid_intervals_per_user.copy()
            used_intervals = []
            while not compute_date_end or hours_to_plan > 0:
                for start_date, end_date, _dummy in split_at_midnight(
                    temp_valid_intervals_per_user[user_ids]
                ):
                    if first_possible_start_date:
                        if end_date <= first_possible_start_date:
                            continue

                        start_date = max(start_date, first_possible_start_date)

                    day = start_date.date()
                    real_interval_duration = (
                        end_date - start_date
                    ).total_seconds() / 3600
                    interval_duration = real_interval_duration
                    for user_id in user_ids or ():
                        if user_id in flex_user_work_hours_per_day:
                            interval_duration = min(
                                interval_duration,
                                flex_user_work_hours_per_day[user_id].get(day, 0.0),
                                flex_user_work_hours_per_week[user_id].get(
                                    week_of_user(user_id, day), 0.0
                                ),
                            )

                    if interval_duration <= 0.0:
                        continue

                    consumed_hours = min(interval_duration, hours_to_plan)
                    for user_id in user_ids or ():
                        if user_id in flex_user_work_hours_per_day:
                            flex_user_work_hours_per_day[user_id][day] -= consumed_hours
                            flex_user_work_hours_per_week[user_id][
                                week_of_user(user_id, day)
                            ] -= consumed_hours

                    hours_to_plan -= consumed_hours
                    if not compute_date_start:
                        compute_date_start = start_date

                    diff = real_interval_duration - consumed_hours
                    if diff > 0:
                        end_date -= relativedelta(hours=diff)

                    used_intervals.append((start_date, end_date, task))

                    if hours_to_plan == 0.0:  # noqa: RUF069  exact by construction
                        compute_date_end = end_date
                        break

                if compute_date_end and hours_to_plan <= 0:
                    break

                if fetch_date_end < end_loop:
                    new_fetch_date_end = min(
                        fetch_date_end + relativedelta(months=1), end_loop
                    )
                    _debug.logic(
                        "schedule_intervals_extended",
                        task=task,
                        hours_left=hours_to_plan,
                        fetch_until=new_fetch_date_end,
                    )
                    (
                        valid_intervals_per_user,
                        extra_hours_per_day,
                        extra_hours_per_week,
                    ) = self._scheduling_get_valid_intervals(
                        fetch_date_end,
                        new_fetch_date_end,
                        users,
                        [],
                        True,
                        valid_intervals_per_user,
                    )
                    # the budgets already consumed stay; the extension only adds
                    # the days and weeks the earlier window did not cover
                    for budget, extra in (
                        (flex_user_work_hours_per_day, extra_hours_per_day),
                        (flex_user_work_hours_per_week, extra_hours_per_week),
                    ):
                        for user_id, hours_per_period in extra.items():
                            user_budget = budget.setdefault(user_id, {})
                            for period, hours in hours_per_period.items():
                                user_budget.setdefault(period, hours)
                    temp_valid_intervals_per_user = valid_intervals_per_user.copy()
                    fetch_date_end = new_fetch_date_end
                    update_used_intervals(
                        temp_valid_intervals_per_user, used_intervals, user_ids
                    )
                else:
                    if "no_intervals" not in warnings:
                        warnings["no_intervals"] = self.env._(
                            "Some tasks weren't planned because the closest available starting date was too far ahead in the future"
                        )
                    break

            self -= task
            if not compute_date_end or hours_to_plan > 0:
                _debug.logic(
                    "task_not_scheduled",
                    task=task,
                    date_end=compute_date_end,
                    hours_unplanned=hours_to_plan,
                    reason="hours_left",
                )
                continue

            end_bound = end_bound_per_task.get(task.id)
            if end_bound and compute_date_end < end_bound:
                _debug.logic(
                    "task_end_held_by_dependency",
                    task=task,
                    date_end=compute_date_end,
                    held_until=end_bound,
                )
                compute_date_end = end_bound
            start_no_utc = compute_date_start.astimezone(UTC).replace(tzinfo=None)
            end_no_utc = compute_date_end.astimezone(UTC).replace(tzinfo=None)
            tasks_to_write[task] = {"start": start_no_utc, "end": end_no_utc}
            _debug.logic(
                "task_scheduled",
                task=task,
                start=start_no_utc,
                end=end_no_utc,
                users=user_ids,
            )

            for row in successor_rows_per_task[task.id]:
                anchor = (
                    compute_date_end
                    if row["dependency_type"] in FINISH_ANCHORED_TYPES
                    else compute_date_start
                )
                bound = anchor + timedelta(hours=row["lag_hours"])
                bounds = (
                    first_possible_date_per_task
                    if row["constrained_field"] == "date_start"
                    else end_bound_per_task
                )
                bounds[row["task_id"]] = max(bounds.get(row["task_id"], bound), bound)

            update_used_intervals(valid_intervals_per_user, used_intervals, user_ids)

        for task in tasks_to_write:
            old_vals_per_task_id[task.id] = {
                "date_start": task.date_start,
                "date_end": task.date_end,
            }
            task_vals = {
                "date_start": tasks_to_write[task]["start"],
                "date_end": tasks_to_write[task]["end"],
            }
            if user_to_assign:
                old_user_ids = task.user_ids.ids
                if user_to_assign.id not in old_user_ids:
                    task_vals["user_ids"] = user_to_assign.ids
                    old_vals_per_task_id[task.id]["user_ids"] = old_user_ids or False

            task.write(task_vals)

        _debug.pipeline(
            "schedule_done", planned=len(tasks_to_write), warnings=list(warnings)
        )
        return [warnings, old_vals_per_task_id]

    def _get_hours_to_plan(self):
        # What the task books, read through its assignees' own schedules; a
        # task not booked yet plans its estimate.
        return self.allocated_hours or self.planned_hours

    @_debug.perf.timed
    def _get_dependency_rows(self) -> list[dict]:
        # every dependency of these tasks on an active predecessor, with the
        # predecessor date it reads already shifted by the lag
        if not self.ids:
            return []
        self.flush_model(["active", "date_start", "date_end"])
        self.env["project.task.dependency"].flush_model()
        self.env.cr.execute(
            SQL(
                """
                SELECT d.task_id,
                       d.depends_on_id,
                       d.dependency_type,
                       CASE WHEN d.dependency_type IN ('fs', 'ss')
                            THEN 'date_start'
                            ELSE 'date_end'
                       END AS constrained_field,
                       CASE WHEN d.dependency_type IN ('fs', 'ff')
                            THEN p.date_end
                            ELSE p.date_start
                       END + make_interval(secs => d.lag_hours * 3600) AS bound,
                       d.lag_hours
                  FROM project_task_dependency d
                  JOIN project_task p
                    ON p.id = d.depends_on_id
                 WHERE d.task_id = ANY(%s)
                   AND p.active
                """,
                self.ids,
            )
        )
        return self.env.cr.dictfetchall()

    def _get_dependency_bounds_per_task(self) -> dict[int, dict[str, datetime]]:
        bounds = defaultdict(dict)
        for row in self._get_dependency_rows():
            if row["depends_on_id"] in self._ids or not row["bound"]:
                continue
            task_bounds = bounds[row["task_id"]]
            field = row["constrained_field"]
            task_bounds[field] = max(task_bounds.get(field, row["bound"]), row["bound"])
        return dict(bounds)

    @_debug.perf.timed
    def _scheduling_get_users_unavailable_intervals(
        self, user_ids, date_begin, date_end, tasks_to_exclude_ids
    ) -> dict:
        domain = [
            ("user_ids", "in", user_ids),
            ("date_end", ">=", date_begin.replace(tzinfo=None)),
            ("date_start", "<=", date_end.replace(tzinfo=None)),
        ]

        if tasks_to_exclude_ids:
            domain.append(("id", "not in", tasks_to_exclude_ids))

        already_planned_tasks = self.env["project.task"].search(
            domain, order="date_end"
        )
        _debug.logic(
            "unavailable_intervals_fetched",
            users=user_ids,
            date_begin=date_begin,
            date_end=date_end,
            planned_tasks=len(already_planned_tasks),
        )
        unavailable_intervals_per_user_id = defaultdict(list)
        for task in already_planned_tasks:
            interval_vals = (
                task.date_start.astimezone(UTC),
                task.date_end.astimezone(UTC),
                task,
            )
            for user_id in task.user_ids.ids:
                unavailable_intervals_per_user_id[user_id].append(interval_vals)

        return {
            user_id: Intervals(vals)
            for user_id, vals in unavailable_intervals_per_user_id.items()
        }

    @_debug.perf.timed
    def _scheduling_get_valid_intervals(
        self,
        start_date,
        end_date,
        users,
        candidates_ids=[],  # noqa: B006  read-only, passed straight through
        remove_intervals_with_planned_tasks=True,
        valid_intervals_per_user=None,
    ) -> tuple:
        if not self:
            return {}, {}, {}
        _debug.pipeline(
            "valid_intervals_fetched",
            tasks=self,
            start=start_date,
            end=end_date,
            users=users.ids,
            remove_planned=remove_intervals_with_planned_tasks,
            incremental=valid_intervals_per_user is not None,
        )

        flex_resource_user = {}
        flex_resources_ids = set()
        regular_resources_users_ids = set()
        for user in users:
            resource = user._get_project_task_resource()
            if resource and resource._is_flexible():
                flex_resource_user[resource.id] = user.id
                flex_resources_ids.add(resource.id)
            else:
                regular_resources_users_ids.add(user.id)

        regular_resources_users = self.env["res.users"].browse(
            regular_resources_users_ids
        )
        original_start_date, original_end_date = (
            start_date.astimezone(UTC),
            end_date.astimezone(UTC),
        )
        start_date, end_date = original_start_date, original_end_date

        flex_resources = self.env["resource.resource"].browse(flex_resources_ids)
        flex_resources_work_intervals, hours_per_day, hours_per_week = (
            flex_resources._get_flexible_resource_valid_work_intervals(
                start_date, end_date
            )
        )
        users_work_intervals, calendar_work_intervals = (
            regular_resources_users.sudo()._get_valid_work_intervals(
                start_date, end_date
            )
        )

        if flex_resources:
            start_date, end_date = flex_resources._get_flexible_week_bounds(
                start_date, end_date
            )

        unavailable_intervals = (
            self._scheduling_get_users_unavailable_intervals(
                users.ids, start_date, end_date, candidates_ids
            )
            if remove_intervals_with_planned_tasks
            else {}
        )

        flex_user_work_hours_per_day = {}
        flex_user_work_hours_per_week = {}
        for resource in flex_resources:
            user_id = flex_resource_user[resource.id]
            users_work_intervals[user_id] = flex_resources_work_intervals[resource.id]

            if resource._is_fully_flexible():
                continue
            flex_user_work_hours_per_day[user_id] = hours_per_day[resource.id]
            flex_user_work_hours_per_week[user_id] = hours_per_week[resource.id]

            if user_id not in unavailable_intervals:
                continue

            unavailable_intervals_day_formatted = (
                unavailable_intervals[user_id]
                & flex_resources_work_intervals[resource.id]
            )
            for interval in split_at_midnight(unavailable_intervals_day_formatted):
                tasks = interval[2]
                day = interval[0].date()

                interval_allocated_hours = 0.0
                for task in tasks:
                    interval_as_Interval = Intervals(
                        [
                            (
                                interval[0].astimezone(UTC).replace(tzinfo=None),
                                interval[1].astimezone(UTC).replace(tzinfo=None),
                                set(),
                            )
                        ]
                    )
                    interval_task_intersection = interval_as_Interval & Intervals(
                        [(task.date_start, task.date_end, set())]
                    )
                    interval_duration = get_intervals_hours(interval_task_intersection)
                    task_total_duration = (
                        task.date_end - task.date_start
                    ).total_seconds() / 3600
                    rate = interval_duration / task_total_duration
                    # the load a placed task spreads over its window is its
                    # effort: the estimate first, the booking only when there
                    # is none, since a flexible resource's booking is the
                    # capacity the window holds, not the work
                    effort_hours = task.planned_hours or task.allocated_hours
                    interval_allocated_hours = (
                        rate * effort_hours if effort_hours else interval_duration
                    )
                    interval_allocated_hours_per_user = interval_allocated_hours / len(
                        task.user_ids
                    )
                    if day in flex_user_work_hours_per_day[user_id]:
                        flex_user_work_hours_per_day[user_id][day] -= (
                            interval_allocated_hours_per_user
                        )

                    flex_user_work_hours_per_week[user_id][
                        resource._get_week_of(day)
                    ] -= interval_allocated_hours_per_user

        baseInterval = Intervals(
            [
                (
                    original_start_date,
                    original_end_date,
                    self.env["resource.calendar.attendance"],
                )
            ]
        )
        new_valid_intervals_per_user = {}
        invalid_intervals_per_user = {}
        for user_id, work_intervals in users_work_intervals.items():
            _id = (user_id,)
            new_valid_intervals_per_user[_id] = (
                work_intervals - unavailable_intervals.get(user_id, Intervals())
            )
            invalid_intervals_per_user[_id] = (
                baseInterval - new_valid_intervals_per_user[_id]
            )

        company_id = (
            users.company_id if len(users.company_id) == 1 else self.env.company
        )
        company_calendar_id = company_id.resource_calendar_id
        company_work_intervals = calendar_work_intervals.get(company_calendar_id.id)
        if not company_work_intervals:
            new_valid_intervals_per_user[False] = (
                company_calendar_id.sudo()._work_intervals_batch(
                    original_start_date, original_end_date
                )[False]
            )
        else:
            new_valid_intervals_per_user[False] = company_work_intervals

        for task in self:
            user_ids = tuple(task.user_ids.ids)
            if len(user_ids) < 2 or user_ids in new_valid_intervals_per_user:
                continue

            new_valid_intervals_per_user[user_ids] = new_valid_intervals_per_user[False]
            for user_id in user_ids:
                if (user_id,) not in invalid_intervals_per_user:
                    new_valid_intervals_per_user[user_ids] = Intervals()
                    break

                new_valid_intervals_per_user[user_ids] -= (
                    invalid_intervals_per_user.get((user_id,))
                )

        if not valid_intervals_per_user:
            valid_intervals_per_user = new_valid_intervals_per_user
        else:
            for user_ids, new_intervals in new_valid_intervals_per_user.items():
                if user_ids in valid_intervals_per_user:
                    valid_intervals_per_user[user_ids] |= new_intervals
                else:
                    valid_intervals_per_user[user_ids] = new_intervals

        return (
            valid_intervals_per_user,
            flex_user_work_hours_per_day,
            flex_user_work_hours_per_week,
        )

    def action_view_overlapping_tasks(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "project.action_view_all_task"
        )
        name = self.env._("Tasks in Conflict")
        action.update(
            {
                "display_name": name,
                "name": name,
                "domain": [
                    ("user_ids", "in", self.user_ids.ids),
                ],
                "context": {
                    "fsm_mode": False,
                    "initialDate": self.date_start,
                    "search_default_conflict_task": True,
                },
            }
        )
        return action
