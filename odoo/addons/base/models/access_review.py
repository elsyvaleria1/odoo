import contextvars
from datetime import timedelta
from typing import Any

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict
from odoo.tools.safe_eval import safe_eval

from .ir_access_log import kept_on_uninstall
from .res_users_grant import _marked

_debug = DebugLog(__name__)

REVIEW_LOG_EVENTS = [
    ("review_started", "Review started"),
    ("review_certified", "Access certified"),
    ("review_revoked", "Access revoked by a review"),
    ("review_closed", "Review closed"),
]
REVIEW_KINDS = [
    ("memberships", "Group memberships"),
    ("eligibilities", "Eligibilities"),
    ("links", "External links"),
    ("exceptions", "Access exceptions"),
    ("timed_grants", "Grants ending soon"),
    ("break_glass", "Break-glass sessions"),
]
KIND_MODELS = {
    "memberships": "res.users.grant",
    "eligibilities": "res.users.eligibility",
    "links": "access.link",
    "exceptions": "ir.access.exception",
    "timed_grants": "res.users.grant",
    "break_glass": "res.users.eligibility",
}
_DECIDING: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "access_review_deciding", default=False
)
DECISION_FIELDS = frozenset(
    {
        "decision",
        "decided_by_id",
        "decided_at",
        "applied_at",
        "escalated",
        "reviewer_ids",
        "res_model",
        "res_id",
        "subject_user_id",
        "group_id",
        "campaign_id",
    }
)
REVOKED_AT_DEADLINE = frozenset({"eligibilities", "links", "exceptions"})


class IrAccessLog(models.Model):
    _inherit = "ir.access.log"

    event = fields.Selection(
        selection_add=REVIEW_LOG_EVENTS,
        ondelete=kept_on_uninstall(REVIEW_LOG_EVENTS),
    )


class MixinAccessReviewable(models.AbstractModel):
    _name = "mixin.access.reviewable"
    _description = "Access a Review May Revoke"
    _access_anchors = frozendict(
        {"review": models.Anchor("review_revoker_ids", kind="owner")}
    )

    review_revoker_ids = fields.Many2many(
        comodel_name="res.users",
        compute="_compute_review_revoker_ids",
        search="_search_review_revoker_ids",
        help="The reviewers who decided to revoke this access, while the review "
        "has not applied it yet.",
    )

    def _review_revoker_pairs(self, user_ids: list[int] | None) -> list[tuple]:
        self.env["access.review.item"].flush_model(
            ["res_model", "res_id", "decision", "applied_at", "reviewer_ids"]
        )
        self.env.cr.execute(
            SQL(
                """SELECT item.res_id, rel.user_id
                     FROM access_review_item AS item
                     JOIN access_review_item_reviewer_rel AS rel
                       ON rel.item_id = item.id
                    WHERE item.res_model = %s
                      AND item.decision = 'revoked'
                      AND item.applied_at IS NULL
                      AND %s""",
                self._name,
                SQL("rel.user_id = ANY(%s)", user_ids)
                if user_ids is not None
                else SQL("item.res_id = ANY(%s)", list(self.ids)),
            )
        )
        return self.env.cr.fetchall()

    def _compute_review_revoker_ids(self) -> None:
        revokers: dict[int, list[int]] = {}
        for res_id, user_id in self._review_revoker_pairs(None):
            revokers.setdefault(res_id, []).append(user_id)
        for record in self:
            record.review_revoker_ids = [
                fields.Command.set(revokers.get(record.id, []))
            ]

    def _search_review_revoker_ids(self, operator: str, value: Any) -> Domain:
        if operator not in ("in", "="):
            return NotImplemented
        user_ids = [value] if isinstance(value, int) else list(value)
        ids = [res_id for res_id, _user in self._review_revoker_pairs(user_ids)]
        return Domain("id", "in", ids) if ids else Domain.FALSE

    def _review_revoke(self, reason: str) -> None:
        raise NotImplementedError(self._name)


class ResUsersGrant(models.Model):
    _name = "res.users.grant"
    _inherit = ["res.users.grant", "mixin.access.reviewable"]

    def _review_revoke(self, reason: str) -> None:
        self.action_revoke(reason)


class ResUsersEligibility(models.Model):
    _name = "res.users.eligibility"
    _inherit = ["res.users.eligibility", "mixin.access.reviewable"]

    def _review_revoke(self, reason: str) -> None:
        self.action_revoke(reason)


class AccessLink(models.Model):
    _name = "access.link"
    _inherit = ["access.link", "mixin.access.reviewable"]

    def _review_revoke(self, reason: str) -> None:
        self.action_revoke(reason)

    def _review_issuer(self) -> models.BaseModel:
        self.check_singleton()
        issuer = self.create_uid
        return issuer if issuer and not issuer._is_superuser() else issuer.browse()


class IrAccessException(models.Model):
    _name = "ir.access.exception"
    _inherit = ["ir.access.exception", "mixin.access.reviewable"]

    def _review_revoke(self, reason: str) -> None:
        self.action_revoke(reason)


class AccessReviewCampaign(models.Model):
    _name = "access.review.campaign"
    _description = "Access Review"
    _order = "date_deadline desc, id desc"
    _access_audit = True

    name = fields.Char(required=True)
    kind = fields.Selection(
        selection=REVIEW_KINDS,
        default="memberships",
        required=True,
    )
    state = fields.Selection(
        selection=[("draft", "Draft"), ("running", "Running"), ("closed", "Closed")],
        default="draft",
        index=True,
        readonly=True,
        required=True,
    )
    group_ids = fields.Many2many(
        comodel_name="res.groups",
        relation="access_review_campaign_group_rel",
        column1="campaign_id",
        column2="group_id",
        help="Memberships and eligibilities: the groups reviewed, with every group "
        "implying one of them; empty: every group.",
    )
    older_than_days = fields.Integer(
        help="Memberships: only the grants made more than this many days ago.",
    )
    ending_within_days = fields.Integer(
        default=30,
        help="Exceptions and grants ending soon: the ones ending within this "
        "many days of the start.",
    )
    description = fields.Text(
        help="What the review covers and what it leaves out, for its reviewers.",
    )
    link_domain = fields.Char(
        default="[('state', '=', 'live'), ('legacy_source', '=', False), "
        "('cause', '=', 'share')]",
        help="External links: which live links are reviewed.",
    )
    reviewer = fields.Selection(
        selection=[
            ("admin_group", "The group's administrators"),
            ("issuer", "Who issued the access"),
            ("named", "Named reviewers"),
        ],
        default="admin_group",
        required=True,
        help="Who decides each item. Never the person the item is about: when "
        "nobody else is left, the access administrators decide.",
    )
    reviewer_ids = fields.Many2many(
        comodel_name="res.users",
        relation="access_review_campaign_reviewer_rel",
        column1="campaign_id",
        column2="user_id",
        string="Reviewers",
    )
    date_planned = fields.Date(
        string="Starts On",
        help="A draft review with this date starts by itself that day.",
    )
    date_start = fields.Date(readonly=True)
    date_deadline = fields.Date(
        string="Deadline",
        default=lambda self: fields.Date.context_today(self) + timedelta(days=14),
        required=True,
    )
    on_deadline = fields.Selection(
        selection=[("revoke", "Revoke"), ("keep", "Keep and escalate")],
        compute="_compute_on_deadline",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
        help="What happens to an item still pending at the deadline.",
    )
    recurrence_months = fields.Integer(
        string="Repeat Every (months)",
        help="Once closed, the review starts again after this many months; 0: once.",
    )
    item_ids = fields.One2many(
        comodel_name="access.review.item",
        inverse_name="campaign_id",
        string="Items",
    )
    pending_count = fields.Integer(compute="_compute_counts")
    certified_count = fields.Integer(compute="_compute_counts")
    revoked_count = fields.Integer(compute="_compute_counts")

    @api.depends("kind")
    def _compute_on_deadline(self) -> None:
        for campaign in self:
            campaign.on_deadline = (
                "revoke" if campaign.kind in REVOKED_AT_DEADLINE else "keep"
            )

    @api.depends("item_ids.decision")
    def _compute_counts(self) -> None:
        for campaign in self:
            decisions = campaign.item_ids.mapped("decision")
            campaign.pending_count = decisions.count("pending")
            campaign.certified_count = decisions.count("certified")
            campaign.revoked_count = decisions.count("revoked")

    def action_start(self) -> bool:
        for campaign in self:
            if campaign.state != "draft":
                raise UserError(self.env._("%s has started already.", campaign.name))
            targets = campaign._scope_records()
            campaign.env["access.review.item"].create(
                [campaign._item_values(target) for target in targets]
            )
            campaign.write(
                {"state": "running", "date_start": fields.Date.context_today(self)}
            )
            campaign._log("review_started", len(targets))
            _debug.lifecycle(
                "review_started",
                campaign=campaign.id,
                kind=campaign.kind,
                items=len(targets),
            )
        return True

    def _scope_records(self) -> models.BaseModel:
        self.check_singleton()
        model = self.env["ir.access"]._access_evaluator(KIND_MODELS[self.kind])
        now = self.env.cr.now()
        Grant = self.env["res.users.grant"]
        groups = self.group_ids.all_implied_by_ids if self.group_ids else None
        if self.kind == "memberships":
            domain = (
                Grant._live_domain()
                & Domain("cause", "not in", ("activation", "break_glass"))
                & Domain("user_id.active", "=", True)
            )
            if groups is not None:
                domain &= Domain("group_id", "in", groups.ids)
            if self.older_than_days:
                domain &= Domain(
                    "create_date", "<", now - timedelta(days=self.older_than_days)
                )
        elif self.kind == "timed_grants":
            domain = (
                Grant._live_domain()
                & Domain("date_to", "!=", False)
                & Domain("date_to", "<=", now + timedelta(days=self.ending_within_days))
                & Domain("cause", "not in", ("activation", "break_glass"))
            )
        elif self.kind == "eligibilities":
            domain = Domain("state", "=", "active")
            if groups is not None:
                domain &= Domain("group_id", "in", groups.ids)
        elif self.kind == "exceptions":
            domain = Domain("state", "in", ("scheduled", "active")) & Domain(
                "date_to", "<=", now + timedelta(days=self.ending_within_days)
            )
        elif self.kind == "links":
            domain = Domain(safe_eval(self.link_domain or "[]"))
        else:
            domain = Domain.FALSE
        return model.search(domain)

    def _item_values(self, target: models.BaseModel) -> ValuesType:
        subject, group = self._item_subject(target)
        return {
            "campaign_id": self.id,
            "res_model": target._name,
            "res_id": target.id,
            "name": target.display_name,
            "subject_user_id": subject.id,
            "group_id": group.id,
            "reviewer_ids": [
                fields.Command.set(self._item_reviewers(target, subject, group).ids)
            ],
        }

    def _item_subject(self, target: models.BaseModel) -> tuple:
        groups = self.env["res.groups"]
        if target._name in ("res.users.grant", "res.users.eligibility"):
            return target.user_id, target.group_id
        if target._name == "ir.access.exception":
            return target.user_id, groups
        return self.env["res.users"], groups

    def _item_reviewers(
        self,
        target: models.BaseModel,
        subject: models.BaseModel,
        group: models.BaseModel,
    ) -> models.BaseModel:
        users = self.env["res.users"]
        if self.reviewer == "named":
            reviewers = self.reviewer_ids
        elif self.reviewer == "issuer":
            if target._name == "ir.access.exception":
                reviewers = target.reviewer_ids
            elif target._name == "access.link":
                reviewers = target._review_issuer()
            else:
                reviewers = target.granted_by_id
        else:
            admin = group.admin_group_id or self.env.ref("base.group_erp_manager")
            reviewers = admin.all_user_ids
        excluded = subject
        if self.reviewer != "issuer" and "granted_by_id" in target._fields:
            excluded |= target.granted_by_id
        reviewers = (
            reviewers.filtered(lambda user: user.active and not user.share) - excluded
        )
        if reviewers:
            return reviewers
        administrators = self.env.ref("base.group_erp_manager").all_user_ids
        return administrators.filtered(lambda user: user.active) - excluded or users

    @api.model
    def _cron_close_due(self) -> None:
        today = fields.Date.context_today(self)
        for campaign in self.search(
            [("state", "=", "running"), ("date_deadline", "<", today)]
        ):
            campaign._close()
        self.search(
            [
                ("state", "=", "draft"),
                ("date_planned", "!=", False),
                ("date_planned", "<=", today),
            ]
        ).action_start()

    def action_close(self) -> bool:
        for campaign in self.filtered(lambda campaign: campaign.state == "running"):
            campaign._close()
        return True

    def _close(self) -> None:
        self.check_singleton()
        pending = self.item_ids.filtered(lambda item: item.decision == "pending")
        if self.on_deadline == "revoke":
            pending._decide("revoked", self.env._("Not certified by the deadline"))
        else:
            with _marked(_DECIDING):
                pending.write({"escalated": True})
        self.write({"state": "closed"})
        self._log("review_closed", len(pending))
        _debug.lifecycle(
            "review_closed",
            campaign=self.id,
            pending=len(pending),
            on_deadline=self.on_deadline,
        )
        if self.recurrence_months:
            start = (
                self.date_start or fields.Date.context_today(self)
            ) + relativedelta(months=self.recurrence_months)
            span = self.date_deadline - (self.date_start or self.date_deadline)
            self.copy(
                {
                    "name": self.name,
                    "date_planned": start,
                    "date_deadline": start + span,
                    "date_start": False,
                }
            )

    def _log(self, event: str, count: int) -> None:
        self.env["ir.access.log"]._record(
            [
                {
                    "event": event,
                    "model_name": self._name,
                    "res_ids": str(self.id),
                    "reason": self.name,
                    "count": count,
                }
            ]
        )


class AccessReviewItem(models.Model):
    _name = "access.review.item"
    _description = "Access Review Item"
    _order = "campaign_id, decision, id"
    _access_audit = True
    _access_anchors = frozendict({"owner": "reviewer_ids"})
    _access_verbs = {
        "decide": models.Verb(
            requires="read", methods=("action_certify", "action_revoke")
        ),
    }

    campaign_id = fields.Many2one(
        comodel_name="access.review.campaign",
        index=True,
        required=True,
        ondelete="cascade",
    )
    kind = fields.Selection(related="campaign_id.kind")
    res_model = fields.Char(
        string="Model",
        readonly=True,
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Access",
        readonly=True,
        required=True,
    )
    name = fields.Char(readonly=True)
    subject_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Person",
        index=True,
        readonly=True,
        ondelete="set null",
    )
    group_id = fields.Many2one(
        comodel_name="res.groups",
        readonly=True,
        ondelete="set null",
    )
    reviewer_ids = fields.Many2many(
        comodel_name="res.users",
        relation="access_review_item_reviewer_rel",
        column1="item_id",
        column2="user_id",
        string="Reviewers",
    )
    decision = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("certified", "Certified"),
            ("revoked", "Revoked"),
        ],
        default="pending",
        index=True,
        readonly=True,
        required=True,
    )
    decided_by_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        ondelete="set null",
    )
    decided_at = fields.Datetime(readonly=True)
    note = fields.Char()
    applied_at = fields.Datetime(readonly=True)
    escalated = fields.Boolean(
        readonly=True,
        help="Still pending when the review closed, and kept.",
    )

    @api.constrains("reviewer_ids", "subject_user_id")
    def _check_not_own(self) -> None:
        for item in self:
            if item.subject_user_id and item.subject_user_id in item.reviewer_ids:
                raise ValidationError(
                    self.env._(
                        "%(user)s cannot review their own access.",
                        user=item.subject_user_id.name,
                    )
                )

    def write(self, vals: ValuesType) -> bool:
        if DECISION_FIELDS & vals.keys() and not (self.env.su or _DECIDING.get()):
            raise UserError(
                self.env._("A review item is decided by certifying or revoking it.")
            )
        return super().write(vals)

    def action_certify(self, note: str | None = None) -> None:
        self._decide("certified", note)

    def action_revoke(self, note: str | None = None) -> bool:
        self._decide("revoked", note)
        return True

    def _decide(self, decision: str, note: str | None) -> None:
        pending = self.filtered(lambda item: item.decision == "pending")
        if not pending:
            return
        if self.env.uid in pending.subject_user_id.ids:
            raise UserError(self.env._("Nobody reviews their own access."))
        now = self.env.cr.now()
        with _marked(_DECIDING):
            pending.write(
                {
                    "decision": decision,
                    "decided_by_id": self.env.uid,
                    "decided_at": now,
                    "note": note or False,
                }
            )
            if decision == "revoked":
                pending._apply()
        pending._log(
            "review_revoked" if decision == "revoked" else "review_certified", note
        )

    def _apply(self) -> None:
        reason = self.env._("Revoked by an access review")
        for res_model, items in self.grouped("res_model").items():
            targets = (
                self.env[res_model]
                .with_privilege("base.privilege_apply_review", reason=reason)
                .browse(items.mapped("res_id"))
                .exists()
            )
            targets._review_revoke(reason)
        self.write({"applied_at": self.env.cr.now()})

    def _log(self, event: str, note: str | None) -> None:
        self.env["ir.access.log"]._record(
            [
                {
                    "event": event,
                    "subject_user_id": item.subject_user_id.id,
                    "group_id": item.group_id.id,
                    "model_name": item.res_model,
                    "res_ids": str(item.res_id),
                    "reason": note or item.campaign_id.name,
                }
                for item in self
            ]
        )


class ResUsersGrantBreakGlass(models.Model):
    _inherit = "res.users.grant"

    def _on_grant_changed(self, event: str) -> None:
        super()._on_grant_changed(event)
        if event not in ("grant_expired", "grant_revoked"):
            return
        closed = self.filtered(lambda grant: grant.cause == "break_glass")
        if closed:
            self.env["access.review.campaign"]._review_break_glass(closed)


class AccessReviewCampaignBreakGlass(models.Model):
    _inherit = "access.review.campaign"

    @api.model
    def _review_break_glass(self, grants: models.BaseModel) -> None:
        campaigns = self.env["ir.access"]._access_evaluator(self._name)
        campaign = campaigns.search(
            [("kind", "=", "break_glass"), ("state", "=", "running")], limit=1
        )
        if not campaign:
            campaign = campaigns.create(
                {
                    "name": self.env._("Break-glass sessions"),
                    "kind": "break_glass",
                    "reviewer": "admin_group",
                    "date_deadline": fields.Date.context_today(self)
                    + timedelta(days=14),
                }
            )
            campaign.write(
                {"state": "running", "date_start": fields.Date.context_today(self)}
            )
        eligibilities = (
            self.env["ir.access"]
            ._access_evaluator("res.users.eligibility")
            .browse(grants.mapped("cause_res_id"))
        )
        campaign.env["access.review.item"].create(
            [
                campaign._item_values(eligibilities.browse(grant.cause_res_id))
                | {
                    "name": self.env._(
                        "%(eligibility)s, until %(until)s: %(why)s",
                        eligibility=eligibilities.browse(
                            grant.cause_res_id
                        ).display_name,
                        until=grant.revoked_at or grant.date_to,
                        why=grant.reason or "",
                    )
                }
                for grant in grants
                if grant.cause_model == "res.users.eligibility"
            ]
        )
