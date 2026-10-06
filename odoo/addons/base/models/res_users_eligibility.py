from datetime import timedelta
from typing import Any, Self

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

from .ir_access_log import kept_on_uninstall
from .res_users_grant import activating

_debug = DebugLog(__name__)

ELEVATION_LOG_EVENTS = [
    ("elevation_activated", "Elevation activated"),
    ("elevation_ended", "Elevation ended"),
    ("break_glass_opened", "Break-glass opened"),
    ("break_glass_closed", "Break-glass closed"),
]
ACTIVATION_CAUSES = ("activation", "break_glass")


class IrAccessLog(models.Model):
    _inherit = "ir.access.log"

    event = fields.Selection(
        selection_add=ELEVATION_LOG_EVENTS,
        ondelete=kept_on_uninstall(ELEVATION_LOG_EVENTS),
    )


class ResGroups(models.Model):
    _inherit = "res.groups"

    is_break_glass = fields.Boolean(
        string="Break-Glass",
        help="Held only for a few hours at a time, by activating an eligibility: "
        "the access administrators are told when it opens, and a review "
        "follows when it closes.",
    )


class ResUsersEligibility(models.Model):
    _name = "res.users.eligibility"
    _description = "Eligibility"
    _order = "user_id, group_id, id"
    _allow_sudo_commands = False
    _access_audit = True
    _access_anchors = frozendict({"owner": "user_id"})
    _access_verbs = {
        "activate": models.Verb(requires="read", methods=("action_activate",)),
    }

    user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        required=True,
        ondelete="cascade",
        help="Who may activate the group.",
    )
    group_id = fields.Many2one(
        comodel_name="res.groups",
        index=True,
        required=True,
        ondelete="cascade",
        help="The group an activation grants, for a few hours.",
    )
    company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="res_users_eligibility_company_rel",
        column1="eligibility_id",
        column2="company_id",
        string="Companies",
        help="The companies the activation's grant is limited to; empty: every "
        "company the user works in.",
    )
    max_hours = fields.Float(
        string="Longest Activation (hours)",
        default=8.0,
        required=True,
    )
    justification_required = fields.Boolean(default=True)
    is_break_glass = fields.Boolean(related="group_id.is_break_glass")
    state = fields.Selection(
        selection=[("active", "Active"), ("revoked", "Revoked")],
        default="active",
        index=True,
        readonly=True,
        required=True,
    )
    reason = fields.Char(help="Why the person may activate the group.")
    granted_by_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.uid,
        readonly=True,
        ondelete="set null",
    )
    revoked_by_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        ondelete="set null",
    )
    revoked_at = fields.Datetime(readonly=True)
    revoke_reason = fields.Char(readonly=True)
    active_until = fields.Datetime(
        compute="_compute_active_until",
        help="When the live activation ends; empty: not active now.",
    )

    _max_hours_positive = models.Constraint(
        "CHECK (max_hours > 0)",
        "An activation lasts some time.",
    )

    @api.depends("user_id", "group_id")
    def _compute_display_name(self) -> None:
        for eligibility in self:
            eligibility.display_name = (
                f"{eligibility.user_id.display_name}: {eligibility.group_id.full_name}"
            )

    def _compute_active_until(self) -> None:
        live = self._live_activations()
        until = {grant.cause_res_id: grant.date_to for grant in live}
        for eligibility in self:
            eligibility.active_until = until.get(eligibility.id, False)

    def _live_activations(
        self, grants: models.BaseModel | None = None
    ) -> models.BaseModel:
        grants = grants if grants is not None else self.env["res.users.grant"]
        if not self.ids or not grants.has_access("read"):
            return grants
        return grants.search(
            grants._live_domain()
            & Domain("cause", "in", ACTIVATION_CAUSES)
            & Domain("cause_model", "=", self._name)
            & Domain("cause_res_id", "in", self.ids)
        )

    @api.constrains("user_id", "group_id", "state")
    def _check_not_held_standing(self) -> None:
        # an eligibility for a group the person holds anyway, directly or
        # through a group implying it, is standing access by another name
        grants = self.env["res.users.grant"]
        for eligibility in self.filtered(lambda e: e.state == "active"):
            standing = grants.search(
                grants._live_domain()
                & Domain("user_id", "=", eligibility.user_id.id)
                & Domain("cause", "not in", ACTIVATION_CAUSES)
                & Domain("group_id.all_implied_ids", "in", eligibility.group_id.ids)
            )
            if standing:
                raise ValidationError(
                    self.env._(
                        "%(user)s holds %(group)s through %(standing)s already: "
                        "revoke that before making the group something to "
                        "activate.",
                        user=eligibility.user_id.name,
                        group=eligibility.group_id.full_name,
                        standing=", ".join(standing.group_id.mapped("full_name")),
                    )
                )

    @api.constrains("group_id")
    def _check_group(self) -> None:
        for eligibility in self:
            group = eligibility.group_id
            if (
                group.is_privilege
                or group in self.env["res.groups"]._get_user_type_groups()
            ):
                raise ValidationError(
                    self.env._(
                        "%(group)s cannot be activated: it is code's or it says "
                        "what kind of user someone is.",
                        group=group.full_name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        eligibilities = super().create(vals_list)
        _debug.lifecycle("created", eligibilities=eligibilities.ids)
        return eligibilities

    def write(self, vals: dict[str, Any]) -> bool:
        if {"user_id", "group_id"} & vals.keys():
            raise UserError(
                self.env._(
                    "An eligibility's person and group do not change: revoke it "
                    "and create another."
                )
            )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_by_the_superuser(self) -> None:
        if not self.env.su:
            raise UserError(
                self.env._(
                    "An eligibility is part of the record of who could do what: "
                    "revoke it instead of deleting it."
                )
            )

    def action_activate(
        self, hours: float | None = None, justification: str | None = None
    ) -> bool:
        self.check_singleton()
        if self.state != "active":
            raise UserError(self.env._("This eligibility was revoked."))
        hours = float(hours or self.max_hours)
        if not 0 < hours <= self.max_hours:
            raise UserError(
                self.env._(
                    "An activation of %(group)s lasts at most %(hours)s hours.",
                    group=self.group_id.full_name,
                    hours=self.max_hours,
                )
            )
        justification = (justification or "").strip()
        if self.justification_required and not justification:
            raise UserError(self.env._("Say why you need %s.", self.group_id.full_name))
        if self._live_activations():
            raise UserError(
                self.env._(
                    "%(group)s is active until %(until)s already.",
                    group=self.group_id.full_name,
                    until=self.active_until,
                )
            )
        cause = "break_glass" if self.is_break_glass else "activation"
        grants = self.env["res.users.grant"].with_privilege(
            "base.privilege_activate_eligibility", reason=justification or cause
        )
        with activating():
            grant = grants.create(
                {
                    "user_id": self.user_id.id,
                    "group_id": self.group_id.id,
                    "company_ids": [fields.Command.set(self.company_ids.ids)],
                    "date_to": self.env.cr.now() + timedelta(hours=hours),
                    "cause": cause,
                    "cause_model": self._name,
                    "cause_res_id": self.id,
                    "reason": justification or False,
                }
            )
        _debug.lifecycle(
            "activated", eligibility=self.id, grant=grant.id, hours=hours, cause=cause
        )
        self._log(
            "break_glass_opened" if cause == "break_glass" else "elevation_activated",
            grant,
            justification,
        )
        return True

    def action_stop(self) -> None:
        grants = self._live_activations()
        if grants:
            grants.with_privilege(
                "base.privilege_activate_eligibility", reason="stopped"
            ).action_revoke(self.env._("Stopped early"))

    def action_revoke(self, reason: str | None = None) -> bool:
        live = self.filtered(lambda eligibility: eligibility.state == "active")
        ending = self.env["res.users.grant"].with_privilege(
            "base.privilege_end_activation", reason=reason or "eligibility revoked"
        )
        live._live_activations(ending).action_revoke(reason)
        live.write(
            {
                "state": "revoked",
                "revoked_by_id": self.env.uid,
                "revoked_at": self.env.cr.now(),
                "revoke_reason": reason or False,
            }
        )
        return True

    def action_open_activate(self) -> dict[str, Any]:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Activate %s", self.group_id.full_name),
            "res_model": "wizard.res.users.eligibility.activate",
            "view_mode": "form",
            "target": "new",
            "context": {"default_eligibility_id": self.id},
        }

    def _log(self, event: str, grant: models.BaseModel, reason: str | None) -> None:
        self.env["ir.access.log"]._record(
            [
                {
                    "event": event,
                    "subject_user_id": eligibility.user_id.id,
                    "group_id": eligibility.group_id.id,
                    "grant_id": grant.id,
                    "cause": grant.cause,
                    "cause_model": self._name,
                    "cause_res_id": eligibility.id,
                    "reason": reason or False,
                }
                for eligibility in self
            ]
        )


class ResUsersGrant(models.Model):
    _inherit = "res.users.grant"

    def _on_grant_changed(self, event: str) -> None:
        super()._on_grant_changed(event)
        if event not in ("grant_expired", "grant_revoked"):
            return
        ended = self.filtered(
            lambda grant: (
                grant.cause in ACTIVATION_CAUSES
                and grant.cause_model == "res.users.eligibility"
            )
        )
        eligibilities = self.env["res.users.eligibility"].browse(
            ended.mapped("cause_res_id")
        )
        for grant in ended:
            eligibility = eligibilities.browse(grant.cause_res_id)
            eligibility._log(
                "break_glass_closed"
                if grant.cause == "break_glass"
                else "elevation_ended",
                grant,
                event,
            )


class ResUsers(models.Model):
    _inherit = "res.users"

    eligibility_ids = fields.One2many(
        comodel_name="res.users.eligibility",
        inverse_name="user_id",
        string="Eligibilities",
    )

    @property
    def SELF_READABLE_FIELDS(self) -> list[str]:
        return [*super().SELF_READABLE_FIELDS, "eligibility_ids"]
