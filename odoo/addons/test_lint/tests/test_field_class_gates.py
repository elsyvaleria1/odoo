import ast
import functools
import tempfile
from pathlib import Path

from lxml import etree

from odoo.modules import Manifest

from . import _access_index as index
from . import _parallel, lint_case
from ._derived_fields import derived_findings
from ._rules import is_test_path

_CLASS_KEYS = ("classification", "write_classification", "discloses")

type FieldCall = tuple[int, frozenset[str], dict[str, str | None]]


def _field_call_facts(path: str) -> list[FieldCall]:
    # (line, keyword names, the class keywords' literal values) of every
    # `name = fields.X(...)` in a class body
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    except SyntaxError, UnicodeDecodeError:
        return []
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if not (
                isinstance(statement, (ast.Assign, ast.AnnAssign))
                and isinstance(statement.value, ast.Call)
            ):
                continue
            call = statement.value
            func = call.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "fields"
            ):
                continue
            keywords = {k.arg: k.value for k in call.keywords if k.arg}
            found.append(
                (
                    statement.lineno,
                    frozenset(keywords),
                    {key: index._string(keywords.get(key)) for key in _CLASS_KEYS},
                )
            )
    return found


@functools.cache
def _production_field_calls() -> dict[str, list[FieldCall]]:
    return _parallel.map_items(
        _field_call_facts,
        [
            path
            for path in lint_case.module_file_paths()
            if path.endswith(".py") and not is_test_path(path)
        ],
    )


def _field_calls(path: str) -> list[FieldCall]:
    known = _production_field_calls()
    return known[path] if path in known else _field_call_facts(path)


def anonymous_findings(paths) -> list[str]:
    # a field whose only class is the one its groups= compiles into: nothing
    # names it, so no row can grant or reach-limit it
    return [
        f"{path}:{line}"
        for path in paths
        for line, keywords, _classes in _field_calls(path)
        if ("groups" in keywords or "write_groups" in keywords)
        and "classification" not in keywords
        and "write_classification" not in keywords
    ]


@functools.cache
def _shipped_classes() -> dict[str, set[str]]:
    # per module, the classes its data files create
    shipped: dict[str, set[str]] = {}
    for manifest in Manifest.get_all_addon_manifests():
        root = Path(manifest.path)
        for path in index._walk(root, ".xml"):
            if "tests" in path.relative_to(root).parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "ir.access.class" not in text:
                continue
            try:
                tree = etree.fromstring(text.encode())
            except etree.XMLSyntaxError:
                continue
            for record in tree.iter("record"):
                if record.get("model") != "ir.access.class":
                    continue
                for field_node in record.iter("field"):
                    if field_node.get("name") == "name" and field_node.text:
                        shipped.setdefault(manifest.name, set()).add(
                            field_node.text.strip()
                        )
    return shipped


@functools.cache
def _depends() -> dict[str, frozenset[str]]:
    direct = {
        manifest.name: tuple(manifest.get("depends", ()))
        for manifest in Manifest.get_all_addon_manifests()
    }

    def closure(name, seen=frozenset()):
        if name in seen:
            return frozenset()
        result = {name}
        for dependency in direct.get(name, ()):
            result |= closure(dependency, seen | {name})
        return frozenset(result)

    return {name: closure(name) for name in direct}


def undeclared_findings() -> list[str]:
    # a classification naming a class neither its module nor a dependency ships
    shipped = _shipped_classes()
    depends = _depends()
    findings = []
    for manifest in Manifest.get_all_addon_manifests():
        if manifest.name.startswith("test_"):
            continue
        root = Path(manifest.path)
        reachable = set().union(
            *(shipped.get(module, set()) for module in depends.get(manifest.name, ()))
        )
        for path in index._walk(root, ".py"):
            if "tests" in path.relative_to(root).parts or is_test_path(str(path)):
                continue
            for line, _keywords, classes in _field_calls(str(path)):
                for key in _CLASS_KEYS:
                    value = classes[key]
                    if value and value not in reachable:
                        findings.append(
                            f"{path}:{line} {key}={value!r} "
                            f"({manifest.name} ships no such class)"
                        )
    return findings


class TestFieldClassGates(lint_case.LintCase):
    def test_a_classified_field_names_a_class_it_can_reach(self):
        self.assert_ratchet(
            undeclared_findings(),
            "field_class_declared",
            "classification(s) naming a class the module does not ship or depend on",
            "Ship the ir.access.class record in the module or a dependency, "
            "or name one that is.",
        )

    def test_fields_whose_only_class_is_anonymous(self):
        # one floor per repository, as bare_sudo_*: the count then holds at
        # whatever scope the gate runs at, a repository off the addons path
        # being one whose floor is not read
        found: dict[str, list[str]] = {}
        for root in lint_case._module_roots():
            found.setdefault(lint_case.repo_of(root), []).extend(
                anonymous_findings(
                    path
                    for path in lint_case.module_file_paths((Path(root).name,))
                    if path.endswith(".py")
                    and not any(
                        part == "tests" or part.startswith("test_")
                        for part in path.split("/")
                    )
                    and "/migrations/" not in path
                )
            )
        self.assert_ratchet_per_repository(
            found,
            "field_class_anonymous",
            "field(s) in <repo> whose only class is their groups=",
            "Name what the field is (classification=) and state its "
            "readers in ir.access rows for that class; the floor only "
            "goes down.",
        )

    def test_a_derived_field_states_what_it_discloses(self):
        found: dict[str, list[str]] = {}
        for repo in lint_case.repositories():
            with index.scope(lint_case.visible(repo)):
                found[repo] = [
                    finding
                    for finding in derived_findings()
                    if lint_case.repo_of(finding.split(":", 1)[0]) == repo
                ]
        self.assert_ratchet_per_repository(
            found,
            "field_class_derived",
            "derived field(s) showing what a source of theirs hides in <repo>",
            "Give the field its source's class (classification=, or groups=), or "
            "say the derived value is meant to be shown: discloses='<class>'.",
        )


class TestFieldClassGatesSeeTheirFaults(lint_case.LintCase):
    def test_a_grouped_field_without_a_class(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "m.py"
        path.write_text(
            "class M(models.Model):\n"
            "    a = fields.Char(groups='base.group_user')\n"
            "    b = fields.Char(groups='base.group_user', classification='x.y')\n"
            "    c = fields.Char()\n"
        )
        self.assertEqual(len(anonymous_findings([str(path)])), 1)

    def test_a_derived_field_over_a_hidden_source(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "m.py"
        path.write_text(
            "class M(models.Model):\n"
            "    _name = 'planted.derived'\n"
            "    secret = fields.Char(groups='base.group_system')\n"
            "    shown = fields.Char(compute='_compute_shown', store=True)\n"
            "    said = fields.Char(\n"
            "        compute='_compute_shown', store=True, discloses='x.y'\n"
            "    )\n"
            "    lazy = fields.Char(compute='_compute_shown')\n"
            "\n"
            "    @api.depends('secret')\n"
            "    def _compute_shown(self):\n"
            "        pass\n"
        )
        findings = derived_findings((path,))
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("planted.derived.shown", findings[0])
