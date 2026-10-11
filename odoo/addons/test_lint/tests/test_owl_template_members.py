import re
import shutil
from collections import defaultdict
from pathlib import Path

import odoo
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged
from odoo.tests.utils import InfrastructureUnavailable
from odoo.tools.assets.owl_precompile import precompile_templates, web_static_path

from . import lint_case

_ENTRY = re.compile(
    r'^("(?:[^"\\]|\\.)+"): \[".*?", \[.*?\], (function \(app, bdom, helpers\) \{.*?)\],$',
    re.MULTILINE | re.DOTALL,
)
_READ = re.compile(r"ctx\['([A-Za-z_$][\w$]*)'\]")
_ASSIGNED = re.compile(r'ctx\[[`"]([A-Za-z_$][\w$]*)[`"]\]\s*=')
_T_CALL = re.compile(r't-call="([^"{]+)"')
_CLASS = re.compile(r"\bclass\s+(\w+)\s+extends\s+[\w.]+\s*\{")
_PATCH = re.compile(r"\bpatch\(\s*(\w+)\.prototype\s*,\s*\{")
_TEMPLATE = re.compile(r'static\s+template\s*=\s*"([^"]+)"')
_MEMBER = re.compile(
    r"^\s{4}(?:static\s+)?(?:async\s+)?(?:get\s+|set\s+)?\*?([A-Za-z_$][\w$]*)\s*\(",
    re.MULTILINE,
)
_NOT_MEMBERS = frozenset({"constructor", "setup", "if", "for", "while", "switch"})


def free_names(compiled_script: str) -> dict[str, set[str]]:
    free = {}
    for match in _ENTRY.finditer(compiled_script):
        code = match.group(2)
        free[json_loads(match.group(1))] = set(_READ.findall(code)) - set(
            _ASSIGNED.findall(code)
        )
    return free


def _block(text: str, start: int) -> str:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text[start:]


def component_members(sources) -> dict[str, set[str]]:
    classes = defaultdict(set)
    members = defaultdict(set)
    for text in sources:
        for match in _CLASS.finditer(text):
            block = _block(text, match.end() - 1)
            members[match.group(1)] |= set(_MEMBER.findall(block)) - _NOT_MEMBERS
            for template in _TEMPLATE.findall(block):
                classes[template].add(match.group(1))
        for match in _PATCH.finditer(text):
            block = _block(text, match.end() - 1)
            members[match.group(1)] |= set(_MEMBER.findall(block)) - _NOT_MEMBERS
    return {
        template: set().union(*(members[name] for name in names))
        for template, names in classes.items()
    }


def bare_member_findings(registrations: str, compiled_script: str, sources):
    called = set(_T_CALL.findall(registrations))
    members = component_members(sources)
    return sorted(
        f"{template}: {name} (write this.{name})"
        for template, names in free_names(compiled_script).items()
        if template not in called
        for name in names & members.get(template, set())
    )


def _require_precompiler() -> None:
    node_modules = Path(odoo.__path__[0]).parent / "node_modules"
    if not shutil.which("node") or not (node_modules / "jsdom").is_dir():
        raise InfrastructureUnavailable("node with the jsdom package is unavailable")


@tagged("post_install", "-at_install")
class TestOwlTemplateMembers(lint_case.LintCase):
    def test_a_template_reads_its_component_through_this(self):
        _require_precompiler()
        found = set()
        judged, unjudged = 0, []
        with self.superuser_env() as env:
            for name in self.served_bundle_names(env):
                bundle = env["ir.qweb"]._get_asset_bundle(name, css=False, js=True)
                registrations = bundle._xml.generate_xml_bundle()
                if not registrations:
                    continue
                result = precompile_templates(
                    registrations, {}, web_static=web_static_path(), label=name
                )
                if result is None:
                    unjudged.append(name)
                    continue
                judged += 1
                sources = [
                    asset.content
                    for asset in (*bundle.javascripts, *bundle.native_modules)
                    if asset.content
                ]
                found.update(
                    bare_member_findings(registrations, result.script, sources)
                )
        self.assertFalse(
            unjudged,
            "the template precompiler gave no result for these bundles, so their "
            "templates went unread (its log names the cause)",
        )
        self.assertTrue(judged, "no bundle registers a template -- nothing judged")
        self.assert_ratchet(
            sorted(found),
            "owl_bare_member",
            "template(s) reading a member of their component by a bare name, "
            "which OWL 3 reads as an undefined template variable",
            "Write this.<member>: a bare name in an OWL template is a t-set, "
            "t-foreach or slot-scope variable, never the component's.",
        )


_PLANTED_REGISTRATIONS = (
    'registerTemplate("pl.Bar", "/pl/bar.xml", `<div t-name="pl.Bar"/>`);'
    'registerTemplate("pl.Row", "/pl/row.xml", `<div t-name="pl.Row"/>`);'
    '<t t-call="pl.Row"/>'
)
_PLANTED_SCRIPT = (
    '"pl.Bar": ["1", ["pl.Bar"], function (app, bdom, helpers) {'
    " ctx[`item`] = 1; return ctx['shown'] && ctx['item'] && ctx['total']; }],\n"
    '"pl.Row": ["2", ["pl.Row"], function (app, bdom, helpers) {'
    " return ctx['shown']; }],"
)
_PLANTED_SOURCES = [
    (
        "export class Bar extends Component {\n"
        '    static template = "pl.Bar";\n'
        "    get shown() {\n        return true;\n    }\n"
        "    item() {}\n"
        "}\n"
    ),
    "patch(Bar.prototype, {\n    get total() {\n        return 1;\n    },\n});\n",
    (
        "export class Row extends Component {\n"
        '    static template = "pl.Row";\n'
        "    get shown() {\n        return true;\n    }\n"
        "}\n"
    ),
]


class TestOwlTemplateMembersSeesItsFaults(lint_case.LintCase):
    def test_a_bare_getter_and_a_bare_patched_getter_are_found(self):
        self.assertEqual(
            bare_member_findings(
                _PLANTED_REGISTRATIONS, _PLANTED_SCRIPT, _PLANTED_SOURCES
            ),
            ["pl.Bar: shown (write this.shown)", "pl.Bar: total (write this.total)"],
        )

    def test_a_name_the_template_sets_is_its_own(self):
        self.assertEqual(free_names(_PLANTED_SCRIPT)["pl.Bar"], {"shown", "total"})

    def test_a_called_template_reads_its_callers_variables(self):
        findings = bare_member_findings(
            _PLANTED_REGISTRATIONS, _PLANTED_SCRIPT, _PLANTED_SOURCES
        )
        self.assertFalse([f for f in findings if f.startswith("pl.Row")])
