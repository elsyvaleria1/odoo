from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import frozendict

REVIEW_KINDS = [
    ("onboarding", "Onboarding"),
    ("periodic", "Periodic"),
    ("event", "Triggered by an event"),
    ("limit_request", "Limit request"),
    ("exception", "Reclassification of an exception"),
    ("manual", "Manual"),
]
REVIEW_STATES = [
    ("draft", "Draft"),
    ("in_progress", "In Progress"),
    ("approved", "Approved"),
    ("refused", "Refused"),
    ("cancel", "Cancelled"),
]


class CreditReview(models.Model):
    _name = "credit.review"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _description = "Credit Review"
    _order = "create_date desc, id desc"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    profile_id = fields.Many2one(
        comodel_name="credit.profile",
        index=True,
        required=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        related="profile_id.partner_id",
        store=True,
    )
    company_id = fields.Many2one(
        related="profile_id.company_id",
        store=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    kind = fields.Selection(
        selection=REVIEW_KINDS,
        default="manual",
        required=True,
    )
    state = fields.Selection(
        selection=REVIEW_STATES,
        default="draft",
        required=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Reviewer",
        default=lambda self: self.env.user,
        tracking=True,
    )
    trigger_event_id = fields.Many2one(
        comodel_name="credit.event",
        ondelete="set null",
    )
    score = fields.Float(
        digits=(5, 2),
        readonly=True,
    )
    line_ids = fields.One2many(
        comodel_name="credit.review.line",
        inverse_name="review_id",
        readonly=True,
    )
    grade_current_id = fields.Many2one(
        comodel_name="credit.grade",
        readonly=True,
    )
    grade_proposed_id = fields.Many2one(
        comodel_name="credit.grade",
        readonly=True,
    )
    grade_decided_id = fields.Many2one(
        comodel_name="credit.grade",
        tracking=True,
    )
    limit_current = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    limit_suggested = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    exposure_total = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    limit_decided = fields.Monetary(
        currency_field="currency_id",
        tracking=True,
        help="Facility granted on approval, replacing the profile's manual lines. "
        "Zero grants no line beyond the collateral.",
    )
    facility_months = fields.Integer(
        default=12,
        help="Months the granted facility runs before it expires.",
    )
    notes = fields.Html()
    decided_by_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
    )
    decided_on = fields.Datetime(readonly=True)

    @api.depends("partner_id", "kind", "create_date")
    def _compute_name(self):
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        for review in self:
            review.name = "%s: %s" % (
                kinds.get(review.kind, ""),
                review.partner_id.name or "",
            )

    @api.model_create_multi
    def create(self, vals_list):
        reviews = super().create(vals_list)
        reviews._snapshot()
        return reviews

    def _snapshot(self):
        for review in self:
            profile = review.profile_id
            profile._update_metrics()
            review.write(
                {
                    "score": profile.score,
                    "grade_current_id": profile.grade_id.id,
                    "grade_proposed_id": profile.grade_proposed_id.id,
                    "grade_decided_id": review.grade_decided_id.id
                    or profile.grade_proposed_id.id
                    or profile.grade_id.id,
                    "limit_current": profile.limit_amount,
                    "limit_suggested": profile.limit_suggested,
                    "exposure_total": profile.exposure_total,
                    "limit_decided": review.limit_decided
                    or max(profile.limit_suggested, profile.exposure_total),
                    "line_ids": [Command.clear()]
                    + [
                        Command.create(
                            {
                                name: line[name]
                                for name in self.env["credit.review.line"]._SNAPSHOT
                            }
                            | {"dimension_id": line.dimension_id.id}
                        )
                        for line in profile.score_line_ids
                    ],
                }
            )

    def action_refresh(self):
        self.filtered(lambda r: r.state in ("draft", "in_progress"))._snapshot()

    def action_start(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "in_progress"})

    def _check_can_decide(self) -> None:
        if not self.env.user.has_group("account_credit.group_credit_manager"):
            raise UserError(self.env._("Only a credit manager can decide a review."))
        for review in self:
            if review.state not in ("draft", "in_progress"):
                raise UserError(self.env._("This review is already decided."))

    def action_approve(self):
        self._check_can_decide()
        today = fields.Date.today()
        for review in self:
            if not review.grade_decided_id:
                raise ValidationError(self.env._("Decide a grade before approving."))
            profile = review.profile_id.sudo()
            profile.write({"grade_id": review.grade_decided_id.id})
            manual = profile.facility_ids.filtered(
                lambda f: f.source in ("manual", "grade") and f.state == "active"
            )
            if manual:
                manual.write({"state": "revoked"})
            if review.limit_decided > 0:
                self.env["credit.facility"].sudo().create(
                    {
                        "profile_id": profile.id,
                        "source": "grade",
                        "amount": review.limit_decided,
                        "date_start": today,
                        "date_end": today + relativedelta(months=review.facility_months)
                        if review.facility_months
                        else False,
                        "review_id": review.id,
                        "user_id": self.env.user.id,
                        "reason": review.name,
                    }
                )
            months = review.grade_decided_id.review_interval_months or 12
            profile.write(
                {
                    "next_review_date": today + relativedelta(months=months),
                    "exception_until": False,
                    "exception_reason": False,
                }
            )
            review.write(
                {
                    "state": "approved",
                    "decided_by_id": self.env.user.id,
                    "decided_on": fields.Datetime.now(),
                }
            )
            profile.message_post(
                body=self.env._(
                    "Review approved: grade %(grade)s, facility %(limit)s.",
                    grade=review.grade_decided_id.name,
                    limit=review.currency_id.format(review.limit_decided),
                )
            )

    def action_approve_proposed(self) -> None:
        self._check_can_decide()
        for review in self:
            grade = (
                review.grade_proposed_id
                or review.grade_current_id
                or review.profile_id.grade_id
            )
            if not grade:
                raise ValidationError(
                    self.env._(
                        "No grade is proposed for '%s'; decide it by hand.",
                        review.partner_id.name,
                    )
                )
            review.write({"grade_decided_id": grade.id})
        self.action_approve()

    def action_refuse(self):
        self._check_can_decide()
        self.write(
            {
                "state": "refused",
                "decided_by_id": self.env.user.id,
                "decided_on": fields.Datetime.now(),
            }
        )

    def action_cancel(self):
        self.filtered(lambda r: r.state in ("draft", "in_progress")).write(
            {"state": "cancel"}
        )


class CreditReviewLine(models.Model):
    _name = "credit.review.line"
    _inherit = ["mixin.score.line"]
    _description = "Credit Review Score Line"
    _order = "review_id, dimension_id, id"

    _SNAPSHOT = (
        "source_key",
        "grouping_key",
        "value",
        "points",
        "max_points",
        "applied",
        "applicable",
    )

    review_id = fields.Many2one(
        comodel_name="credit.review",
        index=True,
        required=True,
        ondelete="cascade",
    )
