import csv
import functools
import io
import re
import tokenize
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lxml import etree

from odoo.modules.module import get_manifest, get_module_path
from odoo.tools.convert import _record_noupdate

GROUP_EVERYONE = "base.group_everyone"
OPERATIONS = "crud"
PERM_OF_OPERATION = {
    "c": "perm_create",
    "r": "perm_read",
    "u": "perm_write",
    "d": "perm_unlink",
}
TRUE = ""
NOTHING = "[(0, '=', 1)]"
_TRUE_DOMAIN_RE = re.compile(
    r"""^\s*(\[\s*\]|\[\s*\(\s*1\s*,\s*(["'])=\2\s*,\s*1\s*\)\s*\])\s*$"""
)


@dataclass(frozen=True, slots=True)
class Effective:
    guards: frozenset[str]
    grants: frozenset[str] | None

    @property
    def sees_all(self) -> bool:
        return self.grants is not None and TRUE in self.grants

    @classmethod
    def of(cls, guards: Iterable[str], grants: Iterable[str] | None) -> Effective:
        guards = frozenset(guards) - {TRUE}
        if grants is None:
            return cls(frozenset(), None)
        grants = frozenset(grants)
        return cls(guards, frozenset({TRUE}) if TRUE in grants else grants)


@dataclass(slots=True)
class _Acl:
    key: str
    xmlid: str | None
    module: str | None
    name: str
    model: str
    group: str
    ops: frozenset[str]
    noupdate: bool = False


@dataclass(slots=True)
class _Rule:
    key: str
    xmlid: str | None
    module: str | None
    name: str
    model: str
    group: str | None
    groups: tuple[str, ...]
    ops: frozenset[str]
    domain: str
    restrict: bool
    noupdate: bool = False


def normalize_domain(domain: str | None) -> str:
    if not domain or _TRUE_DOMAIN_RE.match(domain):
        return TRUE
    return _without_comments(domain).strip()


def _without_comments(domain: str) -> str:
    if "#" not in domain:
        return domain
    try:
        comments = [
            token.start
            for token in tokenize.generate_tokens(io.StringIO(domain).readline)
            if token.type == tokenize.COMMENT
        ]
    except tokenize.TokenError, SyntaxError:
        return domain
    if not comments:
        return domain
    lines = domain.splitlines()
    for row, col in comments:
        lines[row - 1] = lines[row - 1][:col]
    return " ".join(" ".join(line.split()) for line in lines if line.strip())


def operation_string(ops: Iterable[str]) -> str:
    ops = set(ops)
    return "".join(op for op in OPERATIONS if op in ops)


def group_closures(
    group_implications: Mapping[str, Iterable[str]],
    extra: Iterable[str] = (),
) -> dict[str, frozenset[str]]:
    implied = {group: set(targets) for group, targets in group_implications.items()}
    universe = set(implied) | {g for gs in implied.values() for g in gs} | set(extra)
    universe.add(GROUP_EVERYONE)
    closures: dict[str, frozenset[str]] = {}
    for group in universe:
        seen = {group, GROUP_EVERYONE}
        todo = [group]
        while todo:
            for target in implied.get(todo.pop(), ()):
                if target not in seen:
                    seen.add(target)
                    todo.append(target)
        closures[group] = frozenset(seen)
    return closures


def _local_name(xmlid: str) -> str:
    return xmlid.rpartition(".")[2]


def _module_of(xmlid: str | None) -> str | None:
    return xmlid.partition(".")[0] if xmlid and "." in xmlid else None


class _Converter:
    def __init__(
        self,
        acl_lines: Sequence[Mapping[str, Any]],
        rules: Sequence[Mapping[str, Any]],
        group_implications: Mapping[str, Iterable[str]],
    ) -> None:
        self.acls: dict[str, list[_Acl]] = defaultdict(list)
        self.rules: dict[str, list[_Rule]] = defaultdict(list)
        mentioned: set[str] = set()
        for index, line in enumerate(acl_lines):
            if acl := self._read_acl(index, line):
                self.acls[acl.model].append(acl)
                mentioned.add(acl.group)
        for index, rule in enumerate(rules):
            for parsed in self._read_rule(index, rule):
                self.rules[parsed.model].append(parsed)
                if parsed.group:
                    mentioned.add(parsed.group)
        self.closure = group_closures(group_implications, mentioned)

    @staticmethod
    def _module(line: Mapping[str, Any]) -> str | None:
        return line.get("module") or _module_of(line.get("xmlid"))

    def _read_acl(self, index: int, line: Mapping[str, Any]) -> _Acl | None:
        key = line.get("xmlid") or f"ir.model.access#{line.get('id', index)}"
        if not (line.get("active", True) and line.get("model")):
            return None
        ops = frozenset(op for op, perm in PERM_OF_OPERATION.items() if line.get(perm))
        return _Acl(
            key=key,
            xmlid=line.get("xmlid"),
            module=self._module(line),
            name=line.get("name") or line["model"],
            model=line["model"],
            group=line.get("group") or GROUP_EVERYONE,
            ops=ops,
            noupdate=bool(line.get("noupdate")),
        )

    def _read_rule(self, index: int, rule: Mapping[str, Any]) -> list[_Rule]:
        key = rule.get("xmlid") or f"ir.rule#{rule.get('id', index)}"
        if not (rule.get("active", True) and rule.get("model")):
            return []
        ops = frozenset(
            op
            for op, perm in PERM_OF_OPERATION.items()
            if rule.get(perm) is None or rule.get(perm)
        )
        composition = rule.get("composition") or "grant"
        if not ops or composition not in ("grant", "restrict"):
            return []
        domain = normalize_domain(rule.get("domain_force"))
        groups = tuple(sorted(set(rule.get("groups") or ())))
        if not groups and rule.get("global") is False:
            return []
        common = {
            "key": key,
            "xmlid": rule.get("xmlid"),
            "module": self._module(rule),
            "name": rule.get("name") or rule["model"],
            "model": rule["model"],
            "groups": groups,
            "ops": ops,
            "domain": domain,
            "restrict": composition == "restrict",
            "noupdate": bool(rule.get("noupdate")),
        }
        if not groups:
            return [_Rule(group=None, **common)]
        return [_Rule(group=group, **common) for group in groups]

    @staticmethod
    def new_effective(
        rows: Iterable[Mapping[str, Any]], op: str, groups: frozenset[str]
    ) -> Effective:
        guards, grants = set(), set()
        for row in rows:
            if op not in row["operation"]:
                continue
            if row["kind"] == "permission":
                if row["group"] in groups and row["domain"] != NOTHING:
                    grants.add(row["domain"])
            elif row["guard_scope"] == "everyone" or row["group"] in groups:
                guards.add(row["domain"])
        return Effective.of(guards, grants or None)


def reach(
    rows: Iterable[Mapping[str, Any]], operation: str, groups: frozenset[str]
) -> Effective:
    return _Converter.new_effective(rows, operation, groups)


def _qualify_ref(module: str, ref: str | None) -> str:
    return "" if not ref else ref if "." in ref else f"{module}.{ref}"


def shipped_access_records(module: str) -> Iterator[tuple[str, dict[str, str], bool]]:
    path = get_module_path(module, display_warning=False)
    if not path:
        return
    qualify = functools.partial(_qualify_ref, module)
    for name in get_manifest(module, path).get("data", ()):
        file = Path(path, name)
        if not file.is_file():
            continue
        if file.name == "ir.access.csv":
            with file.open(newline="", encoding="utf-8") as stream:
                for line in csv.DictReader(stream):
                    yield (
                        qualify(line["id"]),
                        {
                            "kind": line.get("kind") or "",
                            "group": qualify(line.get("group_id/id")),
                            "operation": line.get("operation") or "",
                            "model": qualify(line.get("model_id/id")),
                        },
                        False,
                    )
        elif file.suffix == ".xml":
            for record in etree.parse(str(file)).iter("record"):
                if record.get("model") != "ir.access" or not record.get("id"):
                    continue
                fields = {f.get("name"): f for f in record.iter("field")}
                yield (
                    qualify(record.get("id")),
                    {
                        "kind": (fields["kind"].text or "") if "kind" in fields else "",
                        "group": qualify(fields["group_id"].get("ref"))
                        if "group_id" in fields
                        else "",
                        "operation": (fields["operation"].text or "")
                        if "operation" in fields
                        else "",
                        "model": qualify(fields["model_id"].get("ref"))
                        if "model_id" in fields
                        else "",
                    },
                    _record_noupdate(record),
                )
