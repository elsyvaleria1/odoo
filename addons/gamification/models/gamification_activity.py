from odoo import api, fields, models


class GamificationActivity(models.Model):
    _name = "gamification.activity"
    _description = "Gamification Activity Feed"
    _inherit = ["mixin.mail.thread"]
    _order = "activity_date desc, id desc"
    _rec_name = "summary"

    activity_type = fields.Selection(
        selection=[
            ("badge", "Badge Earned"),
            ("kudos", "Kudos Sent"),
            ("achievement", "Achievement Unlocked"),
            ("streak_milestone", "Streak Milestone"),
            ("level_up", "Level Up"),
            ("challenge_completed", "Challenge Completed"),
            ("quest_completed", "Quest Completed"),
            ("skill_unlocked", "Skill Unlocked"),
        ],
        string="Type",
        index=True,
        readonly=True,
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    target_user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        readonly=True,
        ondelete="set null",
        help="Secondary user (e.g. kudos recipient).",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="user_id.company_id",
        string="Company",
    )
    summary = fields.Char(
        readonly=True,
        required=True,
    )
    icon = fields.Char(
        string="Icon CSS",
        readonly=True,
    )
    activity_date = fields.Datetime(
        string="Date",
        default=fields.Datetime.now,
        index=True,
        readonly=True,
    )

    badge_id = fields.Many2one(
        comodel_name="gamification.badge",
        readonly=True,
        ondelete="set null",
    )
    achievement_id = fields.Many2one(
        comodel_name="gamification.achievement",
        readonly=True,
        ondelete="set null",
    )
    challenge_id = fields.Many2one(
        comodel_name="gamification.challenge",
        readonly=True,
        ondelete="set null",
    )
    karma_gained = fields.Integer(readonly=True)

    ACTIVITY_KINDS = {
        "badge": "fa fa-certificate",
        "kudos": "fa fa-heart",
        "achievement": "fa fa-trophy",
        "streak_milestone": "fa fa-fire",
        "level_up": "fa fa-arrow-up",
        "challenge_completed": "fa fa-flag-checkered",
        "quest_completed": "fa fa-flag-checkered",
        "skill_unlocked": "fa fa-puzzle-piece",
    }

    @api.model
    def _log_batch(self, entries: list[dict]) -> GamificationActivity:
        if not entries:
            return self.browse()

        Users = self.env["res.users"]
        Users.browse(
            {
                uid
                for entry in entries
                for uid in (entry.get("user_id"), entry.get("target_user_id"))
                if uid
            }
        ).mapped("name")
        for model, key in (
            ("gamification.badge", "badge_id"),
            ("gamification.achievement", "achievement_id"),
            ("gamification.challenge", "challenge_id"),
        ):
            if ids := {e[key] for e in entries if e.get(key)}:
                self.env[model].browse(ids).mapped("name")

        vals_list = []
        for entry in entries:
            entry = dict(entry)
            kind = entry["activity_type"]
            summary_args = entry.pop("summary_args", {})
            entry.setdefault("icon", self.ACTIVITY_KINDS.get(kind, "fa fa-star"))
            entry.setdefault("summary", self._render_summary(kind, entry, summary_args))
            vals_list.append(entry)
        return self.sudo().create(vals_list)

    @api.model
    def _log(self, activity_type: str, user, **kwargs) -> GamificationActivity:
        return self._log_batch(
            [{"activity_type": activity_type, "user_id": user.id, **kwargs}]
        )

    @api.model
    def _render_summary(self, kind: str, vals: dict, args: dict) -> str:
        Users = self.env["res.users"]
        user = Users.browse(vals["user_id"])
        target = Users.browse(vals.get("target_user_id") or ())
        if kind == "badge":
            badge = self.env["gamification.badge"].browse(vals["badge_id"])
            if target:
                return self.env._(
                    "%(sender)s awarded %(badge)s to %(user)s",
                    sender=target.name,
                    badge=badge.name,
                    user=user.name,
                )
            return self.env._(
                "%(user)s earned the %(badge)s badge", user=user.name, badge=badge.name
            )
        if kind == "kudos":
            return self.env._(
                "%(sender)s recognized %(recipient)s for %(category)s",
                sender=user.name,
                recipient=target.name,
                category=args["category"],
            )
        if kind == "achievement":
            ach = self.env["gamification.achievement"].browse(vals["achievement_id"])
            return self.env._(
                "%(user)s unlocked '%(achievement)s' (%(rarity)s)",
                user=user.name,
                achievement=ach.name,
                rarity=ach.rarity,
            )
        if kind == "streak_milestone":
            return self.env._(
                "%(user)s reached %(days)s days on %(streak)s!",
                user=user.name,
                days=args["days"],
                streak=args["streak"],
            )
        if kind == "level_up":
            return self.env._(
                "%(user)s reached %(rank)s!", user=user.name, rank=args["rank"]
            )
        if kind == "challenge_completed":
            challenge = self.env["gamification.challenge"].browse(vals["challenge_id"])
            return self.env._(
                "%(user)s completed the '%(challenge)s' challenge",
                user=user.name,
                challenge=challenge.name,
            )
        if kind == "quest_completed":
            return self.env._(
                "%(user)s completed the '%(quest)s' quest!",
                user=user.name,
                quest=args["quest"],
            )
        if kind == "skill_unlocked":
            return self.env._(
                "%(user)s unlocked skill '%(skill)s'",
                user=user.name,
                skill=args["skill"],
            )
        return self.env._("%(user)s earned an achievement", user=user.name)

    @api.model
    def _log_badge(self, user, badge, sender=None):
        return self._log(
            "badge",
            user,
            target_user_id=sender.id if sender else False,
            badge_id=badge.id,
        )

    @api.model
    def _log_kudos(self, sender, recipient, category, karma):
        return self._log(
            "kudos",
            sender,
            target_user_id=recipient.id,
            icon=category.icon or "fa fa-heart",
            karma_gained=karma,
            summary_args={"category": category.name},
        )

    @api.model
    def _log_achievement(self, user, achievement, karma):
        return self._log(
            "achievement",
            user,
            achievement_id=achievement.id,
            karma_gained=karma,
        )

    @api.model
    def _log_streak_milestone(self, user, streak_type, day_count, karma):
        return self._log(
            "streak_milestone",
            user,
            karma_gained=karma,
            summary_args={"days": day_count, "streak": streak_type.name},
        )

    @api.model
    def _log_level_up(self, user, rank):
        return self._log("level_up", user, summary_args={"rank": rank.name})

    @api.model
    def _log_challenge_completed(self, user, challenge):
        return self._log("challenge_completed", user, challenge_id=challenge.id)

    @api.model
    def _log_quest_completed(self, user, quest, karma):
        return self._log(
            "quest_completed",
            user,
            karma_gained=karma,
            summary_args={"quest": quest.name},
        )

    @api.model
    def _log_skill_unlocked(self, user, node, karma):
        return self._log(
            "skill_unlocked",
            user,
            karma_gained=karma,
            summary_args={"skill": node.name},
        )

    def _get_display_summary(self) -> str:
        self.check_singleton()
        args = {}
        if self.activity_type == "streak_milestone":
            return self.summary
        if self.activity_type == "kudos" or self.activity_type in (
            "quest_completed",
            "skill_unlocked",
        ):
            return self.summary
        if self.activity_type == "level_up":
            if not self.user_id.rank_id:
                return self.summary
            args = {"rank": self.user_id.rank_id.name}
        required = {
            "badge": self.badge_id,
            "achievement": self.achievement_id,
            "challenge_completed": self.challenge_id,
        }.get(self.activity_type)
        if required is not None and not required:
            return self.summary

        vals = {
            "user_id": self.user_id.id,
            "target_user_id": self.target_user_id.id,
            "badge_id": self.badge_id.id,
            "achievement_id": self.achievement_id.id,
            "challenge_id": self.challenge_id.id,
        }
        try:
            return self._render_summary(self.activity_type, vals, args)
        except KeyError, ValueError:
            return self.summary

    @api.model
    def get_activity_feed(self, limit=30) -> list:
        activities = self.search(
            [
                ("company_id", "=", self.env.company.id),
                ("user_id.gamification_visibility", "!=", "private"),
                "|",
                ("target_user_id", "=", False),
                ("target_user_id.gamification_visibility", "!=", "private"),
            ],
            limit=self.env["res.users"]._gamification_clamp_limit(limit, default=30),
        )
        return [
            {
                "id": a.id,
                "activity_type": a.activity_type,
                "user_name": a.user_id.name,
                "target_user_name": a.target_user_id.name
                if a.target_user_id
                else False,
                "summary": a._get_display_summary(),
                "icon": a.icon,
                "karma_gained": a.karma_gained,
                "date": a.activity_date.date().isoformat()
                if a.activity_date
                else False,
            }
            for a in activities
        ]
