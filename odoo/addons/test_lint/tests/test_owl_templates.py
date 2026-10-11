import functools
import re
from collections.abc import Callable
from pathlib import Path

from lxml import etree

from odoo.modules import Manifest
from odoo.tests.common import BaseCase, no_retry

from . import _js_sources, lint_case
from ._xml_rules import inline_event_handlers

_PARSER = etree.XMLParser(remove_comments=True, resolve_entities=False)
_TAGGED = re.compile(r"\bxml`(.*?)`", re.DOTALL)
_T_ESC = re.compile(r"(?<=\s)t-esc(?=\s*=)|@t-esc\b|<attribute\s+name=[\"']t-esc[\"']")
_OPENING_TAG = re.compile(
    r"<([a-z][\w.-]*)((?:\s+[^\s=>/]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'))?)*)\s*/?>"
)
_HANDLER_ATTRIBUTE = re.compile(r"\s(on[a-z]+)\s*=")


def t_esc_in_xml(source: bytes) -> list[int]:
    root = etree.fromstring(source, _PARSER)
    lines = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        refs_old_name = "t-esc" in element.attrib or any(
            "@t-esc" in value for value in element.attrib.values()
        )
        if element.tag == "attribute" and element.get("name") == "t-esc":
            refs_old_name = True
        if refs_old_name:
            lines.append(element.sourceline)
    return lines


def t_esc_in_js(source: str) -> list[int]:
    return [
        source.count("\n", 0, template.start(1) + hit.start()) + 1
        for template in _TAGGED.finditer(source)
        for hit in _T_ESC.finditer(template.group(1))
    ]


def event_handlers_in_xml(source: bytes) -> list[int]:
    try:
        root = etree.fromstring(source, _PARSER)
    except etree.XMLSyntaxError:
        return []
    return [line for line, _found in inline_event_handlers(root)]


def event_handlers_in_js(source: str) -> list[int]:
    return [
        source.count("\n", 0, template.start(1) + tag.start()) + 1
        for template in _TAGGED.finditer(source)
        for tag in _OPENING_TAG.finditer(template.group(1))
        if tag.group(1) != "t" and _HANDLER_ATTRIBUTE.search(tag.group(2))
    ]


def _owl_template_findings(
    in_xml: Callable[[bytes], list[int]],
    in_js: Callable[[str], list[int]],
    needle: str,
) -> dict[str, tuple[str, ...]]:
    repository_by_addon = {
        manifest.name: lint_case.repo_of(manifest.path)
        for manifest in Manifest.get_all_addon_manifests()
    }
    found: dict[str, list[str]] = {
        repository: [] for repository in repository_by_addon.values()
    }
    for manifest in Manifest.get_all_addon_manifests():
        static_root = Path(manifest.path) / "static"
        if not static_root.is_dir():
            continue
        for path in sorted(static_root.rglob("*.xml")):
            if _js_sources.vendored(path):
                continue
            source = path.read_bytes()
            if needle.encode() in source:
                found[repository_by_addon[manifest.name]] += [
                    f"{path}:{line}" for line in in_xml(source)
                ]
    for addon, path, source in _js_sources.addon_js_outside_lib():
        if needle in source and not _js_sources.vendored(path):
            found[repository_by_addon[addon]] += [
                f"{path}:{line}" for line in in_js(source)
            ]
    return {repository: tuple(sites) for repository, sites in sorted(found.items())}


@functools.cache
def _t_esc_findings() -> dict[str, tuple[str, ...]]:
    return _owl_template_findings(t_esc_in_xml, t_esc_in_js, "t-esc")


@functools.cache
def _event_handler_findings() -> dict[str, tuple[str, ...]]:
    return _owl_template_findings(event_handlers_in_xml, event_handlers_in_js, "on")


class TestOwlTemplates(lint_case.LintCase):
    def test_no_owl_template_uses_t_esc(self):
        self.assert_ratchet_per_repository(
            _t_esc_findings(),
            "owl_t_esc",
            "t-esc in OWL templates (static XML and xml`` in JS) in <repo>",
            "Write t-out: the vendored OWL 3 parses t-esc as a deprecated "
            "alias of t-out and warns on every template it compiles. "
            "Inheritance locators, <attribute name=...> and @t-esc XPaths "
            "follow the parent template's attribute name",
        )

    def test_no_owl_template_carries_an_inline_event_handler(self):
        self.assert_ratchet_per_repository(
            _event_handler_findings(),
            "owl_inline_event_handler",
            "inline on* handlers in OWL templates (static XML and xml`` "
            "in JS) in <repo>",
            "Write t-on-<event>: every HTML response carries a nonce "
            "script policy, under which the browser runs no inline "
            "handler. A component's on* attribute is a prop and a "
            "t-call's a parameter; neither is counted",
        )


@no_retry
class TestOwlTemplateScan(BaseCase):
    def test_every_way_of_naming_t_esc_in_a_static_template_is_found(self):
        source = b"""<templates>
            <t t-name="a"><span t-esc="x"/><span t-out="y"/></t>
            <t t-inherit="a" t-inherit-mode="extension">
                <xpath expr="//span[@t-esc='x']" position="attributes">
                    <attribute name="t-esc">z</attribute>
                </xpath>
            </t>
        </templates>"""
        self.assertEqual(t_esc_in_xml(source), [2, 4, 5])

    def test_a_t_out_template_is_clean(self):
        source = b"""<templates><t t-name="a"><span t-out="x">default</span>
            <xpath expr="//span[@t-out='x']" position="replace"/></t></templates>"""
        self.assertEqual(t_esc_in_xml(source), [])

    def test_only_tagged_templates_in_js_are_scanned(self):
        source = (
            'const arch = `<kanban><t t-esc="record.a.value"/></kanban>`;\n'
            "class A {\n"
            '    static template = xml`<div t-esc="this.x"/>`;\n'
            "}\n"
            'const names = ["t-esc", "t-out"];\n'
        )
        self.assertEqual(t_esc_in_js(source), [3])

    def test_an_inline_handler_is_found_on_an_element_and_as_an_operation(self):
        source = b"""<templates>
            <t t-name="a"><img src="x" onerror="f()"/><button t-on-click="go"/></t>
            <t t-inherit="a" t-inherit-mode="extension">
                <xpath expr="//img" position="attributes">
                    <attribute name="onload">g()</attribute>
                </xpath>
            </t>
            <t t-name="b"><t t-call="c" onchange="this.change"/>
                <Toggle onchange="this.change"/></t>
        </templates>"""
        self.assertEqual(event_handlers_in_xml(source), [2, 5])

    def test_an_inline_handler_in_a_tagged_template_is_found(self):
        source = (
            "class A {\n"
            '    static template = xml`<div t-on-click="go">\n'
            '        <a href="#" onclick="go()">x</a><Child onselect="this.s"/>\n'
            '        <t t-call="x" onchange="this.c"/></div>`;\n'
            "}\n"
            'const html = `<b onclick="x">untagged</b>`;\n'
        )
        self.assertEqual(event_handlers_in_js(source), [3])
