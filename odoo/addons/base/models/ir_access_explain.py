from typing import Any

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

from .ir_access import AccessInfo, covers
from .ir_access_log import kept_on_uninstall

_debug = DebugLog(__name__)

EXPLAIN_LOG_EVENTS = [("explained_other", "Someone's access explained")]


class IrAccessLog(models.Model):
    _inherit = "ir.access.log"

    event = fields.Selection(
        selection_add=EXPLAIN_LOG_EVENTS,
        ondelete=kept_on_uninstall(EXPLAIN_LOG_EVENTS),
    )


class IrAccess(models.Model):
    _inherit = "ir.access"

    @api.model
    def _explain_record(self, record: models.BaseModel, operation: str) -> dict:
        record.check_singleton()
        env = self.env
        model_name = record._name
        self._check_operation(model_name, operation)
        target = env[model_name].browse(record.id)
        scopes = env.user._get_group_scopes()
        domain_of = self._row_domains()
        model = self._access_evaluator(model_name)

        def admits(domain: Domain) -> bool:
            return bool(model.search_count(domain & Domain("id", "=", record.id)))

        grants = self._explain_grants()
        permissions, guards = [], []
        for row in self._get_all_access().get(model_name, ()):
            if not covers(row, operation):
                continue
            binds_everyone = row.kind == "guard" and row.guard_scope == "everyone"
            held = row.group_id in scopes
            if not binds_everyone and not held:
                continue
            domain = domain_of(model_name, row)
            if not binds_everyone:
                domain = self._scoped(model_name, row, domain, scopes[row.group_id])
            entry = self._explain_row(model_name, row) | {"admits": admits(domain)}
            if row.kind == "permission":
                entry["held_through"] = grants.get(row.group_id, [])
                permissions.append(entry)
            else:
                guards.append(entry)
        own = target._access_guard(operation)
        own_guard = (
            None
            if own.is_true()
            else {
                "name": env._("the condition of %(model)s itself", model=model_name),
                "admits": admits(own),
            }
        )
        explanation = {
            "user": env.user.id,
            "model": model_name,
            "record": record.id,
            "operation": operation,
            "allowed": target.has_access(operation),
            "model_allowed": env.registry.access_policy.model_allowed(
                env, model_name, operation
            ),
            "permissions": permissions,
            "guards": guards,
            "own_guard": own_guard,
            "parents": self._explain_parents(target, operation),
            "requires": None,
            "obligations": [],
            "graph": [],
            "fields": self._explain_fields(target),
        }
        verb = env.registry.model_verbs.get(model_name, {}).get(operation)
        if verb is not None:
            explanation["requires"] = self._explain_record(record, verb.requires)
            explanation["obligations"] = env[
                "ir.access.obligation"
            ]._explain_obligations(target, operation)
        if isinstance(target, env.registry["mixin.access.graph"]):
            explanation["graph"] = [
                {
                    "node": source["node"].id,
                    "partner": source["partner"].id,
                    "group": source["group"].id,
                    "company": source["company"].id,
                    "role": source["role"],
                    "inherited": source["inherited"],
                }
                for source in model.browse(record.id)._access_graph_sources()
            ]
        _debug.logic(
            "explained",
            model=model_name,
            operation=operation,
            record=record.id,
            uid=env.uid,
            allowed=explanation["allowed"],
        )
        return explanation

    def _explain_row(self, model_name: str, row: AccessInfo) -> dict:
        return {
            "row": row.id,
            "name": row.name,
            "kind": row.kind,
            "scope": row.guard_scope,
            "group": row.group_id,
            "reach": self._reach_words(model_name, row),
        }

    def _explain_grants(self) -> dict[int, list[dict]]:
        grants = self.env["res.users.grant"]
        if not grants.has_access("read"):
            return {}
        live = grants.search(
            grants._live_domain() & Domain("user_id", "=", self.env.uid)
        )
        implying = self._group_ids_implying()
        carried: dict[int, list[dict]] = {}
        for grant in live:
            entry = {
                "grant": grant.id,
                "group": grant.group_id.id,
                "cause": grant.cause,
                "companies": grant.company_ids.ids,
                "date_to": grant.date_to and str(grant.date_to),
            }
            for group_id, implied_by in implying.items():
                if grant.group_id.id in implied_by:
                    carried.setdefault(group_id, []).append(entry)
        return carried

    def _explain_parents(self, target: models.BaseModel, operation: str) -> list:
        if not target._inherits_rules:
            return []
        parents = []
        for parent_model_name, field_name in target._inherits.items():
            if operation == "create" and not target._fields[field_name].store:
                continue
            parent = self._access_evaluator(target._name).browse(target.id)[field_name]
            if not parent:
                continue
            parents.append(
                {"field": field_name}
                | self._explain_record(
                    self.env[parent_model_name].browse(parent.id), operation
                )
            )
        return parents

    def _explain_fields(self, target: models.BaseModel) -> list[dict]:
        hidden = []
        for name, field in target._fields.items():
            if field.access_classes is None:
                continue
            verdicts = {}
            for operation in ("read", "write"):
                verdicts[operation] = bool(
                    target._has_field_access(field, operation)
                    and target._filtered_field_access(field, operation)
                )
            if not all(verdicts.values()):
                hidden.append(
                    {
                        "field": name,
                        "string": field.string,
                        "classes": list(field.access_classes.read),
                    }
                    | verdicts
                )
        return hidden

    @api.model
    def _who_can(self, record: models.BaseModel, operation: str) -> list[dict]:
        record.check_singleton()
        self._check_operation(record._name, operation)
        groups = self._get_groups_with_access(record._name, operation)
        candidates = self.env["res.users"].search(
            [("all_group_ids", "in", groups.ids), ("active", "=", True)]
        )
        result = []
        for user in candidates:
            principal = self.with_user(user).with_context(
                allowed_company_ids=user.company_ids.ids
            )
            target = principal.env[record._name].browse(record.id)
            if not target.has_access(operation):
                continue
            explanation = principal._explain_record(target, operation)
            result.append(
                {
                    "user": user.id,
                    "through": [
                        entry["name"]
                        for entry in explanation["permissions"]
                        if entry["admits"]
                    ],
                }
            )
        _debug.logic(
            "who_can",
            model=record._name,
            operation=operation,
            record=record.id,
            candidates=len(candidates),
            allowed=len(result),
        )
        return result

    @api.model
    def _explain_as(
        self, user: models.BaseModel, record: models.BaseModel, operation: str
    ) -> dict[str, Any]:
        if user != self.env.user:
            self.env["ir.access.log"]._record(
                [
                    {
                        "event": "explained_other",
                        "subject_user_id": user.id,
                        "model_name": record._name,
                        "operation": operation,
                        "res_ids": str(record.id),
                    }
                ]
            )
        principal = self.with_user(user).with_context(
            allowed_company_ids=user.company_ids.ids
        )
        return principal._explain_record(
            principal.env[record._name].browse(record.id), operation
        )
