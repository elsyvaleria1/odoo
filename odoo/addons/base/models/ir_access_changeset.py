import contextlib
import contextvars
import json
from collections.abc import Iterator
from typing import Any, ClassVar, Self

from odoo import api, fields, models
from odoo.api import MODULE_UNINSTALL_FLAG, ValuesType
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads
from odoo.service.model import called_model
from odoo.tools import frozendict

from .ir_access_audit import _plain
from .ir_access_log import kept_on_uninstall
from .res_users_grant import _marked

_debug = DebugLog(__name__)

CHANGESET_LOG_EVENTS = [
    ("changeset_proposed", "Change set proposed"),
    ("changeset_activated", "Change set activated"),
    ("changeset_cancelled", "Change set cancelled"),
]
POLICY_VERSION = "base.access_policy_version"
IMPACT_OPERATIONS = ("read", "write", "create", "unlink")
_APPLYING: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "ir_access_changeset_applying", default=False
)
_MOVING: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "ir_access_changeset_moving", default=False
)
_NESTED: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "ir_access_changeset_nested", default=False
)
COMODEL_WRITING_COMMANDS = frozenset(
    {fields.Command.CREATE, fields.Command.UPDATE, fields.Command.DELETE}
)
LIFECYCLE_FIELDS = frozenset(
    {
        "author_id",
        "state",
        "cause",
        "module",
        "rollback_of_id",
        "impact",
        "policy_version",
        "activated_at",
        "activated_by_id",
    }
)


@contextlib.contextmanager
def applying() -> Iterator[None]:
    token = _APPLYING.set(True)
    try:
        yield
    finally:
        _APPLYING.reset(token)


STAGING_ENTRIES = frozenset(
    {
        "ir.access",
        "ir.access.class",
        "ir.access.predicate",
        "ir.access.sod.rule",
        "res.groups",
        "res.users",
        "res.users.eligibility",
        "ir.model",
        "base_import.import",
    }
)


def staging(env: api.Environment) -> bool:
    return not (
        env.su
        or _APPLYING.get()
        or env.context.get("install_module")
        or env.context.get(MODULE_UNINSTALL_FLAG)
        or (called_model() not in STAGING_ENTRIES and not _NESTED.get())
    )


@contextlib.contextmanager
def nesting() -> Iterator[None]:
    token = _NESTED.set(True)
    try:
        yield
    finally:
        _NESTED.reset(token)


class _Discard(Exception):
    pass


class Base(models.AbstractModel):
    _inherit = "base"

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if not self._access_staged_commands(vals_list):
            return super().create(vals_list)
        with nesting():
            return super().create(vals_list)

    def write(self, vals: ValuesType) -> bool:
        if not self._access_staged_commands([vals]):
            return super().write(vals)
        with nesting():
            return super().write(vals)

    def _access_staged_commands(self, vals_list: list[ValuesType]) -> bool:
        if _NESTED.get() or called_model() is None:
            return False
        for vals in vals_list:
            for name, value in vals.items():
                field = self._fields.get(name)
                if (
                    field is not None
                    and field.type in ("one2many", "many2many", "one2one")
                    and isinstance(value, list | tuple)
                    and issubclass(self.pool[field.comodel_name], MixinAccessStaged)
                    and any(
                        isinstance(command, list | tuple)
                        and command
                        and command[0] in COMODEL_WRITING_COMMANDS
                        for command in value
                    )
                ):
                    _debug.logic("nested_commands_staged", model=self._name, field=name)
                    return True
        return False


class IrAccessLog(models.Model):
    _inherit = "ir.access.log"

    event = fields.Selection(
        selection_add=CHANGESET_LOG_EVENTS,
        ondelete=kept_on_uninstall(CHANGESET_LOG_EVENTS),
    )
    changeset_id = fields.Many2one(
        comodel_name="ir.access.changeset",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
    )


class MixinAccessAudit(models.AbstractModel):
    _inherit = "mixin.access.audit"

    def _access_audit_module_record(
        self, module: str, lines: list[dict[str, Any]]
    ) -> dict[str, Any]:
        values = super()._access_audit_module_record(module, lines)
        if not lines:
            return values
        changeset = self.env["ir.access.changeset"]._record_module_update(module, lines)
        return {**values, "changeset_id": changeset.id}


class MixinAccessStaged(models.AbstractModel):
    _name = "mixin.access.staged"
    _description = "Security Row Changed Through a Change Set"

    _access_staged_fields: ClassVar[tuple[str, ...]] = ()
    _access_staged_create: ClassVar[tuple[str, Any, Any] | None] = None
    _access_staged_create_deferred: ClassVar[bool] = False

    def _access_staged_names(self, names: Any) -> list[str]:
        staged = self._access_staged_fields
        return sorted(
            name
            for name in names
            if name in self._fields
            and self._fields[name].store
            and (not staged or name in staged)
            and name not in models.MAGIC_COLUMNS
        )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if not staging(self.env):
            return super().create(vals_list)
        held = self._access_staged_create
        if held is None:
            if self._access_staged_create_deferred:
                return self._access_staged_create_then_write(vals_list)
            return super().create(vals_list)
        field, waiting, _live = held
        records = super().create([{**vals, field: waiting} for vals in vals_list])
        changeset = self.env["ir.access.changeset"]._open_for_author()
        changeset._stage(
            [
                {
                    "res_model": self._name,
                    "res_id": record.id,
                    "operation": "create",
                    "values_after": json_loads(json.dumps(vals, default=str)),
                }
                for record, vals in zip(records, vals_list, strict=True)
            ]
        )
        return records

    def _access_staged_create_then_write(self, vals_list: list[ValuesType]) -> Self:
        deferred = [
            {
                name: vals[name]
                for name in self._access_staged_names(vals)
                if not self._fields[name].required
            }
            for vals in vals_list
        ]
        records = super().create(
            [
                {name: value for name, value in vals.items() if name not in later}
                for vals, later in zip(vals_list, deferred, strict=True)
            ]
        )
        for record, later in zip(records, deferred, strict=True):
            if later:
                record._access_stage_write(later)
        return records

    def _access_stage_write(self, staged: dict[str, Any]) -> None:
        names = sorted(staged)
        before = (
            self.env["ir.access"]
            ._access_evaluator(self._name)
            .browse(self.ids)
            ._access_staged_snapshot(names)
        )
        self.env["ir.access.changeset"]._open_for_author()._stage(
            [
                {
                    "res_model": self._name,
                    "res_id": id_,
                    "operation": "write",
                    "values_before": before[id_],
                    "values_after": json_loads(json.dumps(staged, default=str)),
                }
                for id_ in self.ids
            ]
        )
        _debug.logic("write_staged", model=self._name, ids=self.ids, fields=names)

    def write(self, vals: ValuesType) -> bool:
        names = self._access_staged_names(vals) if staging(self.env) else []
        if not names or not self:
            return super().write(vals)
        staged = {name: vals[name] for name in names}
        self._access_stage_write(staged)
        rest = {name: value for name, value in vals.items() if name not in staged}
        return super().write(rest) if rest else True

    def unlink(self) -> bool:
        if not staging(self.env) or not self:
            return super().unlink()
        names = self._access_staged_names(self._access_staged_fields or ("name",))
        before = (
            self.env["ir.access"]
            ._access_evaluator(self._name)
            .browse(self.ids)
            ._access_staged_snapshot(names)
        )
        self.env["ir.access.changeset"]._open_for_author()._stage(
            [
                {
                    "res_model": self._name,
                    "res_id": id_,
                    "operation": "unlink",
                    "values_before": before[id_],
                }
                for id_ in self.ids
            ]
        )
        _debug.logic("unlink_staged", model=self._name, ids=self.ids)
        return True

    def _access_staged_snapshot(self, names: list[str]) -> dict[int, dict[str, Any]]:
        return {
            record.id: {
                name: _plain(self._fields[name], record[name]) for name in names
            }
            for record in self.with_context(active_test=False)
        }


class IrAccess(models.Model):
    _name = "ir.access"
    _inherit = ["ir.access", "mixin.access.staged"]
    _access_staged_fields = (
        "active",
        "anchor",
        "class_id",
        "domain",
        "exempt_group_ids",
        "group_id",
        "guard_scope",
        "kind",
        "model_id",
        "operation",
        "predicate_args",
        "predicate_id",
        "reach",
        "verbs",
    )
    _access_staged_create = ("active", False, True)


class IrAccessPredicate(models.Model):
    _name = "ir.access.predicate"
    _inherit = ["ir.access.predicate", "mixin.access.staged"]
    _access_staged_fields = ("template", "method", "model_id")


class IrAccessClass(models.Model):
    _name = "ir.access.class"
    _inherit = ["ir.access.class", "mixin.access.staged"]
    _access_staged_create = ("active", False, True)


class IrAccessSodRule(models.Model):
    _name = "ir.access.sod.rule"
    _inherit = ["ir.access.sod.rule", "mixin.access.staged"]
    _access_staged_create = ("active", False, True)


class ResGroups(models.Model):
    _name = "res.groups"
    _inherit = ["res.groups", "mixin.access.staged"]
    _access_staged_fields = (
        "admin_group_id",
        "audit_privilege",
        "implied_ids",
        "is_break_glass",
        "is_privilege",
    )
    _access_staged_create_deferred = True

    def unlink(self) -> bool:
        with applying():
            return super().unlink()


class ResUsersEligibility(models.Model):
    _name = "res.users.eligibility"
    _inherit = ["res.users.eligibility", "mixin.access.staged"]
    _access_staged_fields = ("company_ids", "justification_required", "max_hours")
    _access_staged_create = ("state", "staged", "active")

    state = fields.Selection(
        selection_add=[("staged", "Waiting for its change set")],
        ondelete={"staged": "cascade"},
    )


def _named_ids(value: Any) -> set[int]:
    ids: set[int] = set()
    for item in value or ():
        if isinstance(item, int):
            ids.add(item)
        elif item and item[0] == fields.Command.SET:
            ids.update(item[2])
        elif len(item) > 1 and isinstance(item[1], int):
            ids.add(item[1])
    return ids


def _shape(impact: dict[str, Any]) -> set[tuple]:
    return {
        (user_id, model, operation, gained > 0, lost > 0, before < 0, after < 0)
        for user_id, by_model in impact.items()
        if user_id
        for model, by_operation in by_model.items()
        for operation, (before, after, gained, lost) in by_operation.items()
    }


def _widens_eligibility(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if after.get("max_hours", 0) > before.get("max_hours", 0):
        return True
    if before.get("justification_required") and not after.get(
        "justification_required", True
    ):
        return True
    if "company_ids" in after:
        was, now = (
            _named_ids(before.get("company_ids")),
            _named_ids(after["company_ids"]),
        )
        return bool(was) and not (now and now <= was)
    return False


def _widened(impact: dict[str, Any]) -> set[int]:
    return {
        int(user_id)
        for user_id, by_model in impact.items()
        if user_id
        for by_operation in by_model.values()
        for before, after, gained, _lost in by_operation.values()
        if gained > 0 or (before < 0 <= after)
    }


class IrAccessChangeset(models.Model):
    _name = "ir.access.changeset"
    _description = "Security Change Set"
    _order = "id desc"
    _access_audit = True
    _access_anchors = frozendict({"owner": "author_id"})
    _access_verbs = {
        "activate": models.Verb(requires="read", methods=("action_activate",)),
    }

    name = fields.Char(required=True)
    author_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.uid,
        index=True,
        readonly=True,
        required=True,
        ondelete="restrict",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("proposed", "Proposed"),
            ("active", "Active"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        index=True,
        readonly=True,
        required=True,
    )
    cause = fields.Selection(
        selection=[
            ("manual", "Edited by a person"),
            ("rollback", "Rollback"),
            ("module_update", "Module update"),
        ],
        default="manual",
        readonly=True,
        required=True,
    )
    module = fields.Char(
        readonly=True,
        help="The module whose install, update or removal made the change set.",
    )
    rollback_of_id = fields.Many2one(
        comodel_name="ir.access.changeset",
        readonly=True,
        ondelete="restrict",
    )
    line_ids = fields.One2many(
        comodel_name="ir.access.changeset.line",
        inverse_name="changeset_id",
        string="Changes",
    )
    impact = fields.Json(readonly=True)
    impact_summary = fields.Text(
        compute="_compute_impact_summary",
        help="Per person, model and operation, how many records they reach "
        "before and after the change set.",
    )
    policy_version = fields.Integer(readonly=True)
    activated_at = fields.Datetime(readonly=True)
    activated_by_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        ondelete="set null",
    )

    @api.depends("impact")
    def _compute_impact_summary(self) -> None:
        users = self.env["res.users"]
        for changeset in self:
            impact = changeset.impact or {}
            lines = [
                f"{users.browse(int(user_id)).name} / {model} / {operation}: "
                f"{before} -> {after} (+{gained} -{lost})"
                for user_id, by_model in sorted(impact.items())
                if user_id
                for model, by_operation in sorted(by_model.items())
                for operation, (before, after, gained, lost) in sorted(
                    by_operation.items()
                )
            ]
            changeset.impact_summary = "\n".join(lines) or (
                self.env._("Nobody's reach changes.") if changeset.impact else False
            )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if not (self.env.su or _MOVING.get()):
            fresh = {"author_id": self.env.uid, "state": "draft", "cause": "manual"}
            for vals in vals_list:
                if any(
                    vals[name] != fresh.get(name, False)
                    for name in LIFECYCLE_FIELDS & vals.keys()
                ):
                    raise UserError(
                        self.env._(
                            "A change set is created a draft of the person staging it."
                        )
                    )
        return super().create(vals_list)

    def write(self, vals: ValuesType) -> bool:
        if LIFECYCLE_FIELDS & vals.keys() and not (self.env.su or _MOVING.get()):
            raise UserError(
                self.env._(
                    "A change set is proposed, activated or cancelled; who staged "
                    "it and what it does are not written by hand."
                )
            )
        return super().write(vals)

    @api.model
    def _open_for_author(self) -> Self:
        changesets = self.env["ir.access"]._access_evaluator(self._name)
        changeset = changesets.search(
            [("author_id", "=", self.env.uid), ("state", "=", "draft")], limit=1
        )
        if not changeset:
            changeset = changesets.create(
                {
                    "name": self.env._(
                        "Changes by %(user)s, %(date)s",
                        user=self.env.user.name,
                        date=fields.Date.context_today(self),
                    ),
                    "author_id": self.env.uid,
                }
            )
        return changeset

    def _stage(self, lines: list[ValuesType]) -> None:
        self.check_singleton()
        self.env["ir.access"]._access_evaluator("ir.access.changeset.line").create(
            [{"changeset_id": self.id, **line} for line in lines]
        )
        with _marked(_MOVING):
            self.impact = False

    def action_propose(self) -> None:
        for changeset in self:
            if changeset.state != "draft":
                raise UserError(self.env._("Only a draft change set is proposed."))
            with _marked(_MOVING):
                changeset._compute_impact()
                changeset.state = "proposed"
            changeset._log("changeset_proposed")

    def action_cancel(self) -> bool:
        for changeset in self.filtered(lambda c: c.state in ("draft", "proposed")):
            with applying():
                changeset.line_ids.filtered(
                    lambda line: line.operation == "create"
                )._discard_created()
            with _marked(_MOVING):
                changeset.state = "cancelled"
            changeset._log("changeset_cancelled")
        return True

    def action_activate(self) -> bool:
        self.check_singleton()
        if self.state not in ("draft", "proposed"):
            raise UserError(self.env._("This change set was activated or cancelled."))
        if stale := self.line_ids.filtered(lambda line: line._is_stale()):
            raise UserError(
                self.env._(
                    "These rows changed since they were staged: %s. Cancel the "
                    "change set and stage the changes again.",
                    ", ".join(stale.mapped("record_name")),
                )
            )
        impact = self._check_review()
        with applying():
            for line in self.line_ids:
                line._apply()
        parameters = self.env["ir.access"]._access_evaluator("ir.config_parameter")
        version = int(parameters.get_param(POLICY_VERSION, "0")) + 1
        parameters.set_param(POLICY_VERSION, str(version))
        self.env["ir.access"]._access_evaluator(self._name).browse(self.id).write(
            {
                "state": "active",
                "impact": impact,
                "policy_version": version,
                "activated_at": self.env.cr.now(),
                "activated_by_id": self.env.uid,
            }
        )
        self._log("changeset_activated")
        _debug.lifecycle(
            "activated", changeset=self.id, lines=len(self.line_ids), version=version
        )
        return True

    def action_rollback(self) -> dict[str, Any]:
        self.check_singleton()
        if self.state != "active":
            raise UserError(self.env._("Only an active change set is rolled back."))
        with _marked(_MOVING):
            inverse = self.create(
                {
                    "name": self.env._("Rollback of %s", self.name),
                    "cause": "rollback",
                    "rollback_of_id": self.id,
                }
            )
        inverse._stage([line._inverse_values() for line in self.line_ids])
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": inverse.id,
            "view_mode": "form",
        }

    def _check_review(self) -> dict[str, Any]:
        impact = self._impact()
        if self.state == "proposed" and _shape(impact) != _shape(self.impact or {}):
            raise UserError(
                self.env._(
                    "Who reaches what has changed since this change set was "
                    "proposed: propose it again, so that what is activated is "
                    "what was reviewed."
                )
            )
        widened = _widened(impact) | self.line_ids._eligible_user_ids()
        if widened and self.author_id == self.env.user:
            raise UserError(
                self.env._(
                    "This change set widens what %(count)s people reach "
                    "(%(names)s): another access administrator activates it.",
                    count=len(widened),
                    names=", ".join(
                        self.env["res.users"].browse(sorted(widened)).mapped("name")
                    ),
                )
            )
        return impact

    def _compute_impact(self) -> None:
        self.impact = self._impact()

    def _impact(self) -> dict[str, Any]:
        self.check_singleton()
        models_, groups = self.line_ids._affected()
        users = self.env["res.users"].search(
            Domain("active", "=", True)
            & (
                Domain.TRUE
                if groups is None
                else Domain("all_group_ids", "in", sorted(groups))
            )
        )
        before = self._reach_counts(users, models_)
        try:
            with self.env.cr.savepoint():
                with applying():
                    for line in self.line_ids:
                        line._apply()
                self.env.flush_all()
                after = self._reach_counts(users, models_)
                raise _Discard
        except _Discard:
            pass
        finally:
            self.env["ir.access"]._clear_access_caches()
        impact: dict[str, dict[str, dict[str, list[int]]]] = {}
        for key, reached in after.items():
            was = before.get(key)
            if was == reached:
                continue
            user_id, model_name, operation = key
            impact.setdefault(str(user_id), {}).setdefault(model_name, {})[
                operation
            ] = [
                -1 if was is None else len(was),
                -1 if reached is None else len(reached),
                len((reached or set()) - (was or set())),
                len((was or set()) - (reached or set())),
            ]
        return impact or {"": {}}

    def _reach_counts(
        self, users: models.BaseModel, model_names: set[str]
    ) -> dict[tuple, frozenset[int] | None]:
        policy = self.env.registry.access_policy
        counts = {}
        for user in users:
            env = self.env(
                user=user, context={"allowed_company_ids": user.company_ids.ids}
            )
            for model_name in model_names:
                evaluator = self.env["ir.access"]._access_evaluator(model_name)
                for operation in IMPACT_OPERATIONS:
                    if not policy.model_allowed(env, model_name, operation):
                        counts[user.id, model_name, operation] = None
                        continue
                    counts[user.id, model_name, operation] = frozenset(
                        evaluator.search(
                            policy.record_domain(env, model_name, operation)
                        )._ids
                    )
        return counts

    @api.model
    def _record_module_update(self, module: str, lines: list[ValuesType]) -> Self:
        Changesets = self.env["ir.access"]._access_evaluator(self._name)
        Parameters = self.env["ir.access"]._access_evaluator("ir.config_parameter")
        version = int(Parameters.get_param(POLICY_VERSION, "0")) + 1
        Parameters.set_param(POLICY_VERSION, str(version))
        now = self.env.cr.now()
        changeset = Changesets.create(
            {
                "name": self.env._("Module %(module)s", module=module),
                "cause": "module_update",
                "module": module,
                "state": "active",
                "policy_version": version,
                "activated_at": now,
                "activated_by_id": self.env.uid,
                "line_ids": [
                    fields.Command.create(
                        {
                            **line,
                            "values_applied": line.get("values_after") or False,
                        }
                    )
                    for line in lines
                ],
            }
        )
        _debug.lifecycle(
            "module_update", module=module, lines=len(lines), version=version
        )
        return self.browse(changeset.id)

    def _log(self, event: str) -> None:
        self.env["ir.access.log"]._record(
            [
                {
                    "event": event,
                    "changeset_id": changeset.id,
                    "count": len(changeset.line_ids),
                    "reason": changeset.name,
                }
                for changeset in self
            ]
        )


class IrAccessChangesetLine(models.Model):
    _name = "ir.access.changeset.line"
    _description = "Security Change"
    _order = "changeset_id, id"
    _access_anchors = frozendict({"owner": "changeset_id.author_id"})

    changeset_id = fields.Many2one(
        comodel_name="ir.access.changeset",
        index=True,
        required=True,
        ondelete="cascade",
    )
    res_model = fields.Char(
        string="Model",
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Record",
    )
    record_name = fields.Char(compute="_compute_record_name")
    operation = fields.Selection(
        selection=[("create", "Create"), ("write", "Change"), ("unlink", "Delete")],
        required=True,
    )
    values_before = fields.Json(string="Before")
    values_after = fields.Json(string="After")
    values_applied = fields.Json(
        help="The staged fields as they read once the line was applied: what a "
        "rollback restores them from.",
    )

    @api.depends("res_model", "res_id")
    def _compute_record_name(self) -> None:
        for line in self:
            record = (
                self.env["ir.access"]
                ._access_evaluator(line.res_model)
                .browse(line.res_id)
                .exists()
            )
            line.record_name = (
                f"{line.res_model} {record.display_name}"
                if record
                else f"{line.res_model} #{line.res_id}"
            )

    def _record(self) -> models.BaseModel:
        return (
            self.env[self.res_model].with_context(active_test=False).browse(self.res_id)
        )

    def _is_stale(self) -> bool:
        if self.operation == "create" or not self.values_before:
            return False
        record = (
            self.env["ir.access"]._access_evaluator(self.res_model).browse(self.res_id)
        )
        if not record.exists():
            return True
        now = record._access_staged_snapshot(sorted(self.values_before))[record.id]
        return now != self.values_before

    def _apply(self) -> None:
        record = (
            self.env["ir.access"]._access_evaluator(self.res_model).browse(self.res_id)
        )
        if self.operation == "write":
            values = self._write_values()
            record.write(values)
            evaluator = self.env["ir.access"]._access_evaluator
            evaluator(self._name).browse(self.id).values_applied = (
                evaluator(self.res_model)
                .browse(self.res_id)
                ._access_staged_snapshot(sorted(values))[self.res_id]
            )
        elif self.operation == "unlink":
            record.unlink()
        else:
            field, _waiting, live = type(record)._access_staged_create
            record.write({field: live})

    def _write_values(self) -> dict[str, Any]:
        values = {}
        for name, value in (self.values_after or {}).items():
            field = self.env[self.res_model]._fields[name]
            if (
                field.relational
                and field.type != "many2one"
                and isinstance(value, list)
                and all(isinstance(item, int) for item in value)
            ):
                value = [fields.Command.set(value)]
            values[name] = value
        return values

    def _discard_created(self) -> None:
        for line in self.filtered(
            lambda line: line.res_model == "res.users.eligibility"
        ):
            line._record().exists().write({"state": "revoked"})

    def _inverse_values(self) -> ValuesType:
        self.check_singleton()
        if self.operation == "write":
            return {
                "res_model": self.res_model,
                "res_id": self.res_id,
                "operation": "write",
                "values_before": self.values_applied,
                "values_after": self.values_before,
            }
        if self.operation == "create":
            return {
                "res_model": self.res_model,
                "res_id": self.res_id,
                "operation": "unlink",
            }
        raise UserError(
            self.env._(
                "A deleted row cannot be brought back by a rollback: create it "
                "again (%s).",
                self.record_name,
            )
        )

    def _eligible_user_ids(self) -> set[int]:
        return {
            line._record().user_id.id
            for line in self
            if line.res_model == "res.users.eligibility"
            and (
                line.operation == "create"
                or (
                    line.operation == "write"
                    and _widens_eligibility(
                        line.values_before or {}, line.values_after or {}
                    )
                )
            )
        }

    def _affected(self) -> tuple[set[str], set[int] | None]:
        model_names: set[str] = set()
        named: set[int] = set()
        implied: set[int] = set()
        evaluator = self.env["ir.access"]._access_evaluator
        rows = (
            evaluator("ir.access")
            .browse([line.res_id for line in self if line.res_model == "ir.access"])
            .exists()
        )
        if predicate_ids := [
            line.res_id for line in self if line.res_model == "ir.access.predicate"
        ]:
            rows |= evaluator("ir.access").search(
                Domain("predicate_id", "in", predicate_ids)
            )
        groups = evaluator("res.groups").browse(
            [line.res_id for line in self if line.res_model == "res.groups"]
        )
        model_names.update(rows.model_id.mapped("model"))
        named.update((rows.group_id | groups).ids)
        everyone = any(
            row.kind == "guard" and row.guard_scope == "everyone" for row in rows
        )
        for line in self:
            for values in (line.values_before or {}, line.values_after or {}):
                if line.res_model == "ir.access":
                    if isinstance(values.get("group_id"), int):
                        named.add(values["group_id"])
                    everyone |= values.get("guard_scope") == "everyone"
                if line.res_model == "res.groups":
                    implied.update(_named_ids(values.get("implied_ids")))
        group_ids = (
            None
            if everyone
            else set(
                evaluator("res.groups").browse(sorted(named)).all_implied_by_ids.ids
            )
        )
        if implied:
            implied_groups = evaluator("res.groups").browse(sorted(implied)).exists()
            model_names.update(
                evaluator("ir.access")
                .search(
                    Domain("group_id", "in", implied_groups.all_implied_ids.ids)
                    & Domain("model_id", "!=", False)
                )
                .model_id.mapped("model")
            )
        _debug.logic(
            "affected",
            models=sorted(model_names),
            groups=None if group_ids is None else len(group_ids),
        )
        return {name for name in model_names if name in self.env}, group_ids
