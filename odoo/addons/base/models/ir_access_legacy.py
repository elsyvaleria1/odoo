"""Access written for stock Odoo: ir.model.access lines and ir.rule records.

A module written for stock Odoo 19.0 ships its access as ir.model.access lines
and ir.rule records, two models this fork no longer has. The loader leaves
them to ``ir.access._load_legacy_access``, which reads them from the module's
data files once its data is loaded and loads the ir.access rows stock Odoo's
check amounts to, under the module's own external ids:

- a line is a permission of its group, over the operations no rule of a group
  its members all hold governs;
- a rule of a group is a permission of that group, and of every group whose
  members all hold it, with the rule's domain, over the operations those
  groups have a line for;
- a rule of a group binds its members whichever line opened the model: stock
  Odoo ORs the rules of the user's groups and applies them to every access
  line. That is a members guard on the rule's group (base.conditional_reach):
  its members reach what their conditional rows reach, and what the groups
  granting the model whole through a rule (a see-all rule) grant;
- a global rule is a guard of everyone.

The lines of other modules on the same models take part as the lines they
were. What stock Odoo does that no row can say (a rule of a group none of whose
members hold a line of the model, beside the lines of unrelated groups) is
named in the log, and the rows stay on the side of refusing.

Groups and models this fork renamed are followed; one it removed is refused
by name.
"""

from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree

from odoo import api, models
from odoo.fields import Command
from odoo.modules.module import get_manifest, get_module_path
from odoo.tools.safe_eval import safe_eval

from .ir_access_convert import (
    GROUP_EVERYONE,
    NOTHING,
    OPERATIONS,
    TRUE,
    _Converter,
    _local_name,
    operation_string,
)

_logger = logging.getLogger(__name__)

LEGACY_GROUP_RENAMES = {
    "api_doc.group_allow_doc": "rpc.group_allow_doc",
    "fleet.fleet_group_manager": "resource_asset_vehicle.fleet_group_manager",
    "fleet.fleet_group_user": "resource_asset_vehicle.fleet_group_user",
    "sale_management.group_sale_order_template": "sale.group_sale_order_template",
    "sales_team.group_sale_manager": "sale.group_sale_manager",
    "sales_team.group_sale_salesman": "sale.group_sale_salesman",
    "sales_team.group_sale_salesman_all_leads": "sale.group_sale_salesman_all_leads",
}
LEGACY_GROUPS_REMOVED = {
    "purchase_requisition.group_purchase_alternatives": (
        "purchase alternatives are not a separate group in this fork"
    ),
}
LEGACY_MODEL_RENAMES = {
    "crm.lost.reason": "loss.reason",
    "crm.team": "team.team",
    "crm.team.member": "team.member",
    "maintenance.request": "maintenance.order",
    "purchase.requisition": "purchase.agreement",
    "purchase.requisition.line": "purchase.agreement.line",
    "resource.calendar.leaves": "resource.schedule.exception",
    "stock.lot": "product.trace",
}
_OPERATION_NAMES = {"c": "create", "r": "read", "u": "write", "d": "unlink"}
_PERMS = ("perm_read", "perm_write", "perm_create", "perm_unlink")
_CEILING_PREDICATE = "base.access_predicate_conditional_reach"


@dataclass(slots=True)
class LegacySources:
    """A module's lines and rules as its files state them: references unresolved."""

    lines: list[dict[str, Any]] = field(default_factory=list)
    rules: list[dict[str, Any]] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.lines or self.rules)


class _Ref(str):
    __slots__ = ()


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "none")
    return bool(value)


def _commands(value: Any) -> Iterator[tuple[int, Any]]:
    for command in value or ():
        if isinstance(command, (list, tuple)) and command:
            yield command[0], command[1:]


def _group_refs(value: Any) -> list[str]:
    groups: list[str] = []
    for code, args in _commands(value):
        if code in (Command.LINK, Command.UPDATE) and args:
            groups.append(str(args[0]))
        elif code == Command.SET and len(args) > 1:
            groups = [str(ref) for ref in args[1]]
        elif code in (Command.UNLINK, Command.DELETE) and args:
            groups = [g for g in groups if g != str(args[0])]
        elif code == Command.CLEAR:
            groups = []
    return groups


def _record_fields(record: etree._Element) -> dict[str, Any]:
    values: dict[str, Any] = {}
    context = {"ref": _Ref, "Command": Command}
    for node in record.iterchildren("field"):
        name = node.get("name")
        if ref := node.get("ref"):
            values[name] = _Ref(ref)
        elif expression := node.get("eval"):
            values[name] = safe_eval(expression, dict(context))
        else:
            values[name] = node.text or ""
    return values


def _noupdate(record: etree._Element) -> bool:
    return any(
        _bool(element.get("noupdate"), False)
        for element in record.iterancestors()
        if element.tag in ("data", "odoo")
    )


def legacy_access_sources(module: str) -> LegacySources:
    sources = LegacySources()
    path = get_module_path(module, display_warning=False)
    if not path:
        return sources
    for name in get_manifest(module, path).get("data", ()):
        file = Path(path, name)
        if not file.is_file():
            continue
        if file.suffix == ".csv" and file.stem.split("-")[0] == "ir.model.access":
            text = file.read_text(encoding="utf-8-sig")
            for line in csv.DictReader(io.StringIO(text)):
                sources.lines.append(
                    {
                        "id": line.get("id") or "",
                        "name": line.get("name") or "",
                        "model_ref": line.get("model_id:id") or line.get("model_id/id"),
                        "group_ref": line.get("group_id:id")
                        or line.get("group_id/id")
                        or "",
                        "active": _bool(line.get("active"), True),
                        **{perm: _bool(line.get(perm), False) for perm in _PERMS},
                        "noupdate": False,
                        "file": name,
                    }
                )
        elif file.suffix == ".xml":
            text = file.read_text(encoding="utf-8", errors="replace")
            if "ir.rule" not in text and "ir.model.access" not in text:
                continue
            for record in etree.parse(str(file)).iter("record"):
                model = record.get("model")
                if model not in ("ir.rule", "ir.model.access"):
                    continue
                values = _record_fields(record)
                common = {
                    "id": record.get("id") or "",
                    "name": values.get("name") or "",
                    "model_ref": values.get("model_id"),
                    "active": _bool(values.get("active"), True),
                    "noupdate": _noupdate(record),
                    "file": name,
                }
                if model == "ir.model.access":
                    sources.lines.append(
                        {
                            **common,
                            "group_ref": values.get("group_id") or "",
                            **{perm: _bool(values.get(perm), False) for perm in _PERMS},
                        }
                    )
                    continue
                domain = values.get("domain_force")
                sources.rules.append(
                    {
                        **common,
                        "domain_force": domain
                        if isinstance(domain, str)
                        else repr(domain),
                        "group_refs": _group_refs(values.get("groups")),
                        "global": _bool(values.get("global"), not values.get("groups")),
                        **{perm: _bool(values.get(perm), True) for perm in _PERMS},
                    }
                )
    return sources


def convert_legacy(
    module: str,
    lines: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    implications: dict[str, Iterable[str]],
    context_lines: Iterable[dict[str, Any]] = (),
) -> tuple[list[dict[str, Any]], list[str]]:
    context = [{**line, "module": None} for line in context_lines]
    converter = _Converter([*lines, *context], rules, implications, None)
    closure = converter.closure
    rows: list[dict[str, Any]] = []
    notes: list[str] = []

    def own(item: Any) -> bool:
        return item.module == module

    for model in sorted(set(converter.acls) | set(converter.rules)):
        acls = converter.acls.get(model, [])
        model_rules = converter.rules.get(model, [])
        grants = [rule for rule in model_rules if rule.group and not rule.restrict]
        see_all: dict[str, set[str]] = defaultdict(set)
        for rule in grants:
            if rule.domain == TRUE:
                for op in rule.ops:
                    see_all[op].add(rule.group)
        for acl in acls:
            if not own(acl):
                continue
            if not acl.ops:
                rows.append(_row(acl, "permission", acl.group, "r", NOTHING, acl.xmlid))
                continue
            governed = set()
            for rule in grants:
                if rule.group in closure[acl.group]:
                    governed |= rule.ops & acl.ops
            if free := acl.ops - governed:
                rows.append(_row(acl, "permission", acl.group, free, TRUE, acl.xmlid))
        for rule in grants:
            if not own(rule):
                continue
            granted: dict[str, set[str]] = defaultdict(set)
            unrelated: set[str] = set()
            for acl in acls:
                shared = rule.ops & acl.ops
                if not shared:
                    continue
                if rule.group in closure[acl.group]:
                    granted[acl.group] |= shared
                elif acl.group in closure[rule.group]:
                    granted[rule.group] |= shared
                else:
                    unrelated |= shared
            for group, ops in sorted(granted.items()):
                xmlid = rule.xmlid
                if rule.groups != (group,):
                    xmlid = f"{rule.xmlid}_{_local_name(group)}"
                rows.append(_row(rule, "permission", group, ops, rule.domain, xmlid))
            if unrelated - set().union(*granted.values(), set()):
                notes.append(
                    f"{rule.key}: lines of groups unrelated to "
                    f"{rule.group} open {model} "
                    f"{operation_string(unrelated)}; a member reaching it only "
                    f"through them gets what their other groups' rules grant, "
                    f"where stock Odoo gave this rule's records"
                )
            if rule.domain == TRUE:
                continue
            if "#" in rule.group:
                notes.append(
                    f"{rule.key}: its group has no external id, so nothing bounds "
                    f"its members to the rule when another line opens {model}"
                )
                continue
            rows.extend(
                _ceiling(module, model, rule.group, op, see_all[op] - {rule.group})
                for op in sorted(rule.ops)
            )
        for rule in model_rules:
            if not own(rule) or (rule.group and not rule.restrict):
                continue
            scope = "members" if rule.group else "everyone"
            xmlid = rule.xmlid
            if rule.group and len(rule.groups) > 1:
                xmlid = f"{rule.xmlid}_{_local_name(rule.group)}"
            row = _row(
                rule,
                "guard",
                rule.group or GROUP_EVERYONE,
                rule.ops,
                rule.domain,
                xmlid,
            )
            row["guard_scope"] = scope
            rows.append(row)
    return _deduplicated(rows), notes


def _row(source, kind, group, ops, domain, xmlid) -> dict[str, Any]:
    return {
        "xmlid": xmlid,
        "name": source.name,
        "model": source.model,
        "kind": kind,
        "guard_scope": "everyone",
        "group": group,
        "operation": operation_string(ops) if not isinstance(ops, str) else ops,
        "domain": domain,
        "noupdate": source.noupdate,
    }


def _ceiling(module, model, group, op, see_all) -> dict[str, Any]:
    args = {"operation": _OPERATION_NAMES[op], "role": group}
    if with_groups := sorted(g for g in see_all if "#" not in g):
        args["with"] = with_groups
    suffix = f"{model}_{group}".replace(".", "_")
    return {
        "xmlid": f"{module}.legacy_ceiling_{suffix}_{op}",
        "name": f"{model}: what a member of {group} {args['operation']}s, as its rule bounds it",
        "model": model,
        "kind": "guard",
        "guard_scope": "members",
        "group": group,
        "operation": op,
        "domain": TRUE,
        "reach": "predicate",
        "predicate_args": args,
        "noupdate": False,
    }


def _deduplicated(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    kept = []
    for row in rows:
        other = seen.get(row["xmlid"])
        if other is None:
            seen[row["xmlid"]] = row
            kept.append(row)
            continue
        if (other["kind"], other["group"], other["domain"]) == (
            row["kind"],
            row["group"],
            row["domain"],
        ):
            ops = set(other["operation"]) | set(row["operation"])
            other["operation"] = "".join(op for op in OPERATIONS if op in ops)
            continue
        index = 2
        while f"{row['xmlid']}_{index}" in seen:
            index += 1
        row["xmlid"] = f"{row['xmlid']}_{index}"
        seen[row["xmlid"]] = row
        kept.append(row)
    return kept


class IrAccess(models.Model):
    _inherit = "ir.access"

    @api.model
    def _load_legacy_access(self, module: str, mode: str) -> dict[str, bool]:
        sources = legacy_access_sources(module)
        if not sources:
            return {}
        env = self.env
        group_keys = self._legacy_group_keys()
        lines = [self._legacy_line(module, line, group_keys) for line in sources.lines]
        rules = [self._legacy_rule(module, rule, group_keys) for rule in sources.rules]
        models_ = {item["model"] for item in [*lines, *rules]}
        rows, notes = convert_legacy(
            module,
            lines,
            rules,
            self._legacy_implications(group_keys),
            self._legacy_context_lines(module, models_, group_keys),
        )
        for note in notes:
            _logger.warning("Module %s: %s", module, note)
        predicate = env.ref(_CEILING_PREDICATE)
        model_ids = {name: env["ir.model"]._get_id(name) for name in models_}
        group_ids = {key: gid for gid, key in group_keys.items()}
        data_list = []
        for row in rows:
            values = {
                "name": row["name"],
                "model_id": model_ids[row["model"]],
                "group_id": group_ids.get(row["group"]) or env.ref(row["group"]).id,
                "kind": row["kind"],
                "guard_scope": row["guard_scope"],
                "operation": row["operation"],
                "domain": row["domain"] or False,
            }
            if row.get("reach") == "predicate":
                values.update(
                    reach="predicate",
                    predicate_id=predicate.id,
                    predicate_args=row["predicate_args"],
                )
            data_list.append(
                {"xml_id": row["xmlid"], "values": values, "noupdate": row["noupdate"]}
            )
        _logger.info(
            "Module %s: %s stock access lines and %s rules loaded as %s ir.access rows",
            module,
            len(lines),
            len(rules),
            len(data_list),
        )
        self.with_context(install_mode=True)._load_records(
            data_list, update=mode == "update"
        )
        return {
            data["xml_id"] if "." in data["xml_id"] else f"{module}.{data['xml_id']}": (
                data["noupdate"]
            )
            for data in data_list
        }

    @api.model
    def _legacy_group_keys(self) -> dict[int, str]:
        self.env.cr.execute(
            """
            SELECT DISTINCT ON (res_id) res_id, module || '.' || name
              FROM ir_model_data WHERE model = 'res.groups'
             ORDER BY res_id, id
            """
        )
        keys = dict(self.env.cr.fetchall())
        self.env.cr.execute("SELECT id FROM res_groups")
        return {
            group_id: keys.get(group_id, f"res.groups#{group_id}")
            for [group_id] in self.env.cr.fetchall()
        }

    @api.model
    def _legacy_implications(self, group_keys: dict[int, str]) -> dict[str, set[str]]:
        self.env.cr.execute("SELECT gid, hid FROM res_groups_implied_rel")
        implications: dict[str, set[str]] = defaultdict(set)
        for gid, hid in self.env.cr.fetchall():
            implications[group_keys[gid]].add(group_keys[hid])
        return implications

    @api.model
    def _legacy_context_lines(
        self, module: str, model_names: set[str], group_keys: dict[int, str]
    ) -> list[dict[str, Any]]:
        rows = self.with_context(active_test=True).search(
            [
                ("model_id.model", "in", sorted(model_names)),
                ("kind", "=", "permission"),
                ("reach", "=", False),
            ]
        )
        owned = set(
            self.env["ir.model.data"]
            .search([("model", "=", "ir.access"), ("module", "=", module)])
            .mapped("res_id")
        )
        return [
            {
                "id": f"context{row.id}",
                "model": row.model_id.model,
                "group": group_keys[row.group_id.id],
                **{
                    perm: op in (row.operation or "")
                    for op, perm in zip("rucd", _PERMS, strict=True)
                },
            }
            for row in rows
            if row.id not in owned and (not row.domain or row.domain == "[]")
        ]

    def _legacy_ref(self, module: str, ref: str | None, what: str, source: dict) -> str:
        if not ref:
            raise ValueError(
                f"Module {module}: {source['file']} {source['id']} names no {what}"
            )
        return ref if "." in ref else f"{module}.{ref}"

    def _legacy_model(self, module: str, source: dict) -> str:
        xmlid = self._legacy_ref(module, source["model_ref"], "model", source)
        record = self.env.ref(xmlid, raise_if_not_found=False)
        if record is not None and record._name == "ir.model":
            return record.model
        for old, new in LEGACY_MODEL_RENAMES.items():
            if _local_name(xmlid) == "model_" + old.replace(".", "_"):
                if new in self.env:
                    return new
        raise ValueError(
            f"Module {module}: {source['file']} {source['id']} is for model "
            f"{xmlid}, which this fork does not have"
        )

    def _legacy_group(
        self, module: str, ref: str, source: dict, group_keys: dict[int, str]
    ) -> str:
        xmlid = self._legacy_ref(module, ref, "group", source)
        xmlid = LEGACY_GROUP_RENAMES.get(xmlid, xmlid)
        if reason := LEGACY_GROUPS_REMOVED.get(xmlid):
            raise ValueError(
                f"Module {module}: {source['file']} {source['id']} is for group "
                f"{xmlid}, which this fork removed: {reason}"
            )
        group = self.env.ref(xmlid, raise_if_not_found=False)
        if group is None or group._name != "res.groups":
            raise ValueError(
                f"Module {module}: {source['file']} {source['id']} is for group "
                f"{xmlid}, which this fork does not have"
            )
        return group_keys[group.id]

    def _legacy_line(self, module: str, line: dict, group_keys: dict) -> dict:
        return {
            **{perm: line[perm] for perm in _PERMS},
            "xmlid": self._legacy_ref(module, line["id"], "external id", line),
            "module": module,
            "noupdate": line["noupdate"],
            "name": line["name"],
            "active": line["active"],
            "model": self._legacy_model(module, line),
            "group": line["group_ref"]
            and self._legacy_group(module, line["group_ref"], line, group_keys),
        }

    def _legacy_rule(self, module: str, rule: dict, group_keys: dict) -> dict:
        return {
            **{perm: rule[perm] for perm in _PERMS},
            "xmlid": self._legacy_ref(module, rule["id"], "external id", rule),
            "module": module,
            "noupdate": rule["noupdate"],
            "name": rule["name"],
            "active": rule["active"],
            "model": self._legacy_model(module, rule),
            "domain_force": rule["domain_force"],
            "global": rule["global"],
            "groups": [
                self._legacy_group(module, ref, rule, group_keys)
                for ref in rule["group_refs"]
            ],
        }
