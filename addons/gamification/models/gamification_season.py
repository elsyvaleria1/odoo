import logging
from typing import Any

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class GamificationSeason(models.Model):
    _name = "gamification.season"
    _description = "Gamification Season"
    _inherit = ["mixin.mail.thread"]
    _order = "start_date desc"

    name = fields.Char(
        string="Season Name",
        translate=True,
        required=True,
        tracking=True,
    )
    description = fields.Html(
        translate=True,
        sanitize_attributes=False,
    )
    theme = fields.Char(
        translate=True,
        help="Visual theme or motto (e.g., 'The Quality Quarter', 'Innovation Sprint').",
    )
    icon = fields.Image(
        max_width=128,
        max_height=128,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("active", "Active"),
            ("ended", "Ended"),
            ("archived", "Archived"),
        ],
        default="draft",
        index=True,
        required=True,
        tracking=True,
    )
    start_date = fields.Date(
        required=True,
        tracking=True,
    )
    end_date = fields.Date(
        required=True,
        tracking=True,
    )

    challenge_ids = fields.One2many(
        comodel_name="gamification.challenge",
        inverse_name="season_id",
        string="Season Challenges",
    )
    badge_ids = fields.Many2many(
        comodel_name="gamification.badge",
        relation="gamification_season_badge_rel",
        string="Exclusive Badges",
        help="Badges only available during this season.",
    )
    quest_ids = fields.Many2many(
        comodel_name="gamification.quest",
        relation="gamification_season_quest_rel",
        string="Season Quests",
    )

    challenge_count = fields.Count(
        count_of="challenge_ids",
        string="# Challenges",
    )
    participant_count = fields.Integer(
        string="# Participants",
        compute="_compute_participant_count",
    )

    @api.depends("challenge_ids", "challenge_ids.user_ids")
    def _compute_participant_count(self) -> None:
        for season in self:
            all_users = season.challenge_ids.mapped("user_ids")
            season.participant_count = len(all_users)

    def action_view_challenges(self) -> dict[str, Any]:
        self.check_singleton()
        return {
            "name": self.env._("Season Challenges"),
            "type": "ir.actions.act_window",
            "res_model": "gamification.challenge",
            "view_mode": "list,form",
            "domain": [("season_id", "=", self.id)],
            "context": {"default_season_id": self.id},
        }

    _dates_ordered = models.Constraint(
        "CHECK(end_date >= start_date)",
        "A season cannot end before it starts.",
    )

    def action_activate(self):
        self.filtered(lambda s: s.state == "draft").write({"state": "active"})

    def action_end(self) -> None:
        self.filtered(lambda s: s.state == "active").write({"state": "ended"})

    @api.model
    def _cron_update_seasons(self) -> None:
        today = fields.Date.today()
        starting = self.search([("state", "=", "draft"), ("start_date", "<=", today)])
        if starting:
            starting.action_activate()
            _logger.info("Season(s) started: %s", ", ".join(starting.mapped("name")))
        ending = self.search([("state", "=", "active"), ("end_date", "<", today)])
        if ending:
            ending.action_end()
            _logger.info("Season(s) ended: %s", ", ".join(ending.mapped("name")))

    def action_archive(self):
        self.filtered(lambda s: s.state == "ended").write({"state": "archived"})

    def get_season_leaderboard(self, limit=10) -> list:
        self.check_singleton()
        if not self.start_date or not self.end_date:
            return []

        cr = self.env.cr
        cr.execute(
            """
            SELECT
                u.id AS user_id,
                p.name AS user_name,
                COALESCE(SUM(GREATEST(t.new_value - t.old_value, 0)), 0) AS season_karma
            FROM res_users u
            JOIN res_partner p ON p.id = u.partner_id
            LEFT JOIN gamification_karma_tracking t
                ON t.user_id = u.id
                AND t.tracking_date::date >= %(start)s
                AND t.tracking_date::date <= %(end)s
            WHERE u.active IS TRUE
              AND u.share IS NOT TRUE
              AND u.company_id = %(company_id)s
              AND COALESCE(u.gamification_visibility, 'public') != 'private'
            GROUP BY u.id, p.name
            HAVING COALESCE(SUM(GREATEST(t.new_value - t.old_value, 0)), 0) > 0
            ORDER BY season_karma DESC
            LIMIT %(limit)s
        """,
            {
                "start": self.start_date,
                "end": self.end_date,
                "company_id": self.env.company.id,
                "limit": self.env["res.users"]._gamification_clamp_limit(limit),
            },
        )
        current_uid = self.env.uid
        return [
            {
                "user_id": row["user_id"],
                "user_name": row["user_name"],
                "season_karma": row["season_karma"],
                "is_current_user": row["user_id"] == current_uid,
            }
            for row in cr.dictfetchall()
        ]
