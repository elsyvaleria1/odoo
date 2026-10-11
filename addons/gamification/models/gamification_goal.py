import ast
import logging
from datetime import date, datetime, timedelta
from typing import Any, Literal, Self

from odoo import api, exceptions, fields, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.models import ValuesType
from odoo.tools import frozendict
from odoo.tools.safe_eval import safe_eval, time

_logger = logging.getLogger(__name__)


class GamificationGoal(models.Model):

    _name = "gamification.goal"
    _access_anchors = frozendict(
        {
            "company": "user_id.company_id",
            "owner": "challenge_id.user_ids",
            "user": models.Anchor("user_id", kind="owner"),
        }
    )
    _description = "Gamification Goal"
    _inherit = ["mixin.mail.thread"]
    _rec_name = "definition_id"
    _order = "start_date desc, end_date desc, definition_id, id"
    _mail_partner_fields = ("user_partner_id",)

    definition_id = fields.Many2one(
        comodel_name="gamification.goal.definition",
        string="Goal Definition",
        required=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        required=True,
        ondelete="cascade",
        bypass_search_access=True,
    )
    user_partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="user_id.partner_id",
    )
    line_id = fields.Many2one(
        comodel_name="gamification.challenge.line",
        string="Challenge Line",
        ondelete="cascade",
    )
    challenge_id = fields.Many2one(
        related="line_id.challenge_id",
        readonly=True,
        help="Challenge that generated the goal, assign challenge to users "
        "to generate goals with a value in this field.",
    )
    start_date = fields.Date(default=fields.Date.today)
    end_date = fields.Date()
    target_goal = fields.Float(
        string="To Reach",
        required=True,
    )
    current = fields.Float(
        string="Current Value",
        default=0,
        required=True,
    )
    completeness = fields.Float(compute="_compute_completeness")
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("inprogress", "In progress"),
            ("reached", "Reached"),
            ("failed", "Failed"),
            ("canceled", "Cancelled"),
        ],
        default="draft",
        index=True,
        required=True,
    )
    to_update = fields.Boolean(string="To update")
    closed = fields.Boolean(
        string="Closed goal",
        index=True,
    )

    computation_mode = fields.Selection(related="definition_id.computation_mode")
    color = fields.Integer(
        string="Color Index",
        compute="_compute_color",
    )
    remind_update_delay = fields.Integer(
        string="Remind delay",
        help="The number of days after which the user "
        "assigned to a manual goal will be reminded. "
        "Never reminded if no value is specified.",
    )
    last_update = fields.Date(
        help="In case of manual goal, reminders are sent if the goal as not "
        "been updated for a while (defined in challenge). Ignored in "
        "case of non-manual goal or goal not linked to a challenge."
    )

    definition_description = fields.Text(
        related="definition_id.description",
        string="Definition Description",
        readonly=True,
    )
    definition_condition = fields.Selection(
        related="definition_id.condition",
        string="Definition Condition",
        readonly=True,
    )
    definition_suffix = fields.Char(
        related="definition_id.full_suffix",
        string="Suffix",
        readonly=True,
    )
    definition_display = fields.Selection(
        related="definition_id.display_mode",
        string="Display Mode",
        readonly=True,
    )

    OUTCOME_FIELDS = frozenset(
        {"closed", "current", "end_date", "start_date", "state", "target_goal"}
    )

    @api.depends("end_date", "last_update", "state")
    def _compute_color(self) -> None:
        for goal in self:
            goal.color = 0
            if goal.end_date and goal.last_update:
                if (goal.end_date < goal.last_update) and (goal.state == "failed"):
                    goal.color = 2
                elif (goal.end_date < goal.last_update) and (goal.state == "reached"):
                    goal.color = 5

    @api.depends("current", "target_goal", "definition_id.condition")
    def _compute_completeness(self) -> None:
        for goal in self:
            if goal.definition_condition == "higher":
                if goal.current >= goal.target_goal:
                    goal.completeness = 100.0
                else:
                    goal.completeness = (
                        round(100.0 * goal.current / goal.target_goal, 2)
                        if goal.target_goal
                        else 0
                    )
            elif goal.current < goal.target_goal:
                goal.completeness = 100.0
            else:
                goal.completeness = 0.0

    def _check_remind_delay(self) -> dict[str, Any]:
        self.check_singleton()
        if not (self.remind_update_delay and self.last_update):
            return {}

        delta_max = timedelta(days=self.remind_update_delay)
        if date.today() - self.last_update < delta_max:
            return {}

        body_html = self.env.ref(
            "gamification.email_template_goal_reminder"
        )._render_field("body_html", self.ids, compute_lang=True)[self.id]
        self.message_notify(
            body=body_html,
            partner_ids=[self.user_id.partner_id.id],
            subtype_xmlid="mail.mt_comment",
            email_layout_xmlid="mail.mail_notification_light",
        )

        return {"to_update": True}

    def _prepare_write_vals_by_goal(self, new_value: float) -> dict[Any, ValuesType]:
        if self.state not in ("inprogress", "reached"):
            return {}

        result = {}
        if new_value != self.current:
            result["current"] = new_value

        condition = self.definition_id.condition
        reached = (condition == "higher" and new_value >= self.target_goal) or (
            condition == "lower" and new_value <= self.target_goal
        )

        if reached:
            if self.state != "reached":
                result["state"] = "reached"
        elif self.end_date and fields.Date.today() > self.end_date:
            result["state"] = "failed"
            result["closed"] = True
        elif self.state == "reached":
            result["state"] = "inprogress"

        return {self: result} if result else {}

    def update_goal(self) -> bool:
        goals_by_definition = {}
        for goal in self.with_context(prefetch_fields=False):
            goals_by_definition.setdefault(goal.definition_id, []).append(goal)

        measure = {
            "manually": self._measure_manual_goals,
            "python": self._measure_python_goals,
            "count": self._measure_aggregate_goals,
            "sum": self._measure_aggregate_goals,
        }
        in_cron = "commit_gamification" in self.env.context
        for definition, goals in goals_by_definition.items():
            handler = measure.get(definition.computation_mode)
            if handler is None:
                _logger.error(
                    "Invalid computation mode '%s' in definition %s",
                    definition.computation_mode,
                    definition.name,
                )
                continue
            if not in_cron:
                self._write_goal_values(handler(definition, goals))
                continue
            try:
                with self.env.cr.savepoint():
                    self._write_goal_values(handler(definition, goals))
            except PG_RETRY_EXCEPTIONS:
                raise
            except Exception:
                _logger.exception(
                    "Goal definition %r (id %s) failed to evaluate; skipping its "
                    "goals and continuing the run.",
                    definition.name,
                    definition.id,
                )
                continue
            if self.env.context.get("commit_gamification"):
                self.env["ir.cron"]._commit_progress()
        return True

    def _write_goal_values(self, goals_to_write: dict) -> None:
        by_values: dict[frozenset, list[int]] = {}
        for goal, values in goals_to_write.items():
            if not values:
                continue
            by_values.setdefault(frozenset(values.items()), []).append(goal.id)
        Goal = self.env["gamification.goal"].sudo()
        for vals_key, goal_ids in by_values.items():
            Goal.browse(goal_ids).write(dict(vals_key))

    def _measure_manual_goals(self, definition, goals) -> dict:
        return {goal: goal._check_remind_delay() for goal in goals}

    def _measure_python_goals(self, definition, goals) -> dict:
        goals_to_write = {}
        code = definition.compute_code.strip()
        for goal in goals:
            cxt = {
                "object": goal,
                "env": self.env,
                "date": date,
                "datetime": datetime,
                "timedelta": timedelta,
                "time": time,
            }
            safe_eval(code, cxt, mode="exec")
            result = cxt.get("result")
            if isinstance(result, (float, int)):
                goals_to_write.update(goal._prepare_write_vals_by_goal(result))
            else:
                _logger.error(
                    "Invalid return content '%r' from the evaluation "
                    "of code for definition %s, expected a number",
                    result,
                    definition.name,
                )
        return goals_to_write

    def _measure_aggregate_goals(self, definition, goals) -> dict:
        Obj = self.env[definition.model_id.model].sudo()
        if definition.batch_mode:
            return self._measure_batched_goals(definition, goals, Obj)
        return self._measure_per_goal(definition, goals, Obj)

    def _measure_batched_goals(self, definition, goals, Obj) -> dict:
        goals_to_write = {}
        field_date_name = definition.field_date_id.name
        general_domain = ast.literal_eval(definition.domain)
        field_name = definition.batch_distinctive_field.name

        subqueries = {}
        for goal in goals:
            start_date = (field_date_name and goal.start_date) or False
            end_date = (field_date_name and goal.end_date) or False
            subqueries.setdefault((start_date, end_date), {})[goal.id] = safe_eval(
                definition.batch_user_expression, {"user": goal.user_id}
            )

        for (start_date, end_date), query_goals in subqueries.items():
            subquery_domain = list(general_domain)
            subquery_domain.append((field_name, "in", list(set(query_goals.values()))))
            if start_date:
                subquery_domain.append((field_date_name, ">=", start_date))
            if end_date:
                subquery_domain.append((field_date_name, "<=", end_date))

            if definition.computation_mode == "count":
                aggregate = "__count"
            else:
                aggregate = f"{definition.field_id.name}:sum"
            user_values = Obj._read_group(  # noqa: E8507 -- one query per distinct period; goals sharing one were merged above
                subquery_domain, groupby=[field_name], aggregates=[aggregate]
            )

            value_by_key = {
                (
                    field_value.id
                    if isinstance(field_value, models.Model)
                    else field_value
                ): value
                for field_value, value in user_values
            }
            for goal in (g for g in goals if g.id in query_goals):
                new_value = value_by_key.get(query_goals[goal.id], 0)
                goals_to_write.update(goal._prepare_write_vals_by_goal(new_value))
        return goals_to_write

    def _measure_per_goal(self, definition, goals, Obj) -> dict:
        goals_to_write = {}
        field_date_name = definition.field_date_id.name
        field_name = definition.field_id.name
        field = Obj._fields.get(field_name)
        sum_supported = bool(field) and field.type in {"integer", "float", "monetary"}
        if definition.computation_mode == "sum" and not sum_supported:
            _logger.info(
                "Goal definition %s sums %r on %s, which is not numeric "
                "(type %r): counting rows instead.",
                definition.name,
                field_name,
                definition.model_id.model,
                field.type if field else None,
            )

        by_domain: dict[str, tuple[list, list]] = {}
        for goal in goals:
            domain = safe_eval(definition.domain, {"user": goal.user_id})
            if field_date_name:
                if goal.start_date:
                    domain.append((field_date_name, ">=", goal.start_date))
                if goal.end_date:
                    domain.append((field_date_name, "<=", goal.end_date))
            by_domain.setdefault(repr(domain), (domain, []))[1].append(goal)

        for domain, domain_goals in by_domain.values():
            if definition.computation_mode == "sum" and sum_supported:
                res = Obj._read_group(domain, [], [f"{field_name}:sum"])  # noqa: E8507 -- one query per distinct domain; goals sharing one were merged above
                new_value = res[0][0] or 0.0
            else:
                new_value = Obj.search_count(domain)  # noqa: E8507 -- one query per distinct domain; goals sharing one were merged above
            for goal in domain_goals:
                goals_to_write.update(goal._prepare_write_vals_by_goal(new_value))
        return goals_to_write

    def action_start(self) -> bool:
        self.write({"state": "inprogress"})
        return self.update_goal()

    def action_reach(self) -> None:
        self.write({"state": "reached"})

    def action_fail(self) -> None:
        self.write({"state": "failed"})

    def action_cancel(self) -> bool:
        return self.write({"state": "inprogress"})

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        return super(GamificationGoal, self.with_context(no_remind_goal=True)).create(
            vals_list
        )

    def write(self, vals: ValuesType) -> Literal[True]:
        if "definition_id" in vals or "user_id" in vals:
            if any(g.state != "draft" for g in self):
                raise exceptions.UserError(
                    self.env._("Can not modify the configuration of a started goal")
                )

        protected = self.OUTCOME_FIELDS.intersection(vals)
        if protected and not (
            self.env.su or self.env.user.has_group("base.group_erp_manager")
        ):
            if self.filtered(lambda g: g.definition_id.computation_mode != "manually"):
                raise exceptions.UserError(
                    self.env._(
                        "Automatic goals are computed by the system and can not be"
                        " updated manually."
                    )
                )
            if forbidden := protected - {"current"}:
                raise exceptions.UserError(
                    self.env._(
                        "On your own goal you may update the value, not %(fields)s.",
                        fields=", ".join(sorted(forbidden)),
                    )
                )
            if self.filtered(lambda g: g.user_id != self.env.user):
                raise exceptions.UserError(
                    self.env._("You can only update the value of your own goals.")
                )

        if "current" in vals:
            vals = {**vals, "last_update": fields.Date.context_today(self)}
        result = super().write(vals)

        if "current" in vals and "no_remind_goal" not in self.env.context:
            reports_to_send: dict = {}
            for goal in self:
                challenge = goal.challenge_id
                if challenge and challenge.report_message_frequency == "onchange":
                    reports_to_send.setdefault(challenge.id, (challenge, set()))
                    reports_to_send[challenge.id][1].add(goal.user_id.id)
            for challenge, user_ids in reports_to_send.values():
                users = self.env["res.users"].browse(user_ids)
                challenge.sudo().report_progress(users=users)

        return result

    def get_action(self) -> dict[str, Any] | Literal[False]:
        self.check_singleton()
        if self.definition_id.action_id:
            action = self.definition_id.action_id.read()[0]

            if self.definition_id.res_id_field:
                action["res_id"] = safe_eval(
                    self.definition_id.res_id_field, {"user": self.env.user}
                )

                action["views"] = [
                    (view_id, mode)
                    for (view_id, mode) in action["views"]
                    if mode == "form"
                ] or action["views"]
            return action

        if self.computation_mode == "manually":
            return {
                "name": self.env._("Update %s", self.definition_id.name),
                "id": self.id,
                "type": "ir.actions.act_window",
                "views": [[False, "form"]],
                "target": "new",
                "context": {
                    "default_goal_id": self.id,
                    "default_current": self.current,
                },
                "res_model": "wizard.gamification.goal.update.current",
            }

        return False
