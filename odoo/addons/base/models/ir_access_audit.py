import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Any, ClassVar, Self

from odoo import SUPERUSER_ID, api, fields, models
from odoo.api import MODULE_UNINSTALL_FLAG, ValuesType
from odoo.libs.debug_log import DebugLog

from .ir_access_log import kept_on_uninstall

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

AUDIT_LOG_EVENTS = [
    ("security_changed", "Security changed"),
    ("module_security_updated", "Security updated by a module"),
    ("denial", "Refused"),
]
# the transaction's module loads, per module and model: rows created,
# changed and removed, written to the log once the module's load commits
MODULE_CHANGES = "ir.access.log.module_changes"
# and the rows themselves, per module, each a change-set line: what the load
# changed, the diff its module_update change set holds
MODULE_LINES = "ir.access.log.module_lines"


def _loading_module(env: api.Environment) -> str | None:
    if module := env.context.get("install_module"):
        return module
    return None


def _plain(field: fields.Field, value: Any) -> Any:
    if field.type == "many2one":
        return value.id or False
    if field.relational:
        return sorted(value.ids)
    if isinstance(value, datetime | date):
        return fields.Datetime.to_string(value)
    return value


class IrAccessLog(models.Model):
    _inherit = "ir.access.log"

    event = fields.Selection(
        selection_add=AUDIT_LOG_EVENTS,
        ondelete=kept_on_uninstall(AUDIT_LOG_EVENTS),
    )
    values = fields.Json(
        readonly=True,
        help="What changed: each field's value before and after, or the rows a "
        "module's load created, changed and removed per model.",
    )

    @api.model
    def _record_denial(
        self, model_name: str, operation: str, ids: list[int], refusing: list[str]
    ) -> None:
        # the refused transaction rolls back: the row goes through a cursor of
        # its own, which a test's registry shares with the test's
        vals = {
            "event": "denial",
            "actor_id": self.env.uid,
            "subject_user_id": self.env.uid,
            "model_name": model_name,
            "operation": operation,
            "res_ids": ",".join(map(str, ids[:100])),
            "values": {"refused_by": refusing} if refusing else False,
        }
        _debug.logic("denial_logged", model=model_name, operation=operation)
        try:
            with self.env.registry.cursor() as cr:
                api.Environment(cr, SUPERUSER_ID, {})["ir.access.log"].create(vals)
        except Exception:
            _logger.warning(
                "Could not log the refusal of %s on %s %s to user %s",
                operation,
                model_name,
                ids[:10],
                self.env.uid,
                exc_info=True,
            )


class MixinAccessAudit(models.AbstractModel):
    _name = "mixin.access.audit"
    _description = "Security Row Whose Changes Are Logged"

    # the fields whose changes are logged; empty: every stored field written
    _access_audit_fields: ClassVar[tuple[str, ...]] = ()

    def _access_audit_names(self, names: Any) -> list[str]:
        audited = self._access_audit_fields
        return sorted(
            name
            for name in names
            if name in self._fields
            and self._fields[name].store
            and (not audited or name in audited)
            and name not in models.MAGIC_COLUMNS
        )

    def _access_audit_snapshot(self, names: list[str]) -> dict[int, dict[str, Any]]:
        # the log reads the rows as the policy reads its own data, whoever
        # writes them: a refused write must stay a refused write
        records = self.env["ir.access"]._access_evaluator(self._name).browse(self.ids)
        return {
            record.id: {
                name: _plain(self._fields[name], record[name]) for name in names
            }
            for record in records
        }

    def _access_audit_log(
        self,
        operation: str,
        before: dict[int, dict[str, Any]],
        after: dict[int, dict[str, Any]],
    ) -> None:
        if module := _loading_module(self.env):
            lines = [
                {
                    "res_model": self._name,
                    "res_id": id_,
                    "operation": operation,
                    "values_before": {
                        name: value
                        for name, value in old.items()
                        if value != after[id_].get(name)
                    },
                    "values_after": {
                        name: value
                        for name, value in after[id_].items()
                        if value != old.get(name)
                    },
                }
                for id_, old in before.items()
                if old != after.get(id_)
            ]
            self._access_audit_count_module(module, operation, len(lines), lines)
            return
        rows = []
        for id_ in sorted(before.keys() | after.keys()):
            old, new = before.get(id_, {}), after.get(id_, {})
            changed = {
                name: [old.get(name), new.get(name)]
                for name in sorted(old.keys() | new.keys())
                if old.get(name) != new.get(name)
            }
            if operation == "write" and not changed:
                continue
            rows.append(
                {
                    "event": "security_changed",
                    "model_name": self._name,
                    "operation": operation,
                    "res_ids": str(id_),
                    "values": changed or None,
                }
            )
        _debug.logic(
            "security_changed", model=self._name, operation=operation, rows=len(rows)
        )
        self.env["ir.access.log"]._record(rows)

    def _access_audit_count_module(
        self,
        module: str,
        operation: str,
        count: int,
        lines: list[dict[str, Any]],
    ) -> None:
        if not count:
            return
        precommit = self.env.cr.precommit
        if MODULE_CHANGES not in precommit.data:
            precommit.add(self._access_audit_flush_modules)
        counts = precommit.data.setdefault_dict(MODULE_CHANGES).setdefault_dict(
            (module, self._name)
        )
        counts[operation] = counts.get(operation, 0) + count
        precommit.data.setdefault_dict(MODULE_LINES).setdefault_list(module).extend(
            lines
        )

    def _access_audit_flush_modules(self) -> None:
        changes = self.env.cr.precommit.data.pop(MODULE_CHANGES, None)
        lines = self.env.cr.precommit.data.pop(MODULE_LINES, None) or {}
        if not changes:
            return
        by_module: defaultdict[str, dict[str, dict[str, int]]] = defaultdict(dict)
        for (module, model_name), counts in changes.items():
            by_module[module][model_name] = dict(counts)
        _debug.logic("module_security_updated", modules=sorted(by_module))
        self.env["ir.access.log"]._record(
            [
                {
                    "event": "module_security_updated",
                    "cause": "module",
                    "reason": module,
                    "values": models_changes,
                    **self._access_audit_module_record(module, lines.get(module, [])),
                }
                for module, models_changes in sorted(by_module.items())
            ]
        )

    def _access_audit_module_record(
        self, module: str, lines: list[dict[str, Any]]
    ) -> dict[str, Any]:
        # what the module's log row links beside its summary
        return {}

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        records = super().create(vals_list)
        if module := _loading_module(self.env):
            names = self._access_audit_names(
                {name for vals in vals_list for name in vals}
            )
            after = records._access_audit_snapshot(names)
            records._access_audit_count_module(
                module,
                "create",
                len(records),
                [
                    {
                        "res_model": self._name,
                        "res_id": record.id,
                        "operation": "create",
                        "values_after": after[record.id],
                    }
                    for record in records
                ],
            )
            return records
        names = self._access_audit_names({name for vals in vals_list for name in vals})
        records._access_audit_log("create", {}, records._access_audit_snapshot(names))
        return records

    def write(self, vals: ValuesType) -> bool:
        names = self._access_audit_names(vals)
        if not names or not self:
            return super().write(vals)
        before = self._access_audit_snapshot(names)
        result = super().write(vals)
        self._access_audit_log("write", before, self._access_audit_snapshot(names))
        return result

    def unlink(self) -> bool:
        if self.env.context.get(MODULE_UNINSTALL_FLAG):
            # a module's load removing the rows it no longer ships
            data = self.env["ir.model.data"].search_fetch(
                [("model", "=", self._name), ("res_id", "in", self.ids)],
                ["module", "res_id"],
            )
            before = self._access_audit_snapshot(
                self._access_audit_names(self._access_audit_fields or ("name",))
            )
            for module, rows in data.grouped("module").items():
                self._access_audit_count_module(
                    module,
                    "unlink",
                    len(rows),
                    [
                        {
                            "res_model": self._name,
                            "res_id": row.res_id,
                            "operation": "unlink",
                            "values_before": before.get(row.res_id, {}),
                        }
                        for row in rows
                    ],
                )
            return super().unlink()
        before = self._access_audit_snapshot(
            self._access_audit_names(self._access_audit_fields or ("name",))
        )
        result = super().unlink()
        self._access_audit_log("unlink", before, {})
        return result


class IrAccess(models.Model):
    _name = "ir.access"
    _inherit = ["ir.access", "mixin.access.audit"]
    _access_audit_fields = (
        "active",
        "anchor",
        "class_id",
        "domain",
        "exempt_group_ids",
        "group_id",
        "guard_scope",
        "kind",
        "model_id",
        "name",
        "operation",
        "predicate_args",
        "predicate_id",
        "reach",
        "verbs",
    )

    def _log_denial(self, model_name: str, operation: str, records: Any) -> None:
        # a refused change of a model whose changes are security: someone tried
        if operation == "read" or not self.env.registry[model_name]._access_audit:
            return
        refusing = (
            [row.name for row in self._get_failed_accesses(records, operation)]
            if records
            else []
        )
        self.env["ir.access.log"]._record_denial(
            model_name, operation, list(records._ids) if records else [], refusing
        )

    def _prepare_model_access_error(self, model_name: str, operation: str) -> Any:
        self._log_denial(model_name, operation, None)
        return super()._prepare_model_access_error(model_name, operation)

    def _prepare_record_access_error(self, records: Any, operation: str) -> Any:
        self._log_denial(records._name, operation, records)
        return super()._prepare_record_access_error(records, operation)


class IrAccessPredicate(models.Model):
    _name = "ir.access.predicate"
    _inherit = ["ir.access.predicate", "mixin.access.audit"]


class IrAccessClass(models.Model):
    _name = "ir.access.class"
    _inherit = ["ir.access.class", "mixin.access.audit"]


class IrAccessSodRule(models.Model):
    _name = "ir.access.sod.rule"
    _inherit = ["ir.access.sod.rule", "mixin.access.audit"]


class ResGroups(models.Model):
    _name = "res.groups"
    _inherit = ["res.groups", "mixin.access.audit"]
    _access_audit_fields = (
        "admin_group_id",
        "audit_privilege",
        "implied_ids",
        "is_privilege",
        "name",
    )
