"""Every Owl template extension locates its target in the template it extends.

Owl templates are inherited in the browser, lazily, the first time a template
is rendered (`@web/core/template_inheritance`). An `<xpath>` that matches
nothing is not an asset error and not a load error: it throws inside the owl
lifecycle when the component first renders, so the only thing that notices is
a tour that happens to open that screen. That is how two breaks sat in the tree
unnoticed:

* `web.KanbanView` started rendering `<ViewLayout>` instead of `<Layout>`; the
  commit moved the eight inheritors in `odoo` and `account_online_synchronization`
  kept `//Layout`, so the bank reconciliation screen failed to render whenever
  it was installed -- four account tours red.
* `social`'s post and comment menus moved from Bootstrap's `div.dropdown-menu`
  to `<Dropdown>`/`<DropdownItem>`, and `social_crm` kept inserting its
  "Create Lead" link before `div.dropdown-menu/a[1]`.

This reads every template under `static/src` of every addon on the addons path,
resolves each template with its primary parents and its extensions, and lists
the operations whose target cannot be located or that the engine refuses. It
locates and applies with `odoo.libs.xml`, which implements the specification the
browser engine does (`web/static/tests/core/template_inheritance_cases.js` holds
both to it), so what fails here fails in the browser.

Templates are indexed across bundles, so a name defined in two bundles is
resolved against the last definition read; the gate is a superset check and
cannot see which bundle loads which file.
"""

import copy
import pathlib
import tempfile
from collections import defaultdict

from lxml import etree

from odoo.libs.xml import XPathExpressionError, apply_inheritance_specs, locate_node
from odoo.tests import tagged
from odoo.tests.common import BaseCase

from . import lint_case

_TEMPLATE_ROOTS = frozenset({"templates", "template", "odoo"})
_PARSER = etree.XMLParser(remove_comments=True)


def _locate(root: etree._Element, operation: etree._Element):
    try:
        return locate_node(root, operation)
    except XPathExpressionError:
        return None


def _apply(
    root: etree._Element, operation: etree._Element
) -> tuple[etree._Element, str | None]:
    try:
        return apply_inheritance_specs(
            copy.deepcopy(root), [copy.deepcopy(operation)]
        ), None
    except (ValueError, etree.XPathError) as e:
        return root, str(e)


def _describe(operation: etree._Element) -> str:
    return operation.get("expr") or etree.tostring(operation).decode()[:120]


def _index(paths):
    definitions = {}
    extensions = defaultdict(list)
    for path in paths:
        try:
            root = etree.parse(path, _PARSER).getroot()
        except etree.XMLSyntaxError:
            continue
        elements = (
            [el for el in root if isinstance(el.tag, str)]
            if root.tag in _TEMPLATE_ROOTS
            else [root]
        )
        for template in elements:
            parent = template.get("t-inherit")
            if parent and template.get("t-inherit-mode", "primary") == "extension":
                extensions[parent].extend(
                    (path, op) for op in template if isinstance(op.tag, str)
                )
            elif name := template.get("t-name"):
                definitions[name] = template
    return definitions, extensions


def unresolved_extensions(paths) -> list[str]:
    definitions, extensions = _index(paths)
    resolved: dict[str, etree._Element | None] = {}
    findings: list[str] = []

    def resolve(name: str, visiting: frozenset = frozenset()):
        if name in resolved:
            return resolved[name]
        template = definitions.get(name)
        if template is None or name in visiting:
            return None
        parent_name = template.get("t-inherit")
        if parent_name:
            parent = resolve(parent_name, visiting | {name})
            if parent is None:
                resolved[name] = None
                return None
            tree = copy.deepcopy(parent)
            for operation in template:
                if not isinstance(operation.tag, str):
                    continue
                where = f"{name}: t-inherit={parent_name!r}: {_describe(operation)}"
                if _locate(tree, operation) is None:
                    findings.append(f"{where} locates nothing")
                    continue
                tree, error = _apply(tree, operation)
                if error:
                    findings.append(f"{where} fails: {error}")
        else:
            tree = copy.deepcopy(template)
        # Extensions may target nodes another extension adds, and the browser
        # applies them in bundle order this gate cannot see; apply whatever
        # locates until nothing more does, and report only what never did.
        pending = list(extensions.get(name, ()))
        while pending:
            remaining = [(p, op) for p, op in pending if _locate(tree, op) is None]
            for path, operation in pending:
                if (path, operation) not in remaining:
                    tree, error = _apply(tree, operation)
                    if error:
                        findings.append(
                            f"{path}: t-inherit={name!r}: {_describe(operation)} "
                            f"fails: {error}"
                        )
            if len(remaining) == len(pending):
                break
            pending = remaining
        for path, operation in pending:
            findings.append(
                f"{path}: t-inherit={name!r}: {_describe(operation)} locates nothing"
            )
        resolved[name] = tree
        return tree

    for name in definitions:
        resolve(name)
    for parent, operations in extensions.items():
        if parent not in definitions:
            findings.extend(
                f"{path}: t-inherit={parent!r}: no template of that name"
                for path in {path for path, _op in operations}
            )
    return findings


@tagged("post_install", "-at_install")
class TestTemplateExtensions(lint_case.LintCase):
    def test_every_extension_locates_its_target(self):
        paths = [
            path
            for path in self.iter_module_files("*/static/src/*.xml")
            if "/static/src/lib/" not in path
        ]
        self.assert_ratchet(
            unresolved_extensions(paths),
            "lint_template_extension_target",
            "Owl template extension operation(s) whose target cannot be located",
            "The parent template changed shape under the extension: point the "
            "xpath at the node the parent renders now. The browser throws on "
            "first render, so no test but a tour opening that screen would see it.",
        )


class TestTemplateExtensionLookup(BaseCase):
    def _findings(self, xml: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory, "templates.xml")
            path.write_text(xml, encoding="utf-8")
            return unresolved_extensions([str(path)])

    def test_renamed_parent_node_is_reported(self):
        findings = self._findings(
            """<templates>
                <t t-name="p.Kanban"><ViewLayout><div class="o_kanban"/></ViewLayout></t>
                <t t-inherit="p.Kanban" t-inherit-mode="extension">
                    <xpath expr="//Layout" position="before"><div/></xpath>
                </t>
            </templates>"""
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("//Layout locates nothing", findings[0])

    def test_a_primary_child_operation_that_locates_nothing_is_reported(self):
        findings = self._findings(
            """<templates>
                <t t-name="p.Base"><t t-component="this.props.Renderer" model="this.model"/></t>
                <t t-name="p.Child" t-inherit="p.Base" t-inherit-mode="primary">
                    <t model="model" position="after"><div/></t>
                </t>
            </templates>"""
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("p.Child", findings[0])

    def test_an_operation_the_engine_refuses_is_reported(self):
        findings = self._findings(
            """<templates>
                <t t-name="p.Row"><td class="name"/></t>
                <t t-inherit="p.Row" t-inherit-mode="extension">
                    <xpath expr="//td" position="attributes">
                        <t t-if="ok"><attribute name="class" add="more" separator=" "/></t>
                    </xpath>
                </t>
            </templates>"""
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("//td fails: Invalid element <t>", findings[0])

    def test_hasclass_matches_like_the_browser(self):
        self.assertFalse(
            self._findings(
                """<templates>
                    <t t-name="p.Screen"><div class="subpads d-flex flex-column"/></t>
                    <t t-inherit="p.Screen" t-inherit-mode="extension">
                        <xpath expr="//div[hasclass('subpads', 'd-flex')]" position="attributes">
                            <attribute name="t-if">ok</attribute>
                        </xpath>
                    </t>
                </templates>"""
            )
        )

    def test_extension_may_target_what_another_extension_added(self):
        self.assertFalse(
            self._findings(
                """<templates>
                    <t t-name="p.Form"><div class="o_form"/></t>
                    <t t-inherit="p.Form" t-inherit-mode="extension">
                        <xpath expr="//span[hasclass('added')]" position="inside"><b/></xpath>
                    </t>
                    <t t-inherit="p.Form" t-inherit-mode="extension">
                        <xpath expr="//div[hasclass('o_form')]" position="inside">
                            <span class="added"/>
                        </xpath>
                    </t>
                </templates>"""
            )
        )

    def test_primary_child_sees_parent_extensions(self):
        self.assertFalse(
            self._findings(
                """<templates>
                    <t t-name="p.Base"><div class="root"/></t>
                    <t t-inherit="p.Base" t-inherit-mode="extension">
                        <xpath expr="//div[hasclass('root')]" position="inside"><i class="icon"/></xpath>
                    </t>
                    <t t-name="p.Child" t-inherit="p.Base" t-inherit-mode="primary">
                        <xpath expr="//i[hasclass('icon')]" position="replace"><em/></xpath>
                    </t>
                </templates>"""
            )
        )
