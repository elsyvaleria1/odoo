import contextlib
import contextvars
import logging
from collections.abc import Iterator
from typing import Any

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain
from odoo.tools import frozendict, ormcache

from .ir_access_log import kept_on_uninstall

_logger = logging.getLogger(__name__)


DUTY_FIELDS = frozenset({"group_ids", "excluded_group_ids", "verb_ids"})
RULE_FIELDS = frozenset({"function_a_id", "function_b_id", "active"})
WIDENING_EVENTS = frozenset({"grant_created", "grant_changed", "grant_started"})

_SCANNING: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "sod_scanning", default=False
)


@contextlib.contextmanager
def _conflicts_created(rules: Any, cause: str) -> Iterator[None]:
    if _SCANNING.get() or not rules:
        yield
        return
    standing = rules._standing_conflicts()
    token = _SCANNING.set(True)
    try:
        yield
    finally:
        _SCANNING.reset(token)
    rules.env.registry.clear_cache("groups")
    rules._log_new_conflicts(standing, cause)


SOD_LOG_EVENTS = [
    ("sod_conflict", "Duties in conflict"),
    ("sod_refused", "Refused for conflicting duties"),
]


class IrAccessLog(models.Model):
    _inherit = "ir.access.log"

    event = fields.Selection(
        selection_add=SOD_LOG_EVENTS,
        ondelete=kept_on_uninstall(SOD_LOG_EVENTS),
    )


class IrAccess(models.Model):
    _inherit = "ir.access"

    @api.model
    def _duty_rules(self, model_ids: set[int]) -> Any:
        model_ids &= self.env["ir.access.sod.rule"]._get_duty_verb_model_ids()
        if not model_ids:
            return None
        lines = self.env["ir.access.sod.function.verb"].search(
            [("model_id", "in", sorted(model_ids))]
        )
        return lines.function_id._rules()

    @api.model_create_multi
    def create(self, vals_list):
        rules = self._duty_rules({vals.get("model_id") for vals in vals_list})
        with _conflicts_created(rules, "access_changed"):
            return super().create(vals_list)

    def write(self, vals):
        rules = self._duty_rules_of_rows("write", {vals.get("model_id")})
        with _conflicts_created(rules, "access_changed"):
            return super().write(vals)

    def unlink(self):
        rules = self._duty_rules_of_rows("unlink")
        with _conflicts_created(rules, "access_changed"):
            return super().unlink()

    def _duty_rules_of_rows(self, operation: str, model_ids: Any = ()) -> Any:
        if not self or not self.env["ir.access.sod.rule"]._get_duty_verb_model_ids():
            return None
        self.check_access(operation)
        return self._duty_rules(set(self.model_id.ids) | set(model_ids))


class IrAccessSodFunction(models.Model):

    _name = "ir.access.sod.function"
    _description = "Business Duty"
    _order = "name"

    name = fields.Char(
        translate=True,
        required=True,
    )
    group_ids = fields.Many2many(
        comodel_name="res.groups",
        help="Holding any of these groups, directly or through another, is holding "
        "the duty.",
    )
    excluded_group_ids = fields.Many2many(
        comodel_name="res.groups",
        relation="ir_access_sod_function_excluded_group_rel",
        string="Except Holders Of",
        help="Whoever holds one of these groups does not hold the duty, whatever "
        "else they hold: a manager who is also a clerk is not the clerk.",
    )
    verb_ids = fields.One2many(
        comodel_name="ir.access.sod.function.verb",
        inverse_name="function_id",
        string="Verbs",
        help="Holding a permission row for any of these verbs is holding the duty.",
    )

    def _get_holder_ids(
        self, users, scheduled: dict[int, frozenset[int]] | None = None
    ) -> set[int]:
        self.check_singleton()
        spec = dict(self._get_duty_spec())
        spec["verb_groups"] = self._verb_groups(spec["verbs"])
        if scheduled is None:
            scheduled = self._scheduled_group_ids(users)
        return {
            user.id
            for user in users
            if self._holds(
                spec,
                user.id,
                frozenset(user.all_group_ids._ids)
                | scheduled.get(user.id, frozenset()),
            )
        }

    @api.model
    def _scheduled_group_ids(self, users) -> dict[int, frozenset[int]]:
        grants = (
            self.env["res.users"]
            ._grant_model()
            .search_fetch(
                [("user_id", "in", users.ids), ("state", "=", "scheduled")],
                ["user_id", "group_id"],
            )
        )
        scheduled: dict[int, set[int]] = {}
        for grant in grants:
            scheduled.setdefault(grant.user_id.id, set()).update(
                grant.group_id.all_implied_ids._ids
            )
        return {user_id: frozenset(ids) for user_id, ids in scheduled.items()}

    @ormcache("self.id", cache="groups")
    def _get_duty_spec(self) -> dict[str, Any]:
        self.check_singleton()
        return {
            "groups": frozenset(self.group_ids._ids),
            "excluded": frozenset(self.excluded_group_ids._ids),
            "verbs": tuple((line.model_id.model, line.verb) for line in self.verb_ids),
        }

    @api.model
    def _verb_groups(
        self, verbs: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[frozenset[int], frozenset[int]], ...]:
        Access = self.env["ir.access"]
        model_verbs = self.env.registry.model_verbs
        pairs = []
        for model_name, verb_name in verbs:
            verb = model_verbs.get(model_name, {}).get(verb_name)
            if verb is None:
                continue
            pairs.append(
                (
                    Access._group_ids_granting(model_name, verb_name),
                    Access._group_ids_with_access(model_name, verb.requires),
                )
            )
        return tuple(pairs)

    @api.model
    def _holds(self, spec: dict[str, Any], user_id: int, held: frozenset) -> bool:
        if spec["excluded"] & held:
            return False
        return bool(spec["groups"] & held) or any(
            granting & held and requiring & held
            for granting, requiring in spec.get("verb_groups", ())
        )

    @api.model_create_multi
    def create(self, vals_list):
        functions = super().create(vals_list)
        self.env.registry.clear_cache("groups")
        return functions

    def write(self, vals):
        rules = self._rules() if DUTY_FIELDS & vals.keys() else None
        with _conflicts_created(rules, "duty_changed"):
            result = super().write(vals)
            self.env.registry.clear_cache("groups")
        return result

    def _rules(self):
        return self.env["ir.access.sod.rule"].search(
            Domain("function_a_id", "in", self.ids)
            | Domain("function_b_id", "in", self.ids)
        )


class IrAccessSodFunctionVerb(models.Model):
    _name = "ir.access.sod.function.verb"
    _description = "Business Duty Verb"

    function_id = fields.Many2one(
        comodel_name="ir.access.sod.function",
        index=True,
        required=True,
        ondelete="cascade",
    )
    model_id = fields.Many2one(
        comodel_name="ir.model",
        required=True,
        ondelete="cascade",
    )
    verb = fields.Char(required=True)

    @api.model_create_multi
    def create(self, vals_list):
        functions = self.env["ir.access.sod.function"].browse(
            {vals["function_id"] for vals in vals_list if vals.get("function_id")}
        )
        with _conflicts_created(functions._rules(), "duty_changed"):
            lines = super().create(vals_list)
            self.env.registry.clear_cache("groups")
        return lines

    def write(self, vals):
        functions = self.function_id | self.function_id.browse(vals.get("function_id"))
        with _conflicts_created(functions._rules(), "duty_changed"):
            result = super().write(vals)
            self.env.registry.clear_cache("groups")
        return result

    def unlink(self):
        result = super().unlink()
        self.env.registry.clear_cache("groups")
        return result

    @api.constrains("model_id", "verb")
    def _check_verb(self) -> None:
        for line in self:
            if line.verb not in self.env.registry.model_verbs.get(
                line.model_id.model, {}
            ):
                raise ValidationError(
                    self.env._(
                        "%(model)s declares no verb %(verb)s.",
                        model=line.model_id.model,
                        verb=line.verb,
                    )
                )


class IrAccessSodRule(models.Model):

    _name = "ir.access.sod.rule"
    _description = "Separation of Duties Rule"
    _order = "name"

    name = fields.Char(
        translate=True,
        required=True,
    )
    active = fields.Boolean(default=True)
    function_a_id = fields.Many2one(
        comodel_name="ir.access.sod.function",
        string="Duty",
        required=True,
        ondelete="restrict",
    )
    function_b_id = fields.Many2one(
        comodel_name="ir.access.sod.function",
        string="Conflicts With",
        required=True,
        ondelete="restrict",
    )
    action = fields.Selection(
        selection=[("warn", "Warn"), ("block", "Block")],
        default="block",
        required=True,
        help="Warn: the conflict is logged and let through. Block: the change that "
        "creates it is refused, unless the person holds a live exception for this "
        "rule.",
    )

    @api.model
    def _check_users(self, users, cause: str, refuse: bool = True) -> None:
        users = users.filtered(
            lambda user: not user.share and user.active and user.id != SUPERUSER_ID
        )
        if not users:
            return
        rule_ids = self._get_active_rule_ids()
        if not rule_ids:
            return
        logs: list[dict[str, Any]] = []
        refused = []
        Function = self.env["ir.access.sod.function"]
        scheduled = Function._scheduled_group_ids(users)
        for rule_id, function_a_id, function_b_id in rule_ids:
            holders = Function.browse(function_a_id)._get_holder_ids(users, scheduled)
            if not holders:
                continue
            holders &= Function.browse(function_b_id)._get_holder_ids(users, scheduled)
            rule = self.browse(rule_id)
            for user in users.browse(sorted(holders)):
                exception = self.env["ir.access.exception"]._find(user, "sod", rule)
                if exception:
                    exception._record_use(cause)
                    continue
                blocking = refuse and rule.action == "block" and self.env.registry.ready
                logs.append(rule._log_values(user, cause, blocking))
                if blocking:
                    refused.append((rule, user))
        if logs:
            self.env["ir.access.log"]._record(logs)
        if refused:
            rule, user = refused[0]
            _logger.warning(
                "Separation of duties rule %s refused %s: %s would hold both %s "
                "and %s.",
                rule.name,
                cause,
                user.login,
                rule.function_a_id.name,
                rule.function_b_id.name,
            )
            raise AccessError(
                self.env._(
                    "%(user)s would both %(duty)s and %(other)s, which rule "
                    "'%(rule)s' keeps apart. Ask for an exception, or remove one of "
                    "the two.",
                    user=user.name,
                    duty=rule.function_a_id.name,
                    other=rule.function_b_id.name,
                    rule=rule.name,
                )
            )

    @api.model
    @ormcache(cache="groups")
    def _get_active_rule_ids(self) -> tuple[tuple[int, int, int], ...]:
        if not self.env.ref("base.privilege_check_duties", raise_if_not_found=False):
            return ()
        rules = self.with_privilege(
            "base.privilege_check_duties",
            reason="every grant is checked against the separation of duties",
        ).search_fetch([], ["function_a_id", "function_b_id"])
        return tuple(
            (rule.id, rule.function_a_id.id, rule.function_b_id.id) for rule in rules
        )

    @api.model
    @ormcache(cache="groups")
    def _get_duty_verb_model_ids(self) -> frozenset[int]:
        if not self._get_active_rule_ids():
            return frozenset()
        lines = (
            self.env["ir.access.sod.function.verb"]
            .with_privilege(
                "base.privilege_check_duties",
                reason="every change of access is checked against the duties",
            )
            .search_fetch([], ["model_id"])
        )
        return frozenset(lines.model_id._ids)

    @api.model
    @ormcache(cache="groups")
    def _get_affecting_group_ids(self) -> frozenset[int]:
        rule_ids = self._get_active_rule_ids()
        if not rule_ids:
            return frozenset()
        Function = self.env["ir.access.sod.function"].with_privilege(
            "base.privilege_check_duties",
            reason="every grant is checked against the separation of duties",
        )
        held: set[int] = set()
        for _rule_id, *function_ids in rule_ids:
            for function in Function.browse(function_ids):
                spec = function._get_duty_spec()
                held |= spec["groups"] | spec.get("approver_group_ids", frozenset())
                for granting, requiring in function._verb_groups(spec["verbs"]):
                    held |= granting | requiring
        if not held:
            return frozenset()
        return frozenset(
            group.id
            for group in self.env["res.groups"].search_fetch([], ["all_implied_ids"])
            if held & ({group.id} | set(group.all_implied_ids._ids))
        )

    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        self.env.registry.clear_cache("groups")
        rules._log_new_conflicts(set(), "rule_changed")
        return rules

    def write(self, vals):
        rules = self if RULE_FIELDS & vals.keys() else None
        with _conflicts_created(rules, "rule_changed"):
            result = super().write(vals)
            self.env.registry.clear_cache("groups")
        return result

    def _standing_conflicts(self) -> set[tuple[int, int]]:
        users = self.env["res.users"].search(
            [("share", "=", False), ("id", "!=", SUPERUSER_ID)]
        )
        scheduled = self.env["ir.access.sod.function"]._scheduled_group_ids(users)
        return {
            (rule.id, user_id)
            for rule in self.filtered("active")
            for user_id in rule._get_conflicting_user_ids(users, scheduled)
        }

    def _log_new_conflicts(self, standing: set[tuple[int, int]], cause: str) -> None:
        Exception_ = self.env["ir.access.exception"]
        Users = self.env["res.users"]
        logs = [
            rule._log_values(user, cause, False)
            for rule_id, user_id in sorted(self._standing_conflicts() - standing)
            for rule, user in [(self.browse(rule_id), Users.browse(user_id))]
            if not Exception_._find(user, "sod", rule)
        ]
        if logs:
            self.env["ir.access.log"]._record(logs)

    def unlink(self):
        result = super().unlink()
        self.env.registry.clear_cache("groups")
        return result

    def _get_conflicting_user_ids(
        self, users, scheduled: dict[int, frozenset[int]] | None = None
    ) -> set[int]:
        self.check_singleton()
        if scheduled is None:
            scheduled = self.function_a_id._scheduled_group_ids(users)
        return self.function_a_id._get_holder_ids(
            users, scheduled
        ) & self.function_b_id._get_holder_ids(users, scheduled)

    def _log_values(self, user, cause: str, blocking: bool) -> dict[str, Any]:
        self.check_singleton()
        return {
            "event": "sod_refused" if blocking else "sod_conflict",
            "subject_user_id": user.id,
            "cause": cause,
            "cause_model": self._name,
            "cause_res_id": self.id,
            "reason": self.name,
        }

    def _get_conflicts(self) -> list[tuple[Any, Any]]:
        internal = self.env["res.users"].search(
            [("share", "=", False), ("id", "!=", SUPERUSER_ID)]
        )
        scheduled = self.env["ir.access.sod.function"]._scheduled_group_ids(internal)
        return [
            (rule, user)
            for rule in self
            for user in internal.browse(
                sorted(rule._get_conflicting_user_ids(internal, scheduled))
            )
        ]

    @api.model
    def action_view_conflicts(self) -> dict[str, Any]:
        Exception_ = self.env["ir.access.exception"]
        conflicts = self.env["ir.access.sod.conflict"].create(
            [
                {
                    "rule_id": rule.id,
                    "user_id": user.id,
                    "exception_id": Exception_._find(user, "sod", rule).id,
                }
                for rule, user in self.search([])._get_conflicts()
            ]
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Duties in Conflict"),
            "res_model": "ir.access.sod.conflict",
            "view_mode": "list",
            "domain": [("id", "in", conflicts.ids)],
        }


class ResUsersGrant(models.Model):
    _inherit = "res.users.grant"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    sod_rule_ids = fields.Many2many(
        comodel_name="ir.access.sod.rule",
        string="Duties in Conflict",
        compute="_compute_sod_rule_ids",
        search="_search_sod_rule_ids",
        help="The separation-of-duties rules whose two duties the person holds today.",
    )

    @api.depends("user_id")
    def _compute_sod_rule_ids(self) -> None:
        conflicts = self._sod_conflicts(self.user_id)
        for grant in self:
            grant.sod_rule_ids = conflicts.get(grant.user_id.id, [])

    def _search_sod_rule_ids(self, operator: str, value: Any) -> Domain:
        if operator == "in":
            wanted = {id_ for id_ in value if id_}
        elif operator == "not in" and not any(value):
            wanted = None
        else:
            return NotImplemented
        internal = self.env["res.users"].search(
            [("share", "=", False), ("id", "!=", SUPERUSER_ID)]
        )
        return Domain(
            "user_id",
            "in",
            sorted(
                user_id
                for user_id, rule_ids in self._sod_conflicts(internal).items()
                if wanted is None or wanted.intersection(rule_ids)
            ),
        )

    @api.model
    def _sod_conflicts(self, users) -> dict[int, list[int]]:
        users = users.filtered(
            lambda user: not user.share and user.active and user.id != SUPERUSER_ID
        )
        conflicts: dict[int, list[int]] = {}
        if not users:
            return conflicts
        Function = self.env["ir.access.sod.function"]
        scheduled = Function._scheduled_group_ids(users)
        for rule_id, function_a_id, function_b_id in self.env[
            "ir.access.sod.rule"
        ]._get_active_rule_ids():
            both = Function.browse(function_a_id)._get_holder_ids(
                users, scheduled
            ) & Function.browse(function_b_id)._get_holder_ids(users, scheduled)
            for user_id in both:
                conflicts.setdefault(user_id, []).append(rule_id)
        return conflicts

    def _on_grant_changed(self, event: str) -> None:
        super()._on_grant_changed(event)
        Rule = self.env["ir.access.sod.rule"]
        affecting = Rule._get_affecting_group_ids()
        if affecting and any(grant.group_id.id in affecting for grant in self):
            Rule._check_users(self.user_id, event, refuse=event in WIDENING_EVENTS)


class ResUsers(models.Model):
    _inherit = "res.users"

    def write(self, vals):
        archived = (
            self.with_context(active_test=False).filtered(lambda user: not user.active)
            if vals.get("active")
            else self.browse()
        )
        result = super().write(vals)
        if archived:
            self.env["ir.access.sod.rule"]._check_users(archived, "user_reactivated")
        return result


class IrAccessSodConflict(models.TransientModel):
    _name = "ir.access.sod.conflict"
    _description = "Duties in Conflict"
    _order = "rule_id, user_id"

    rule_id = fields.Many2one(
        comodel_name="ir.access.sod.rule",
        required=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Person",
        required=True,
        ondelete="cascade",
    )
    exception_id = fields.Many2one(
        comodel_name="ir.access.exception",
        ondelete="set null",
        help="The live exception that lets the person hold both duties, if any.",
    )
