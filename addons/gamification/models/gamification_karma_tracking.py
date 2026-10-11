from datetime import datetime
from typing import Literal, Self

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.models import ValuesType
from odoo.tools import date_utils

KARMA_VALUE_FIELDS = frozenset({"gain", "new_value", "old_value", "user_id"})


class GamificationKarmaTracking(models.Model):
    """Audit log of all karma changes with source attribution."""

    _name = "gamification.karma.tracking"
    _description = "Track Karma Changes"
    _rec_name = "user_id"
    _order = "tracking_date desc, id desc"

    def _selection_origin_models(self) -> list[tuple[str, str]]:
        return [
            ("res.users", self.env._("User")),
            ("gamification.streak", self.env._("Streak")),
            ("gamification.kudos", self.env._("Kudos")),
            ("gamification.achievement.unlock", self.env._("Achievement")),
            ("gamification.quest.enrollment", self.env._("Quest")),
            ("gamification.skill.node.unlock", self.env._("Skill")),
            ("gamification.mentorship", self.env._("Mentorship")),
        ]

    user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        required=True,
        ondelete="cascade",
    )
    old_value = fields.Integer(
        string="Old Karma Value",
        readonly=True,
    )
    new_value = fields.Integer(
        string="New Karma Value",
        required=True,
    )
    gain = fields.Integer(
        compute="_compute_gain",
        readonly=False,
    )
    consolidated = fields.Boolean()

    tracking_date = fields.Datetime(
        default=fields.Datetime.now,
        index=True,
        readonly=True,
    )
    reason = fields.Text(
        string="Description",
        default=lambda self: self.env._("Add Manually"),
    )
    origin_ref = fields.Reference(
        selection=lambda self: self._selection_origin_models(),
        string="Source",
        default=lambda self: f"res.users,{self.env.user.id}",
    )
    origin_ref_model_name = fields.Selection(
        selection=lambda self: self._selection_origin_models(),
        string="Source Type",
        compute="_compute_origin_ref_model_name",
        precompute=True,
        store=True,
    )

    _unconsolidated_date_idx = models.Index(
        "(tracking_date) WHERE consolidated IS NOT TRUE"
    )

    @api.depends("old_value", "new_value")
    def _compute_gain(self) -> None:
        for karma in self:
            karma.gain = karma.new_value - (karma.old_value or 0)

    @api.depends("origin_ref")
    def _compute_origin_ref_model_name(self) -> None:
        for karma in self:
            if not karma.origin_ref:
                karma.origin_ref_model_name = False
                continue

            karma.origin_ref_model_name = karma.origin_ref._name

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        users = self.env["res.users"].browse(
            [
                values["user_id"]
                for values in vals_list
                if "old_value" not in values and values.get("user_id")
            ]
        )
        karma_per_users = {user.id: user.karma for user in users}

        for values in vals_list:
            user_id = values.get("user_id")
            if "old_value" not in values and user_id:
                values["old_value"] = karma_per_users[user_id]

            if "gain" in values and "old_value" in values:
                values["new_value"] = values["old_value"] + values["gain"]
                del values["gain"]

            if user_id and "new_value" in values:
                karma_per_users[user_id] = values["new_value"]

        records = super().create(vals_list)
        records._recompute_user_ranks()
        return records

    def write(self, vals: ValuesType) -> Literal[True]:
        res = super().write(vals)
        if not KARMA_VALUE_FIELDS.isdisjoint(vals):
            self._recompute_user_ranks()
        return res

    def unlink(self) -> Literal[True]:
        users = self.user_id
        res = super().unlink()
        users._recompute_rank_if_relevant()
        return res

    def _recompute_user_ranks(self) -> None:
        self.user_id._recompute_rank_if_relevant()

    @api.model
    def _consolidate_cron(self) -> bool:
        from_date = date_utils.start_of(
            fields.Datetime.today(), "month"
        ) - relativedelta(months=2)
        return self._process_consolidate(from_date)

    def _process_consolidate(
        self, from_date: datetime, end_date: datetime | None = None
    ) -> bool:
        self.env["gamification.karma.tracking"].flush_model()

        if not end_date:
            end_date = date_utils.end_of(date_utils.end_of(from_date, "month"), "day")

        select_query = """
        WITH window_rows AS (
            SELECT user_id,
                   MIN(tracking_date) AS from_date,
                   SUM(new_value - COALESCE(old_value, 0)) AS total_gain,
                   (ARRAY_AGG(COALESCE(old_value, 0)
                              ORDER BY tracking_date ASC, id ASC))[1] AS first_old
              FROM gamification_karma_tracking
             WHERE tracking_date BETWEEN %(from_date)s AND %(end_date)s
               AND consolidated IS NOT TRUE
          GROUP BY user_id
        )
            INSERT INTO gamification_karma_tracking (
                            user_id,
                            old_value,
                            new_value,
                            tracking_date,
                            origin_ref,
                            origin_ref_model_name,
                            consolidated,
                            reason)
            SELECT          user_id,
                            first_old,
                            first_old + total_gain,
                            from_date,
                            %(origin_ref)s,
                            'res.users',
                            TRUE,
                            %(reason)s
              FROM window_rows
        """

        self.env.cr.execute(
            select_query,
            {
                "from_date": from_date,
                "end_date": end_date,
                "origin_ref": f"res.users,{self.env.user.id}",
                "reason": self.env._(
                    "Consolidation from %(from_date)s to %(end_date)s",
                    from_date=from_date.date(),
                    end_date=end_date.date(),
                ),
            },
        )

        self.env.cr.execute(
            """
            DELETE FROM gamification_karma_tracking
             WHERE tracking_date BETWEEN %(from_date)s AND %(end_date)s
               AND consolidated IS NOT TRUE
            """,
            {"from_date": from_date, "end_date": end_date},
        )
        self.env["gamification.karma.tracking"].invalidate_model()
        self.env["res.users"].invalidate_model(["karma", "karma_tracking_ids"])
        return True
