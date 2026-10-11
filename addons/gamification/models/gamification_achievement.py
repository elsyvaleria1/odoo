import logging

from odoo import api, fields, models
from odoo.tools import frozendict
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class GamificationAchievement(models.Model):
    """Hidden/discovery achievement that users unlock through normal work."""

    _name = "gamification.achievement"
    _description = "Gamification Achievement"
    _order = "sequence, name"

    name = fields.Char(
        string="Achievement",
        translate=True,
        required=True,
    )
    description = fields.Text(
        translate=True,
        help="Shown after the achievement is unlocked.",
    )
    hint = fields.Text(
        translate=True,
        help="Optional hint shown before unlock. Leave empty for full mystery.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    icon = fields.Image(
        max_width=128,
        max_height=128,
    )

    model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Trigger Model",
        required=True,
        ondelete="cascade",
        help="The model to evaluate for this achievement.",
    )
    model_name = fields.Char(related="model_id.model")
    trigger_domain = fields.Char(
        default="[]",
        required=True,
        help="Domain evaluated per user. May reference 'user'. "
        "Achievement unlocks when at least one record matches.\n"
        "Every candidate user whose domain evaluates to the same text "
        "shares one query and its answer: if the domain does not reference "
        "'user' at all, that is every candidate, so one shared result "
        "unlocks (or fails to unlock) the achievement for the whole "
        "population at once, not per person. That is a deliberate, "
        "supported shape for a company-wide achievement (e.g. 'anyone "
        "closed a deal'); it is a misconfiguration if a per-user "
        "achievement was intended.",
    )
    trigger_count = fields.Integer(
        string="Required Count",
        default=1,
        help="Number of records that must match the domain to unlock. "
        "Use 1 for simple presence checks, higher for cumulative achievements.",
    )

    badge_id = fields.Many2one(
        comodel_name="gamification.badge",
        string="Reward Badge",
        help="Badge automatically granted when the achievement is unlocked.",
    )
    karma_reward = fields.Integer(
        default=0,
        help="Karma points granted on unlock.",
    )
    rarity = fields.Selection(
        selection=[
            ("common", "Common"),
            ("rare", "Rare"),
            ("epic", "Epic"),
            ("legendary", "Legendary"),
        ],
        default="common",
        required=True,
    )
    hidden = fields.Boolean(
        string="Mystery Achievement",
        default=True,
        help="If checked, the achievement name and description are hidden "
        "until unlocked. Only the hint (if any) is visible.",
    )

    unlock_ids = fields.One2many(
        comodel_name="gamification.achievement.unlock",
        inverse_name="achievement_id",
        string="Unlocks",
    )
    unlock_count = fields.Count(
        count_of="unlock_ids",
        string="# Unlocked",
    )

    def _check_achievement_for_users(
        self,
        users: models.Model | None = None,
    ) -> models.Model:
        self.check_singleton()
        if users is None:
            users = self.env["res.users"].search(
                [
                    ("active", "=", True),
                    ("share", "=", False),
                ]
            )

        Unlock = self.env["gamification.achievement.unlock"]
        already_unlocked = Unlock.search(
            [
                ("achievement_id", "=", self.id),
                ("user_id", "in", users.ids),
            ]
        ).mapped("user_id")
        candidates = users - already_unlocked
        if not candidates:
            return Unlock.browse()

        Obj = self.env[self.model_id.model].sudo()
        trigger_count = max(self.trigger_count, 1)
        by_domain: dict[str, tuple[list, list]] = {}
        for user in candidates:
            domain = safe_eval(self.trigger_domain, {"user": user})
            by_domain.setdefault(repr(domain), (domain, []))[1].append(user)

        unlock_vals = []
        for domain, domain_users in by_domain.values():
            if Obj.search_count(domain, limit=trigger_count) < trigger_count:
                continue
            for user in domain_users:
                unlock_vals.append(
                    {
                        "achievement_id": self.id,
                        "user_id": user.id,
                    }
                )
                _logger.info(
                    "Achievement unlocked: '%s' for user %s",
                    self.name,
                    user.login,
                )

        return Unlock.create(unlock_vals) if unlock_vals else Unlock.browse()

    @api.model
    def _cron_check_achievements(self) -> None:
        achievements = self.search([("active", "=", True)])
        users = self.env["res.users"].search(
            [("active", "=", True), ("share", "=", False)]
        )
        for achievement in achievements:
            try:
                with self.env.cr.savepoint():
                    new_unlocks = achievement._check_achievement_for_users(users)
                    for unlock in new_unlocks:
                        unlock._grant_rewards()
            except Exception:
                _logger.exception(
                    "Achievement %r (id %s) failed to evaluate; skipping it "
                    "and continuing the run.",
                    achievement.name,
                    achievement.id,
                )


class GamificationAchievementUnlock(models.Model):
    """Record of a user unlocking an achievement."""

    _name = "gamification.achievement.unlock"
    _description = "Achievement Unlock"
    _order = "unlock_date desc"
    _rec_name = "achievement_id"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    achievement_id = fields.Many2one(
        comodel_name="gamification.achievement",
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
        string="Unlocked On",
        default=fields.Datetime.now,
        readonly=True,
    )

    rarity = fields.Selection(
        related="achievement_id.rarity",
        readonly=True,
    )
    achievement_name = fields.Char(
        related="achievement_id.name",
        string="Achievement Name",
        readonly=True,
    )

    _user_achievement_uniq = models.UniqueIndex(
        "(user_id, achievement_id)",
        "A user can only unlock an achievement once.",
    )

    def _grant_rewards(self) -> None:
        Users = self.env["res.users"].sudo()
        BadgeUser = self.env["gamification.badge.user"].sudo()
        Activity = self.env["gamification.activity"]

        badge_vals = []
        for achievement, unlocks in self.grouped("achievement_id").items():
            if achievement.karma_reward:
                Users._add_karma_batch(
                    {
                        unlock.user_id: {
                            "gain": achievement.karma_reward,
                            "source": unlock,
                            "reason": self.env._("Achievement: %s", achievement.name),
                        }
                        for unlock in unlocks
                    }
                )
            if achievement.badge_id:
                badge_vals += [
                    {
                        "user_id": unlock.user_id.id,
                        "badge_id": achievement.badge_id.id,
                    }
                    for unlock in unlocks
                ]

            for unlock in unlocks:
                unlock.user_id._send_gamification_notification(
                    "achievement",
                    {
                        "title": self.env._("Achievement Unlocked!"),
                        "message": achievement.name,
                        "rarity": achievement.rarity,
                    },
                )
                Activity._log_achievement(
                    unlock.user_id,
                    achievement,
                    achievement.karma_reward,
                )

        if badge_vals:
            BadgeUser.create(badge_vals)._send_badge()
