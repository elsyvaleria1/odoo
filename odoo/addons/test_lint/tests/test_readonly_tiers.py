import functools
import re
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from odoo.modules import Manifest

from . import _access_index as index
from . import lint_case
from ._xml_identity import PARSER

_REF = re.compile(r"""ref\(\s*['"]([\w.]+)['"]\s*\)""")
_USER = "base.group_user"


@dataclass
class Group:
    xmlid: str
    where: str = ""
    privilege: str | None = None
    sequence: int | None = None
    implied: set[str] = field(default_factory=set)


def groups() -> dict[str, Group]:
    found: dict[str, Group] = {}
    for manifest in index._module_manifests():
        root = Path(manifest.path)
        for path in index._walk(root, ".xml"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if 'model="res.groups"' not in text:
                continue
            try:
                tree = etree.fromstring(text.encode(), PARSER)
            except etree.XMLSyntaxError:
                continue
            for record in tree.iter("record"):
                if record.get("model") != "res.groups" or not record.get("id"):
                    continue
                xmlid = index._qualify(manifest.name, record.get("id"))
                group = found.setdefault(
                    xmlid, Group(xmlid, where=f"{path}:{record.sourceline}")
                )
                for element in record.iter("field"):
                    name = element.get("name")
                    if name == "privilege_id" and element.get("ref"):
                        group.privilege = index._qualify(
                            manifest.name, element.get("ref")
                        )
                    elif name == "sequence" and (element.text or "").strip().isdigit():
                        group.sequence = int(element.text.strip())
                    elif name == "implied_ids":
                        group.implied |= {
                            index._qualify(manifest.name, ref)
                            for ref in _REF.findall(element.get("eval") or "")
                        }
    return found


def tiers(rows, known: dict[str, Group]) -> dict[str, list]:
    by_tier: dict[str, list] = {}
    for row in rows:
        group = index._qualify(row.module, row.group or "")
        if (
            group.endswith("_readonly")
            and group in known
            and row.creates
            and row.kind == "permission"
        ):
            by_tier.setdefault(group, []).append(row)
    return by_tier


def write_findings(by_tier, models) -> list[str]:
    return sorted(
        f"{row.where()}: {tier} {row.operation} on {row.model}"
        for tier, rows in by_tier.items()
        for row in rows
        if set(row.operation or "") & set("cud")
        and (info := models.get(row.model)) is not None
        and info.kind != "transient"
    )


def rung_findings(by_tier, known: dict[str, Group]) -> list[str]:
    findings = []
    for tier in sorted(by_tier):
        group = known[tier]
        if not group.privilege:
            findings.append(f"{group.where}: {tier} names no privilege")
            continue
        rungs = [
            other
            for other in known.values()
            if other.privilege == group.privilege and other.xmlid != tier
        ]
        if _USER not in group.implied:
            findings.append(f"{group.where}: {tier} does not imply {_USER}")
        if not any(tier in rung.implied for rung in rungs):
            findings.append(f"{group.where}: no rung of its privilege implies {tier}")
        lower = [
            rung.xmlid
            for rung in rungs
            if rung.sequence is not None
            and (group.sequence is None or rung.sequence < group.sequence)
        ]
        if lower:
            findings.append(
                f"{group.where}: {tier} is not its privilege's lowest rung "
                f"({', '.join(sorted(lower))})"
            )
    return findings


@functools.cache
def loaded_with(module: str) -> frozenset[str]:
    seen = set()
    todo = [module]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        manifest = Manifest.for_addon(name, display_warning=False)
        todo.extend(manifest.get("depends", ()) if manifest else ())
    return frozenset(seen)


def dead_row_findings(by_tier, rows, loaded=loaded_with) -> list[str]:
    everyone_reads = {
        (row.model, row.module)
        for row in rows
        if row.creates
        and row.kind == "permission"
        and index._qualify(row.module, row.group or "") == _USER
        and "r" in (row.operation or "")
        and not row.domain
        and row.reach in (None, "all")
    }
    return sorted(
        f"{row.where()}: {tier} reads {row.model}, which {_USER} reads whole"
        for tier, tier_rows in by_tier.items()
        for row in tier_rows
        if "r" in (row.operation or "")
        and any(
            model == row.model and module in loaded(row.module)
            for model, module in everyone_reads
        )
    )


class TestReadonlyTiers(lint_case.LintCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.found = {"writes": {}, "rung": {}, "dead": {}}
        for repo in lint_case.repositories():
            with index.scope(lint_case.visible(repo)):
                rows = index.rows()
                known = groups()
                by_tier = tiers(
                    [row for row in rows if index.repo_of_module(row.module) == repo],
                    known,
                )
                cls.found["writes"][repo] = write_findings(by_tier, index.models())
                cls.found["rung"][repo] = rung_findings(by_tier, known)
                cls.found["dead"][repo] = dead_row_findings(by_tier, rows)
            if repo == "odoo":
                cls.groups, cls.tiers = known, by_tier

    def test_the_scan_reaches_the_tiers(self):
        self.assertIn("base.group_user", self.groups)
        if "sale.group_sale_readonly" in self.groups:
            self.assertIn("sale.group_sale_readonly", self.tiers)

    def test_a_tier_writes_nothing(self):
        self.assert_ratchet_per_repository(
            self.found["writes"],
            "readonly_tier_writes",
            "read-only tier row(s) granting create, write or delete in <repo>",
            "A read-only tier reads every model its app shows and writes none but "
            "its wizards (coding_guidelines.rst §10.8): drop the letters, or give "
            "the write to the transacting rung.",
        )

    def test_a_tier_is_the_lowest_rung_of_its_privilege(self):
        self.assert_ratchet_per_repository(
            self.found["rung"],
            "readonly_tier_rung",
            "read-only tier(s) out of place in their privilege in <repo>",
            "The tier sets privilege_id, has the lowest sequence of its privilege, "
            "implies base.group_user, and the lowest all-documents rung implies it.",
        )

    def test_a_tier_duplicates_no_read_of_every_user(self):
        self.assert_ratchet_per_repository(
            self.found["dead"],
            "readonly_tier_dead_rows",
            "read-only tier row(s) reading what every internal user reads in <repo>",
            "base.group_user already reads the model whole: the tier's row is dead, "
            "drop it.",
        )


class TestReadonlyTierGatesSeeTheirFaults(lint_case.LintCase):
    def _row(self, **values):
        defaults = {
            "module": "planted",
            "xmlid": "planted.row",
            "path": "planted.csv",
            "line": 2,
            "model": "res.partner",
            "group": "planted.group_planted_readonly",
            "kind": "permission",
            "operation": "r",
            "domain": None,
            "creates": True,
        }
        return index.Row(**(defaults | values))

    def _groups(self, **tier):
        return {
            "planted.group_planted_readonly": Group(
                "planted.group_planted_readonly",
                **(
                    {"privilege": "planted.p", "sequence": 5, "implied": {_USER}} | tier
                ),
            ),
            "planted.group_planted_user": Group(
                "planted.group_planted_user",
                privilege="planted.p",
                sequence=10,
                implied={"planted.group_planted_readonly"},
            ),
        }

    def test_a_tier_that_writes(self):
        known = self._groups()
        by_tier = tiers([self._row(operation="ru")], known)
        self.assertEqual(len(write_findings(by_tier, index.models())), 1)
        by_tier = tiers([self._row()], known)
        self.assertFalse(write_findings(by_tier, index.models()))

    def test_a_tier_out_of_place(self):
        row = [self._row()]
        self.assertFalse(rung_findings(tiers(row, self._groups()), self._groups()))
        for broken in (
            {"implied": set()},
            {"sequence": 20},
            {"privilege": None},
        ):
            with self.subTest(broken=broken):
                known = self._groups(**broken)
                self.assertTrue(rung_findings(tiers(row, known), known))

    def test_a_dead_tier_row(self):
        known = self._groups()
        everyone = self._row(group="base.group_user")
        by_tier = tiers([self._row()], known)
        self.assertEqual(
            len(dead_row_findings(by_tier, [everyone], lambda module: {module})), 1
        )
        self.assertFalse(
            dead_row_findings(
                by_tier,
                [self._row(group="base.group_user", reach="own")],
                lambda module: {module},
            )
        )
        self.assertFalse(
            dead_row_findings(by_tier, [everyone], lambda module: set()),
            "a row of a module the tier's does not load is not dead",
        )
