from odoo import api, fields, models

from .gamification_utils import start_end_date_for_period


class GamificationTeam(models.Model):
    """Team for collaborative gamification challenges."""

    _name = "gamification.team"
    _description = "Gamification Team"
    _inherit = ["mixin.mail.thread"]
    _order = "name"

    name = fields.Char(
        string="Team Name",
        translate=True,
        required=True,
        tracking=True,
    )
    description = fields.Text(translate=True)
    active = fields.Boolean(default=True)
    image_128 = fields.Image(
        string="Avatar",
        max_width=128,
        max_height=128,
    )

    member_ids = fields.Many2many(
        comodel_name="res.users",
        relation="gamification_team_members_rel",
        string="Members",
    )
    captain_id = fields.Many2one(
        comodel_name="res.users",
        help="Team leader who receives challenge reports.",
    )
    member_count = fields.Count(
        count_of="member_ids",
        string="# Members",
    )

    team_karma = fields.Integer(
        compute="_compute_team_stats",
        help="Sum of all members' karma.",
    )
    team_badges = fields.Integer(
        compute="_compute_team_stats",
        help="Total badges earned by all team members.",
    )

    challenge_ids = fields.Many2many(
        comodel_name="gamification.challenge",
        relation="gamification_challenge_team_rel",
        string="Active Challenges",
    )

    @api.depends("member_ids.karma", "member_ids.badge_ids")
    def _compute_team_stats(self) -> None:
        for team in self:
            team.team_karma = 0
            team.team_badges = 0
        members = self.member_ids
        if not members:
            return

        karma_by_user = {user.id: user.karma for user in members}
        badges_by_user = {
            user.id: count
            for user, count in self.env["gamification.badge.user"]._read_group(
                [("user_id", "in", members.ids)],
                groupby=["user_id"],
                aggregates=["__count"],
            )
        }
        for team in self:
            member_ids = team.member_ids.ids
            team.team_karma = sum(karma_by_user.get(uid, 0) for uid in member_ids)
            team.team_badges = sum(badges_by_user.get(uid, 0) for uid in member_ids)

    def get_team_challenge_score(self, challenge) -> float:
        self.check_singleton()
        if not self.member_ids:
            return 0.0
        (start_date, end_date) = start_end_date_for_period(
            challenge.period,
            challenge.start_date,
            challenge.end_date,
        )
        domain = [
            ("challenge_id", "=", challenge.id),
            ("user_id", "in", self.member_ids.ids),
            ("state", "!=", "draft"),
        ]
        if start_date:
            domain.append(("start_date", "=", start_date))
        if end_date:
            domain.append(("end_date", "=", end_date))
        goals = self.env["gamification.goal"].search(domain)
        if not goals:
            return 0.0
        return sum(goals.mapped("completeness")) / len(goals)
