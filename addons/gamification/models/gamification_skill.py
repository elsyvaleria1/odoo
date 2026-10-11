from psycopg.errors import UniqueViolation

from odoo import api, exceptions, fields, models


class GamificationSkillTree(models.Model):

    _name = "gamification.skill.tree"
    _description = "Gamification Skill Tree"
    _order = "sequence, name"

    name = fields.Char(
        string="Tree Name",
        translate=True,
        required=True,
    )
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    icon = fields.Image(
        max_width=128,
        max_height=128,
    )
    color = fields.Integer(
        string="Color Index",
        default=0,
    )

    node_ids = fields.One2many(
        comodel_name="gamification.skill.node",
        inverse_name="tree_id",
        string="Nodes",
    )
    node_count = fields.Count(
        count_of="node_ids",
        string="# Nodes",
    )


class GamificationSkillNode(models.Model):

    _name = "gamification.skill.node"
    _description = "Skill Tree Node"
    _order = "tree_id, level, sequence"

    name = fields.Char(
        string="Skill Name",
        translate=True,
        required=True,
    )
    description = fields.Text(translate=True)
    tree_id = fields.Many2one(
        comodel_name="gamification.skill.tree",
        string="Skill Tree",
        index=True,
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    level = fields.Integer(
        string="Tree Level",
        default=1,
        help="Vertical position in the tree (1 = root, higher = deeper).",
    )

    prerequisite_ids = fields.Many2many(
        comodel_name="gamification.skill.node",
        relation="gamification_skill_node_prereq_rel",
        column1="node_id",
        column2="prereq_id",
        string="Prerequisites",
        domain="[('tree_id', '=', tree_id), ('id', '!=', id)]",
    )
    dependent_ids = fields.Many2many(
        comodel_name="gamification.skill.node",
        relation="gamification_skill_node_prereq_rel",
        column1="prereq_id",
        column2="node_id",
        string="Unlocked By This",
        readonly=True,
    )

    karma_threshold = fields.Integer(
        default=0,
        help="Minimum karma required to unlock (0 = no karma requirement).",
    )
    quest_id = fields.Many2one(
        comodel_name="gamification.quest",
        string="Required Quest",
        ondelete="set null",
        help="Quest that must be completed to unlock this node.",
    )

    karma_reward = fields.Integer(
        string="Unlock Karma",
        default=0,
    )
    badge_id = fields.Many2one(
        comodel_name="gamification.badge",
        string="Unlock Badge",
        ondelete="set null",
    )

    unlock_ids = fields.One2many(
        comodel_name="gamification.skill.node.unlock",
        inverse_name="node_id",
        string="Unlocks",
    )
    unlock_count = fields.Count(
        count_of="unlock_ids",
        string="# Unlocked",
    )

    def check_unlock_for_user(self, user) -> bool:
        self.check_singleton()
        Unlock = self.env["gamification.skill.node.unlock"]

        if Unlock.search_count(
            [
                ("node_id", "=", self.id),
                ("user_id", "=", user.id),
            ],
            limit=1,
        ):
            return False

        if self.prerequisite_ids:
            unlocked_prereqs = Unlock.search(
                [
                    ("node_id", "in", self.prerequisite_ids.ids),
                    ("user_id", "=", user.id),
                ]
            ).mapped("node_id")
            if self.prerequisite_ids - unlocked_prereqs:
                return False

        if self.karma_threshold and user.karma < self.karma_threshold:
            return False

        if self.quest_id:
            completed = self.env["gamification.quest.enrollment"].search_count(
                [
                    ("quest_id", "=", self.quest_id.id),
                    ("user_id", "=", user.id),
                    ("state", "=", "completed"),
                ]
            )
            if not completed:
                return False

        return True

    def unlock_for_user(self, user):
        self.check_singleton()
        if not self.check_unlock_for_user(user):
            return False

        Unlock = self.env["gamification.skill.node.unlock"].sudo()
        try:
            with self.env.cr.savepoint():
                unlock = Unlock.create(
                    {
                        "node_id": self.id,
                        "user_id": user.id,
                    }
                )
        except UniqueViolation:
            return False

        if self.karma_reward:
            user.sudo()._add_karma(
                self.karma_reward,
                source=unlock,
                reason=self.env._("Skill unlocked: %s", self.name),
            )
        if self.badge_id:
            self.env["gamification.badge.user"].sudo().create(
                {
                    "user_id": user.id,
                    "badge_id": self.badge_id.id,
                }
            )._send_badge()

        self.env["gamification.activity"]._log_skill_unlocked(
            user, self, self.karma_reward
        )

        return unlock

    @api.model
    def _unlock_nodes_for_quest(self, enrollment) -> None:
        user = enrollment.user_id
        frontier = self.search([("quest_id", "=", enrollment.quest_id.id)])
        while frontier:
            next_frontier = self.browse()
            for node in frontier:
                if node.unlock_for_user(user):
                    next_frontier |= node.dependent_ids
            frontier = next_frontier

    @api.model
    def _cron_check_skill_unlocks(self) -> None:
        candidates = self.search([("karma_threshold", ">", 0)])
        if not candidates:
            return
        users = self.env["res.users"].search(
            [
                ("active", "=", True),
                ("share", "=", False),
                ("karma", ">=", min(candidates.mapped("karma_threshold"))),
            ]
        )
        for node in candidates:
            for user in users.filtered_domain([("karma", ">=", node.karma_threshold)]):
                frontier = node
                while frontier:
                    opened = frontier.browse()
                    for candidate in frontier:
                        if candidate.unlock_for_user(user):
                            opened |= candidate.dependent_ids
                    frontier = opened

    @api.constrains("prerequisite_ids")
    def _check_no_prerequisite_cycle(self) -> None:
        for node in self:
            seen = set()
            frontier = node.prerequisite_ids
            while frontier:
                if node in frontier:
                    raise exceptions.ValidationError(
                        self.env._(
                            "Skill node %s cannot be a prerequisite of itself "
                            "(directly or transitively).",
                            node.name,
                        )
                    )
                seen |= set(frontier.ids)
                frontier = frontier.prerequisite_ids.filtered_domain(
                    [("id", "not in", list(seen))]
                )


class GamificationSkillNodeUnlock(models.Model):

    _name = "gamification.skill.node.unlock"
    _description = "Skill Node Unlock"
    _order = "unlock_date desc"

    node_id = fields.Many2one(
        comodel_name="gamification.skill.node",
        index=True,
        required=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        required=True,
        ondelete="cascade",
    )
    unlock_date = fields.Datetime(
        default=fields.Datetime.now,
        readonly=True,
    )

    _user_node_uniq = models.UniqueIndex(
        "(user_id, node_id)",
        "A user can only unlock a skill node once.",
    )
