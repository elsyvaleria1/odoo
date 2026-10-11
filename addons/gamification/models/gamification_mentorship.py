from typing import Any

from odoo import api, exceptions, fields, models
from odoo.tools import frozendict


class GamificationMentorship(models.Model):
    """Mentor-mentee pairing for guided gamification progression."""

    _name = "gamification.mentorship"
    _description = "Gamification Mentorship"
    _inherit = ["mixin.mail.thread"]
    _order = "create_date desc"
    _rec_name = "display_name"
    _access_anchors = frozendict(
        {
            "mentor": models.Anchor("mentor_id", kind="owner"),
            "owner": "mentee_id",
        }
    )

    mentor_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    mentee_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("pending", "Awaiting Confirmation"),
            ("active", "Active"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
        index=True,
        required=True,
        tracking=True,
    )
    start_date = fields.Date(
        default=fields.Date.today,
        readonly=True,
    )
    end_date = fields.Date(tracking=True)
    description = fields.Text(
        string="Goals",
        help="What the mentor and mentee aim to achieve together.",
    )

    mentor_karma_per_milestone = fields.Integer(
        string="Mentor Karma per Milestone",
        default=25,
        groups="base.group_erp_manager",
        help="Karma granted to the mentor when the mentee reaches a new rank.",
    )
    mentor_karma_on_completion = fields.Integer(
        string="Mentor Karma on Completion",
        default=100,
        groups="base.group_erp_manager",
        help="Karma bonus for the mentor when the mentorship is completed.",
    )
    mentee_milestones_reached = fields.Integer(
        string="Milestones Reached",
        default=0,
        readonly=True,
        help="Number of rank-ups the mentee achieved during this mentorship.",
    )
    total_mentor_karma = fields.Integer(
        string="Total Mentor Karma Earned",
        default=0,
        readonly=True,
    )

    completion_badge_id = fields.Many2one(
        comodel_name="gamification.badge",
        groups="base.group_erp_manager",
        help="Badge granted to both mentor and mentee on completion.",
    )

    _mentor_mentee_uniq = models.UniqueIndex(
        "(mentor_id, mentee_id) WHERE state != 'cancelled'",
        "A user can only have one mentorship with the same partner.",
    )

    @api.depends("mentor_id", "mentee_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = self.env._(
                "%(mentor)s mentoring %(mentee)s",
                mentor=rec.mentor_id.name or "",
                mentee=rec.mentee_id.name or "",
            )

    @api.constrains("mentor_id", "mentee_id", "state")
    def _check_not_self_mentoring(self) -> None:
        for rec in self:
            if rec.mentor_id == rec.mentee_id:
                raise exceptions.ValidationError(
                    self.env._("A user cannot mentor themselves.")
                )

        live = self.filtered(lambda r: r.state in ("pending", "active"))
        if not live:
            return
        reciprocals = {
            (other.mentor_id.id, other.mentee_id.id)
            for other in self.sudo().search(
                [
                    ("mentor_id", "in", live.mentee_id.ids),
                    ("mentee_id", "in", live.mentor_id.ids),
                    ("state", "in", ("pending", "active")),
                    ("id", "not in", live.ids),
                ]
            )
        }
        for rec in live:
            if (rec.mentee_id.id, rec.mentor_id.id) in reciprocals:
                raise exceptions.ValidationError(
                    self.env._(
                        "%(a)s and %(b)s cannot mentor each other: a reciprocal "
                        "pairing pays both sides for the same progression.",
                        a=rec.mentor_id.name,
                        b=rec.mentee_id.name,
                    )
                )

    @api.constrains("mentor_karma_per_milestone", "mentor_karma_on_completion")
    def _check_karma_rewards_positive(self) -> None:
        for rec in self.sudo():
            if rec.mentor_karma_per_milestone < 0 or rec.mentor_karma_on_completion < 0:
                raise exceptions.ValidationError(
                    self.env._("Mentorship karma rewards cannot be negative.")
                )

    def write(self, vals: Any) -> bool:
        if (
            "state" in vals
            and not self.env.su
            and any(self.env.user in (rec.mentor_id, rec.mentee_id) for rec in self)
        ):
            raise exceptions.UserError(
                self.env._(
                    "Use Accept/Decline/Complete/Cancel instead of changing"
                    " the status directly."
                )
            )
        return super().write(vals)

    def _check_may_accept(self) -> None:
        if self.env.su or self.env.user.has_group("base.group_erp_manager"):
            return
        for rec in self:
            proposer = rec.create_uid
            counterparty = rec.mentor_id if proposer == rec.mentee_id else rec.mentee_id
            if counterparty != self.env.user:
                raise exceptions.AccessError(
                    self.env._(
                        "Only %(who)s or a gamification manager can confirm this "
                        "mentorship. The person who proposed it cannot also "
                        "accept it.",
                        who=counterparty.name,
                    )
                )

    def action_accept(self) -> None:
        self._check_may_accept()
        self.filtered(lambda r: r.state == "pending").sudo().write({"state": "active"})

    def action_decline(self) -> None:
        self._check_may_accept()
        self.filtered(lambda r: r.state == "pending").sudo().write(
            {"state": "cancelled", "end_date": fields.Date.today()}
        )

    def _check_may_complete(self) -> None:
        if self.env.su or self.env.user.has_group("base.group_erp_manager"):
            return
        for rec in self:
            if rec.mentee_id != self.env.user:
                raise exceptions.AccessError(
                    self.env._(
                        "Only %(mentee)s or a gamification manager can complete "
                        "this mentorship. A mentor cannot award their own "
                        "completion rewards.",
                        mentee=rec.mentee_id.name,
                    )
                )

    def action_complete(self):
        self._check_may_complete()
        for rec in self.filtered(lambda r: r.state == "active"):
            rec_sudo = rec.sudo()
            rec_sudo.state = "completed"
            rec_sudo.end_date = fields.Date.today()

            if rec_sudo.mentor_karma_on_completion:
                rec_sudo.mentor_id._add_karma(
                    rec_sudo.mentor_karma_on_completion,
                    source=rec,
                    reason=self.env._(
                        "Mentorship completed with %s", rec_sudo.mentee_id.name
                    ),
                )
                rec_sudo.total_mentor_karma += rec_sudo.mentor_karma_on_completion

            if rec_sudo.completion_badge_id:
                BadgeUser = self.env["gamification.badge.user"].sudo()
                for user in (rec_sudo.mentor_id, rec_sudo.mentee_id):
                    BadgeUser.create(
                        {
                            "user_id": user.id,
                            "badge_id": rec_sudo.completion_badge_id.id,
                        }
                    )._send_badge()

    def action_cancel(self):
        self.filtered(lambda r: r.state == "active").sudo().write(
            {
                "state": "cancelled",
                "end_date": fields.Date.today(),
            }
        )

    def _on_mentee_rank_up(self, mentees) -> None:
        if not mentees:
            return
        pairings = self.sudo().search(
            [
                ("mentee_id", "in", mentees.ids),
                ("state", "=", "active"),
                ("mentor_karma_per_milestone", ">", 0),
            ]
        )
        if not pairings:
            return

        karma_per_mentor: dict[Any, dict[str, Any]] = {}
        for rec in pairings:
            mentee = rec.mentee_id
            gain = rec.mentor_karma_per_milestone
            entry = karma_per_mentor.setdefault(
                rec.mentor_id,
                {
                    "gain": 0,
                    "source": rec,
                    "reason": self.env._(
                        "Mentee %(mentee)s reached %(rank)s",
                        mentee=mentee.name,
                        rank=mentee.rank_id.name or "a new rank",
                    ),
                },
            )
            entry["gain"] += gain
            rec.mentee_milestones_reached += 1
            rec.total_mentor_karma += gain

        self.env["res.users"].sudo()._add_karma_batch(karma_per_mentor)

    @api.model
    def get_suggested_mentors(self, limit=5) -> list:
        user = self.env.user
        existing_pairings = self.search(
            [
                ("state", "in", ("pending", "active")),
                "|",
                ("mentee_id", "=", user.id),
                ("mentor_id", "=", user.id),
            ]
        )
        existing_pairing_ids = (
            existing_pairings.mentor_id | existing_pairings.mentee_id
        ).ids

        Users = self.env["res.users"]
        mentors = Users.search(
            [
                ("karma", ">", user.karma),
                ("id", "!=", user.id),
                ("id", "not in", existing_pairing_ids),
                ("company_id", "=", user.company_id.id),
                *Users._get_domain_gamification_listable(),
            ],
            order="karma desc",
            limit=Users._gamification_clamp_limit(limit),
        )
        return [
            {
                "user_id": m.id,
                "user_name": m.name,
                "karma": m.karma,
                "rank_name": m.rank_id.name or "",
            }
            for m in mentors
        ]
