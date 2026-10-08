from datetime import timedelta

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, LazyTranslate, frozendict

from .mixin_project_column_container import ColumnDeleteTexts
from .project_task import CLOSED_STATES

_debug = DebugLog(__name__)
_lt = LazyTranslate(__name__)


class ProjectWorkflowStep(models.Model):
    _name = "project.workflow.step"
    _access_anchors = frozendict({"company": "project_ids.company_id"})
    _description = "Workflow Step"
    _inherit = ["mixin.project.column.container"]

    _member_model = "project.task"
    _member_field = "step_id"
    _column_action = "project.open_workflow_step_form"
    _delete_texts = ColumnDeleteTexts(
        title=_lt("Delete Workflow Step"),
        confirm=_lt("Are you sure you want to delete these workflow steps?"),
        archive=_lt(
            "You cannot delete workflow steps containing tasks. You can either "
            "archive them or first delete all of their tasks."
        ),
        blocked=_lt(
            "You cannot delete workflow steps containing tasks. You should first "
            "delete all of their tasks."
        ),
    )

    def _default_project_ids(self) -> list[int] | None:
        default_project_id = self.env.context.get("default_project_id")
        return [default_project_id] if default_project_id else None

    project_ids = fields.Many2many(
        comodel_name="project.project",
        relation="project_workflow_step_project_rel",
        column1="step_id",
        column2="project_id",
        string="Projects",
        default=lambda self: self._default_project_ids(),
        help="Projects that use this workflow step. Steps can be shared across "
        "projects with similar processes to consolidate reporting.",
    )
    mail_template_id = fields.Many2one(
        help="Email sent automatically when a task enters this step.",
    )
    archived_member_ids = fields.Many2many(
        comodel_name="project.task",
        relation="project_workflow_step_archived_task_rel",
        column1="step_id",
        column2="task_id",
        string="Tasks Archived With the Step",
        export_string_translation=False,
        copy=False,
        context={"active_test": False},
    )
    task_state = fields.Selection(
        selection="_selection_task_states",
        help="When a task is moved into this step, its state is set to this "
        "value. Leave empty to keep the task's state untouched.",
    )
    rating_template_id = fields.Many2one(
        comodel_name="mail.template",
        string="Rating Email Template",
        domain=[("model", "=", "project.task")],
        help="Rating request sent automatically when a task enters this step, "
        "or at a regular interval while the task remains here.",
    )
    auto_update_state = fields.Boolean(
        string="Auto-update State on Rating",
        default=False,
        help="Automatically update the task state based on customer rating replies:\n"
        " * Good feedback → Approved (green bullet).\n"
        " * Neutral or bad feedback → Changes Requested (orange bullet).",
    )
    wip_limit = fields.Integer(
        string="WIP Limit",
        default=0,
        help="Maximum number of tasks allowed in this step per project. "
        "0 = no limit. When exceeded, the step header shows a warning.",
    )
    rotting_threshold_days = fields.Integer(
        string="Days to Rot",
        default=0,
        help="Number of days of inactivity before tasks in this step are marked "
        "as stale. Set to 0 to disable.",
    )
    date_rating_request = fields.Datetime(
        export_string_translation=False,
        help="Next scheduled periodic rating request. Scheduled when periodic "
        "rating is enabled or its frequency changes, cleared when it is "
        "disabled, and advanced after each send — deliberately a "
        "plain field, not a now()-based compute that would reset on every "
        "module upgrade or unrelated recompute.",
    )
    rating_active = fields.Boolean(string="Send a Customer Rating Request")
    rating_status = fields.Selection(
        selection=[
            ("stage", "When reaching this step"),
            ("periodic", "On a periodic basis"),
        ],
        string="Customer Ratings Status",
        default="stage",
        required=True,
        help="When to send the rating request:\n"
        " * When reaching this step: sent once on step entry.\n"
        " * On a periodic basis: sent at the configured interval.",
    )
    rating_status_period = fields.Selection(
        selection=[
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("bimonthly", "Twice a Month"),
            ("monthly", "Once a Month"),
            ("quarterly", "Quarterly"),
            ("yearly", "Yearly"),
        ],
        string="Rating Frequency",
        default="monthly",
        required=True,
    )

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> ProjectWorkflowStep:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                count=len(vals_list),
                keys=sorted({k for vals in vals_list for k in vals}),
            )
        records = super().create(vals_list)
        _debug.lifecycle("created", steps=records)
        records._update_rating_deadlines(reschedule=False)
        return records

    @_debug.perf.timed
    def write(self, vals: dict) -> bool:
        _debug.lifecycle("write", steps=self, keys=sorted(vals))
        res = super().write(vals)
        if {"rating_active", "rating_status", "rating_status_period"} & vals.keys():
            _debug.pipeline("rating_deadlines_refresh_requested", steps=self)
            self._update_rating_deadlines(reschedule=True)
        return res

    def _count_hidden_projects(self) -> int:
        relation = self._fields["project_ids"]
        self.flush_recordset(["project_ids"])
        linked = self.env.execute_query(
            SQL(
                "SELECT count(DISTINCT %s) FROM %s WHERE %s = ANY(%s)",
                SQL.identifier(relation.column2),
                SQL.identifier(relation.relation),
                SQL.identifier(relation.column1),
                self.ids,
            )
        )[0][0]
        return linked - len(self.with_context(active_test=False).project_ids)

    def _get_projects_out_of_reach(self, members: models.BaseModel) -> models.BaseModel:
        projects = (self.project_ids | members.project_id).with_context(
            active_test=False
        )
        writable = projects.with_env(self.env(su=False))._filtered_access("write")
        accessible = projects.filtered_domain([("user_has_access", "=", True)])
        return projects - writable - accessible

    def _get_sharing_projects(self) -> models.BaseModel:
        return self.project_ids

    _RATING_PERIOD_DAYS = {
        "daily": 1,
        "weekly": 7,
        "bimonthly": 15,
        "monthly": 30,
        "quarterly": 90,
        "yearly": 365,
    }

    def _get_next_rating_deadline(self):
        self.check_singleton()
        return fields.Datetime.now() + timedelta(
            days=self._RATING_PERIOD_DAYS.get(self.rating_status_period, 0)
        )

    def _update_rating_deadlines(self, reschedule: bool) -> None:
        for step in self:
            if not (step.rating_active and step.rating_status == "periodic"):
                if step.date_rating_request:
                    _debug.logic("rating_deadline_cleared", step=step)
                    step.date_rating_request = False
                continue
            if step.date_rating_request and not reschedule:
                continue
            step.date_rating_request = step._get_next_rating_deadline()
            _debug.logic(
                "rating_deadline_scheduled",
                step=step,
                deadline=step.date_rating_request,
                period=step.rating_status_period,
                reschedule=reschedule,
            )

    @_debug.perf.timed
    @api.model
    def _send_rating_all(self) -> None:
        steps = self.search(
            [
                ("rating_active", "=", True),
                ("rating_status", "=", "periodic"),
                ("date_rating_request", "<=", fields.Datetime.now()),
            ]
        )
        _debug.lifecycle("rating_cron_started", due=len(steps))
        for step in steps:
            tasks = step._get_rating_tasks()
            _debug.pipeline("periodic_rating_sent", step=step.id, tasks=tasks)
            tasks._send_task_rating_mail()
            step.date_rating_request = step._get_next_rating_deadline()
            self.env["ir.cron"]._commit_progress(1)
        _debug.lifecycle("rating_cron_finished")

    def _get_rating_tasks(self):
        self.check_singleton()
        return self.env["project.task"].search(
            [
                ("step_id", "=", self.id),
                ("state", "not in", list(CLOSED_STATES)),
            ]
        )

    def _selection_task_states(self) -> list[tuple[str, str]]:
        return (
            self.env["project.task"]._fields["state"]._description_selection(self.env)
        )

    @api.constrains("task_state")
    def _check_task_state_in_selection(self) -> None:
        valid_keys = {key for key, _label in self._selection_task_states()}
        for step in self:
            if step.task_state and step.task_state not in valid_keys:
                raise ValidationError(
                    self.env._(
                        "Step %(step)s has task_state=%(value)s, which is not a "
                        "valid project.task.state value.",
                        step=step.display_name,
                        value=step.task_state,
                    )
                )
