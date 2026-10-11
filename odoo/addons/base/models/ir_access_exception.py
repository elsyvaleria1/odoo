import contextvars
from datetime import timedelta
from typing import Any, Self

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import frozendict

from .ir_access_log import kept_on_uninstall

EXCEPTION_LOG_EVENTS = [
    ("exception_created", "Exception granted"),
    ("exception_changed", "Exception changed"),
    ("exception_used", "Exception used"),
    ("exception_revoked", "Exception revoked"),
]
EXCEPTION_MAX_DAYS = 365
REVOCATION_FIELDS = frozenset(
    {"revoked_at", "revoked_by_id", "revoke_reason", "granted_by_id"}
)
_REVOKING: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "ir_access_exception_revoking", default=False
)


class IrAccessLog(models.Model):
    _inherit = "ir.access.log"
    _access_anchors = frozendict(
        {
            "owner": "subject_user_id",
        }
    )

    event = fields.Selection(
        selection_add=EXCEPTION_LOG_EVENTS,
        ondelete=kept_on_uninstall(EXCEPTION_LOG_EVENTS),
    )


class IrAccessException(models.Model):

    _name = "ir.access.exception"
    _description = "Access Exception"
    _order = "date_to, id"
    _allow_sudo_commands = False
    _access_anchors = frozendict(
        {
            "company": "user_id.company_ids",
            "owner": "reviewer_ids",
            "user": models.Anchor("user_id", kind="owner"),
        }
    )

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Person",
        index=True,
        required=True,
        ondelete="cascade",
        help="The one person the exception lets through.",
    )
    kind = fields.Selection(
        selection=[("sod", "Separation of duties")],
        index=True,
        required=True,
        help="The rule the exception lets the person past.",
    )
    res_model = fields.Char(
        string="Scope Model",
        index=True,
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Scope",
        index=True,
        required=True,
        help="What the rule is about: the duties rule, or the approval category.",
    )
    scope_name = fields.Char(
        string="Applies To",
        compute="_compute_scope_name",
        compute_sudo=True,
    )
    reason = fields.Text(required=True)
    reviewer_ids = fields.Many2many(
        comodel_name="res.users",
        relation="ir_access_exception_reviewer_rel",
        column1="exception_id",
        column2="user_id",
        string="Reviewers",
        compute="_compute_reviewer_ids",
        store=True,
        readonly=False,
        help="Who answers for the exception and is reminded before it lapses. "
        "Never the person it lets through.",
    )
    date_from = fields.Datetime(
        string="Valid From",
        default=fields.Datetime.now,
        required=True,
    )
    date_to = fields.Datetime(
        string="Valid Until",
        index=True,
        required=True,
    )
    granted_by_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.uid,
        readonly=True,
        ondelete="set null",
    )
    revoked_at = fields.Datetime(readonly=True)
    revoked_by_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        ondelete="set null",
    )
    revoke_reason = fields.Char(readonly=True)
    state = fields.Selection(
        selection=[
            ("scheduled", "Scheduled"),
            ("active", "Active"),
            ("lapsed", "Lapsed"),
            ("revoked", "Revoked"),
        ],
        compute="_compute_state",
        search="_search_state",
    )
    use_count = fields.Integer(
        string="Uses",
        compute="_compute_use",
        compute_sudo=True,
    )
    last_used = fields.Datetime(
        compute="_compute_use",
        compute_sudo=True,
    )

    _dates_ordered = models.Constraint(
        "CHECK (date_to > date_from)",
        "An exception ends after it starts.",
    )

    @api.depends("res_model", "res_id")
    def _compute_scope_name(self) -> None:
        for exception in self:
            record = (
                self.env[exception.res_model].browse(exception.res_id)
                if exception.res_model in self.env and exception.res_id
                else None
            )
            exception.scope_name = (
                record.display_name if record and record.exists() else False
            )

    @api.depends("user_id")
    def _compute_reviewer_ids(self) -> None:
        managers = self.env.ref("base.group_erp_manager").all_user_ids
        managers = managers.filtered(lambda user: user.active and not user.share)
        for exception in self:
            if (
                not exception.reviewer_ids
                or exception.user_id in exception.reviewer_ids
            ):
                exception.reviewer_ids = managers - exception.user_id

    @api.depends("date_from", "date_to", "revoked_at")
    def _compute_state(self) -> None:
        now = fields.Datetime.now()
        for exception in self:
            if exception.revoked_at:
                exception.state = "revoked"
            elif exception.date_from and exception.date_from > now:
                exception.state = "scheduled"
            elif exception.date_to and exception.date_to <= now:
                exception.state = "lapsed"
            else:
                exception.state = "active"

    def _search_state(self, operator: str, value: Any) -> Domain:
        if operator not in ("in", "not in"):
            return NotImplemented
        now = fields.Datetime.now()
        by_state = {
            "revoked": Domain("revoked_at", "!=", False),
            "scheduled": Domain("revoked_at", "=", False)
            & Domain("date_from", ">", now),
            "lapsed": Domain("revoked_at", "=", False) & Domain("date_to", "<=", now),
            "active": Domain("revoked_at", "=", False)
            & Domain("date_from", "<=", now)
            & Domain("date_to", ">", now),
        }
        domain = Domain.OR(by_state[state] for state in value if state in by_state)
        return domain if operator == "in" else ~domain

    def _compute_use(self) -> None:
        uses = {
            res_id: (count, last)
            for res_id, count, last in self.env["ir.access.log"]._read_group(
                [
                    ("event", "=", "exception_used"),
                    ("cause_model", "=", self._name),
                    ("cause_res_id", "in", self.ids),
                ],
                ["cause_res_id"],
                ["__count", "create_date:max"],
            )
        }
        for exception in self:
            exception.use_count, exception.last_used = uses.get(
                exception.id, (0, False)
            )

    @api.constrains("user_id", "reviewer_ids")
    def _check_reviewers(self) -> None:
        for exception in self:
            if not exception.reviewer_ids:
                raise ValidationError(
                    self.env._(
                        "The exception for %(user)s needs a reviewer.",
                        user=exception.user_id.name,
                    )
                )
            if exception.user_id in exception.reviewer_ids:
                raise ValidationError(
                    self.env._(
                        "%(user)s cannot review their own exception.",
                        user=exception.user_id.name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if not self.env.su and any(
            REVOCATION_FIELDS & vals.keys() for vals in vals_list
        ):
            raise UserError(
                self.env._("An exception records who gave and revoked it by itself.")
            )
        exceptions = super().create(vals_list)
        exceptions._check_not_own()
        exceptions._check_length()
        self.env["ir.access.log"]._record(
            [exception._log_values("exception_created") for exception in exceptions]
        )
        return exceptions

    def write(self, vals: dict[str, Any]) -> bool:
        self._check_not_own()
        if not self.env.su:
            if {"user_id", "kind", "res_model", "res_id"} & set(vals):
                raise UserError(
                    self.env._(
                        "Whom an exception lets through, and past what, does not "
                        "change: revoke it and grant another."
                    )
                )
            if not _REVOKING.get():
                if REVOCATION_FIELDS & set(vals):
                    raise UserError(
                        self.env._("An exception is revoked with Revoke, for good.")
                    )
                if self.filtered("revoked_at"):
                    raise UserError(
                        self.env._(
                            "A revoked exception does not change: grant another."
                        )
                    )
        result = super().write(vals)
        if {"date_from", "date_to"} & set(vals):
            self._check_length()
            self.env["ir.access.log"]._record(
                [
                    exception._log_values(
                        "exception_changed",
                        f"{exception.date_from} to {exception.date_to}",
                    )
                    for exception in self
                ]
            )
        return result

    def _check_length(self) -> None:
        if self.env.su:
            return
        days = EXCEPTION_MAX_DAYS
        for exception in self:
            start = exception.date_from or exception.create_date
            if exception.date_to - start > timedelta(days=days):
                raise ValidationError(
                    self.env._(
                        "An exception lasts %(days)s days at most; let this one "
                        "lapse and grant another when it is reviewed.",
                        days=days,
                    )
                )

    def _check_not_own(self) -> None:
        if self.env.su:
            return
        if own := self.filtered(lambda exception: exception.user_id == self.env.user):
            raise UserError(
                self.env._(
                    "%(user)s cannot grant or change an exception that lets them "
                    "through: another administrator does.",
                    user=own[0].user_id.name,
                )
            )

    @api.ondelete(at_uninstall=False)
    def _unlink_never(self) -> None:
        if not self.env.su:
            raise UserError(
                self.env._("An exception is revoked, never deleted: it is history.")
            )

    def _log_values(self, event: str, reason: str | None = None) -> dict:
        self.check_singleton()
        return {
            "event": event,
            "subject_user_id": self.user_id.id,
            "cause": self.kind,
            "cause_model": self._name,
            "cause_res_id": self.id,
            "reason": reason or self.reason,
        }

    def action_revoke(self, reason: str | None = None) -> None:
        live = self.filtered(lambda exception: not exception.revoked_at)
        token = _REVOKING.set(True)
        try:
            live.write(
                {
                    "revoked_at": fields.Datetime.now(),
                    "revoked_by_id": self.env.uid,
                    "revoke_reason": reason or False,
                }
            )
        finally:
            _REVOKING.reset(token)
        self.env["ir.access.log"]._record(
            [exception._log_values("exception_revoked", reason) for exception in live]
        )

    @api.model
    def _find(self, user, kind: str, scope) -> Self:
        if not user or not scope:
            return self.browse()
        return (
            self.with_privilege(
                "base.privilege_read_access_exceptions",
                reason="find the exception a strict rule consults",
            )
            .search(
                [
                    ("user_id", "=", user.id),
                    ("kind", "=", kind),
                    ("res_model", "=", scope._name),
                    ("res_id", "=", scope.id),
                    ("state", "=", "active"),
                ],
                limit=1,
            )
            .with_env(self.env)
        )

    def _record_use(self, reason: str) -> None:
        self.env["ir.access.log"]._record(
            [exception._log_values("exception_used", reason) for exception in self]
        )
