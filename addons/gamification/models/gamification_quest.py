from odoo import api, exceptions, fields, models
from odoo.tools import frozendict


class GamificationQuest(models.Model):
    """Multi-step narrative journey wrapping goal definitions."""

    _name = "gamification.quest"
    _description = "Gamification Quest"
    _inherit = ["mixin.mail.thread"]
    _order = "sequence, name"

    name = fields.Char(
        string="Quest Name",
        translate=True,
        required=True,
        tracking=True,
    )
    description = fields.Html(
        string="Story",
        translate=True,
        sanitize_attributes=False,
        help="Narrative framing for the quest (e.g., 'The Data Quality Crusade').",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    icon = fields.Image(
        max_width=128,
        max_height=128,
    )

    step_ids = fields.One2many(
        comodel_name="gamification.quest.step",
        inverse_name="quest_id",
        string="Steps",
        copy=True,
    )
    step_count = fields.Count(
        count_of="step_ids",
        string="# Steps",
    )

    reward_badge_id = fields.Many2one(
        comodel_name="gamification.badge",
        string="Completion Badge",
        help="Badge granted when all steps are completed.",
    )
    reward_karma = fields.Integer(
        string="Completion Karma",
        default=0,
        help="Bonus karma granted on quest completion (on top of step rewards).",
    )

    quest_mode = fields.Selection(
        selection=[("solo", "Solo"), ("team", "Team")],
        string="Mode",
        default="solo",
        required=True,
    )
    difficulty = fields.Selection(
        selection=[
            ("beginner", "Beginner"),
            ("intermediate", "Intermediate"),
            ("advanced", "Advanced"),
            ("expert", "Expert"),
        ],
        default="intermediate",
        required=True,
    )

    enrollment_ids = fields.One2many(
        comodel_name="gamification.quest.enrollment",
        inverse_name="quest_id",
        string="Enrollments",
    )
    enrollment_count = fields.Count(
        count_of="enrollment_ids",
        string="# Enrolled",
    )
    completion_count = fields.Integer(
        string="# Completed",
        compute="_compute_completion_count",
    )

    @api.depends("enrollment_ids.state")
    def _compute_completion_count(self) -> None:
        counts = {}
        if self.ids:
            counts = {
                quest.id: count
                for quest, count in self.env[
                    "gamification.quest.enrollment"
                ]._read_group(
                    [("quest_id", "in", self.ids), ("state", "=", "completed")],
                    groupby=["quest_id"],
                    aggregates=["__count"],
                )
            }
        for quest in self:
            quest.completion_count = counts.get(quest.id, 0)


class GamificationQuestStep(models.Model):
    """Individual step within a quest."""

    _name = "gamification.quest.step"
    _description = "Quest Step"
    _order = "sequence, id"

    quest_id = fields.Many2one(
        comodel_name="gamification.quest",
        index=True,
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(
        string="Step Name",
        translate=True,
        required=True,
    )
    description = fields.Text(
        translate=True,
        help="What the user needs to do for this step.",
    )
    sequence = fields.Integer(default=10)

    definition_id = fields.Many2one(
        comodel_name="gamification.goal.definition",
        string="Goal Definition",
        help="The goal definition this step evaluates. "
        "Leave empty for manually-verified steps.",
    )
    target_goal = fields.Float(
        string="Target",
        default=1,
        help="Target value for the goal (e.g., 10 leads, 5 invoices).",
    )

    prerequisite_ids = fields.Many2many(
        comodel_name="gamification.quest.step",
        relation="gamification_quest_step_prereq_rel",
        column1="step_id",
        column2="prereq_id",
        string="Prerequisites",
        domain="[('quest_id', '=', quest_id), ('id', '!=', id)]",
        help="Steps that must be completed before this one unlocks.",
    )

    karma_reward = fields.Integer(
        string="Step Karma",
        default=0,
    )
    badge_id = fields.Many2one(
        comodel_name="gamification.badge",
        string="Step Badge",
        help="Optional badge for completing this step.",
    )

    skill_node_id = fields.Many2one(
        comodel_name="gamification.skill.node",
        ondelete="set null",
        help="Skill tree node this step contributes to.",
    )

    @api.constrains("prerequisite_ids")
    def _check_no_self_prerequisite(self) -> None:
        for step in self:
            if step in step.prerequisite_ids:
                raise exceptions.ValidationError(
                    self.env._("A step cannot be its own prerequisite.")
                )


class GamificationQuestEnrollment(models.Model):
    """Tracks a user's progress through a quest."""

    _name = "gamification.quest.enrollment"
    _description = "Quest Enrollment"
    _order = "create_date desc"
    _rec_name = "quest_id"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    quest_id = fields.Many2one(
        comodel_name="gamification.quest",
        index=True,
        required=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.uid,
        index=True,
        required=True,
        ondelete="cascade",
    )
    state = fields.Selection(
        selection=[
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("abandoned", "Abandoned"),
        ],
        default="in_progress",
        index=True,
        required=True,
    )
    progress_percent = fields.Float(
        string="Progress %",
        compute="_compute_progress_percent",
        store=True,
    )

    completion_ids = fields.One2many(
        comodel_name="gamification.quest.step.completion",
        inverse_name="enrollment_id",
        string="Step Completions",
    )

    _user_quest_uniq = models.UniqueIndex(
        "(user_id, quest_id)",
        "A user can only enroll in a quest once.",
    )

    def write(self, vals):
        if (
            "state" in vals
            and not self.env.su
            and any(enrollment.user_id == self.env.user for enrollment in self)
        ):
            raise exceptions.UserError(
                self.env._(
                    "Complete the quest's steps instead of changing the status directly."
                )
            )
        return super().write(vals)

    @api.depends("completion_ids", "quest_id.step_ids")
    def _compute_progress_percent(self) -> None:
        for enrollment in self:
            total = len(enrollment.quest_id.step_ids)
            done = len(enrollment.completion_ids)
            enrollment.progress_percent = round(100.0 * done / total, 1) if total else 0

    def complete_step(self, step):
        self.check_singleton()
        if self.state != "in_progress":
            return False

        if step.quest_id != self.quest_id:
            raise exceptions.UserError(
                self.env._(
                    "'%(step)s' belongs to quest '%(other_quest)s', not '%(quest)s'.",
                    step=step.name,
                    other_quest=step.quest_id.name,
                    quest=self.quest_id.name,
                )
            )

        if step.id in self.completion_ids.mapped("step_id").ids:
            return False

        completed_step_ids = set(self.completion_ids.mapped("step_id").ids)
        for prereq in step.prerequisite_ids:
            if prereq.id not in completed_step_ids:
                raise exceptions.UserError(
                    self.env._(
                        "Cannot complete '%(step)s': prerequisite '%(prereq)s' not yet done.",
                        step=step.name,
                        prereq=prereq.name,
                    )
                )

        completion = (
            self.env["gamification.quest.step.completion"]
            .sudo()
            .create(
                {
                    "enrollment_id": self.id,
                    "step_id": step.id,
                }
            )
        )

        user = self.user_id
        if step.karma_reward:
            user.sudo()._add_karma(
                step.karma_reward,
                source=self,
                reason=self.env._("Quest step: %s", step.name),
            )
        if step.badge_id:
            self.env["gamification.badge.user"].sudo().create(
                {
                    "user_id": user.id,
                    "badge_id": step.badge_id.id,
                }
            )._send_badge()

        total_steps = len(self.quest_id.step_ids)
        completed_steps = len(self.completion_ids)
        if completed_steps >= total_steps:
            self._complete_quest()

        return completion

    def _complete_quest(self) -> None:
        self.check_singleton()
        self.sudo().state = "completed"
        user = self.user_id
        quest = self.quest_id

        if quest.reward_karma:
            user.sudo()._add_karma(
                quest.reward_karma,
                source=self,
                reason=self.env._("Quest completed: %s", quest.name),
            )
        if quest.reward_badge_id:
            self.env["gamification.badge.user"].sudo().create(
                {
                    "user_id": user.id,
                    "badge_id": quest.reward_badge_id.id,
                }
            )._send_badge()

        self.env["gamification.activity"]._log_quest_completed(
            user, quest, quest.reward_karma
        )

        self.env["gamification.skill.node"].sudo()._unlock_nodes_for_quest(self)

    def action_abandon(self) -> None:
        self.filtered(lambda e: e.state == "in_progress").sudo().write(
            {
                "state": "abandoned",
            }
        )


class GamificationQuestStepCompletion(models.Model):
    """Record of completing a single quest step."""

    _name = "gamification.quest.step.completion"
    _description = "Quest Step Completion"
    _order = "completion_date desc"
    _access_anchors = frozendict(
        {
            "owner": "enrollment_id.user_id",
        }
    )

    enrollment_id = fields.Many2one(
        comodel_name="gamification.quest.enrollment",
        index=True,
        required=True,
        ondelete="cascade",
    )
    step_id = fields.Many2one(
        comodel_name="gamification.quest.step",
        required=True,
        ondelete="cascade",
    )
    completion_date = fields.Datetime(
        default=fields.Datetime.now,
        readonly=True,
    )

    _enrollment_step_uniq = models.UniqueIndex(
        "(enrollment_id, step_id)",
        "A step can only be completed once per enrollment.",
    )
