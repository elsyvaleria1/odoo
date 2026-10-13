from __future__ import annotations

import re
from collections.abc import Callable

from lxml import etree

from odoo.libs.debug_log import DebugLog
from odoo.libs.xml import (
    SKIPPED_ELEMENT_TYPES,
    apply_inheritance_specs,
    is_locator_attribute,
    locate_node,
)

from .arch import from_arch, to_arch
from .node import COMMENT, PROCESSING_INSTRUCTION, Node
from .patch import Applied, AttrChange, Move, Op, Patch, apply_one

POSITIONS: dict[str, Op] = {
    "inside": "inside",
    "before": "before",
    "after": "after",
    "attributes": "attributes",
}
REPLACE_MODES: dict[str, Op] = {"outer": "replace", "inner": "replace_inner"}

_debug = DebugLog(__name__)

ApplyXml = Callable[[etree._Element, etree._Element], etree._Element]


def combine_specs(
    state: Applied,
    specs_tree: etree._Element,
    origin: str | None = None,
    apply_xml: ApplyXml = apply_inheritance_specs,
) -> tuple[int, int]:
    work = _Working(state)
    specs = _flatten(specs_tree)
    patches = 0
    for spec in specs:
        patch = _translate(work, spec, origin)
        reason = "unnamed"
        if patch is not None:
            try:
                apply_one(state, patch, work.addresses())
            except ValueError as e:
                patch = None
                reason = f"refused:{type(e).__name__}"
            else:
                patches += 1
                work.invalidate()
        if patch is None:
            _debug.logic(
                "combine_specs.xml_way",
                origin=origin,
                spec=spec.tag,
                expr=spec.get("expr"),
                position=spec.get("position", "inside"),
                reason=reason,
            )
            work.apply_xml(spec, apply_xml, origin)
    _debug.pipeline("combine_specs", origin=origin, specs=len(specs), patches=patches)
    return patches, len(specs)


def _flatten(specs_tree: etree._Element) -> list[etree._Element]:
    specs = [specs_tree] if specs_tree.tag != "data" else list(specs_tree)
    flat: list[etree._Element] = []
    while specs:
        spec = specs.pop(0)
        if isinstance(spec, SKIPPED_ELEMENT_TYPES):
            continue
        if spec.tag == "data":
            specs[0:0] = list(spec)
            continue
        flat.append(spec)
    return flat


SIMPLE_XPATH = re.compile(
    r"^//(?P<tag>[A-Za-z_][\w.-]*)"
    r"(?:\[@(?P<attr>[A-Za-z_][\w.-]*)=(?P<q>['\"])(?P<value>[^'\"]*)(?P=q)\])?$"
)


class _Working:
    def __init__(self, state: Applied) -> None:
        self.state = state
        self._arch: etree._Element | None = None
        self._nodes: dict[etree._Element, Node] | None = None
        self._named: dict[tuple[str, str], Node] | None = None
        self._handles: dict[str, Node] = {}

    @property
    def root(self) -> Node:
        return self.state.root

    def invalidate(self) -> None:
        self._arch = None
        self._nodes = None
        self._named = None
        self._handles = {}

    def address(self, node: Node) -> str:
        handle = f"~{id(node)}"
        self._handles[handle] = node
        return handle

    def addresses(self) -> dict[str, Node]:
        return self._handles

    def named(self) -> dict[tuple[str, str], Node]:
        if self._named is None:
            self._named = {}
            for _path, node in self.root.walk():
                if name := node.attrs.get("name"):
                    self._named.setdefault((node.kind, name), node)
        return self._named

    def locate(self, spec: etree._Element) -> Node | None:
        tag, attr, value = _simple_target(spec)
        if tag is not None:
            if attr == "name" and value:
                return self.named().get((tag, value))
            if attr is None:
                return next(self.root.get_nodes_of_kind(tag), None)
            return next(
                (
                    node
                    for node in self.root.get_nodes_of_kind(tag)
                    if node.attrs.get(attr) == value
                ),
                None,
            )
        target = locate_node(self.arch(), spec)
        return None if target is None else self.node_of(target)

    def arch(self) -> etree._Element:
        if self._arch is None:
            self._arch = to_arch(self.root)
            self._nodes = self._nodes_of(self._arch)
        return self._arch

    def _nodes_of(self, arch: etree._Element) -> dict[etree._Element, Node]:
        elements = list(arch.iter())
        nodes = [node for _path, node in self.root.walk()]
        return dict(zip(elements, nodes, strict=True))

    def node_of(self, element: etree._Element) -> Node:
        self.arch()
        assert self._nodes is not None
        return self._nodes[element]

    def apply_xml(
        self, spec: etree._Element, apply_xml: ApplyXml, origin: str | None
    ) -> None:
        arch = self.arch()
        assert self._nodes is not None
        kept = self._nodes
        arch = apply_xml(arch, spec)
        self.state.root = from_arch(arch)
        self.invalidate()
        rebuilt: dict[int, Node] = {}
        for element, node in self._nodes_of(arch).items():
            if (previous := kept.get(element)) is None:
                node.origin = origin
            else:
                node.origin = previous.origin
                rebuilt[id(previous)] = node
        state = self.state
        state.managed = {
            (id(rebuilt[key]), attribute): (rebuilt[key], setter)
            for (key, attribute), (_node, setter) in state.managed.items()
            if key in rebuilt
        }
        for conflict in state.conflicts:
            conflict.node = rebuilt.get(id(conflict.node), conflict.node)


def _simple_target(
    spec: etree._Element,
) -> tuple[str | None, str | None, str | None]:
    if spec.tag != "xpath":
        attrs = [
            (k, v) for k, v in spec.attrib.items() if is_locator_attribute(spec, k)
        ]
        if spec.tag == "field":
            return "field", "name", spec.get("name")
        if not attrs:
            return spec.tag, None, None
        if len(attrs) == 1:
            return spec.tag, attrs[0][0], attrs[0][1]
        return None, None, None
    match = SIMPLE_XPATH.match((spec.get("expr") or "").strip())
    if not match:
        return None, None, None
    return match.group("tag"), match.group("attr"), match.group("value")


def _translate(
    work: _Working, spec: etree._Element, origin: str | None
) -> Patch | None:
    position = spec.get("position", "inside")
    op = (
        REPLACE_MODES.get(spec.get("mode", "outer"))
        if position == "replace"
        else POSITIONS.get(position)
    )
    if op is None:
        return None
    target_node = work.locate(spec)
    if target_node is None:
        return None
    target_id = work.address(target_node)
    if op == "attributes":
        changes = []
        for attribute in spec:
            if not isinstance(attribute.tag, str):
                continue
            name = attribute.get("name")
            if (
                attribute.tag != "attribute"
                or not name
                or any(
                    key not in ("name", "add", "remove", "separator")
                    and not key.startswith("data-oe-")
                    for key in attribute.attrib
                )
                or (
                    (attribute.get("add") or attribute.get("remove")) and attribute.text
                )
            ):
                return None
            changes.append(
                AttrChange(
                    name,
                    value=None
                    if attribute.get("add") or attribute.get("remove")
                    else (attribute.text or ""),
                    add=attribute.get("add", ""),
                    remove=attribute.get("remove", ""),
                    separator=attribute.get("separator"),
                )
            )
        return Patch(op, target_id, attributes=tuple(changes), origin=origin)
    elements = [child for child in spec if isinstance(child.tag, str)]
    if any(child.get("position") == "move" for child in elements[1:]):
        return None
    text = spec.text
    content: list[Node | Move] = []
    for child in spec:
        if not isinstance(child.tag, str):
            if isinstance(child, etree._Comment | etree._ProcessingInstruction):
                if op == "replace" and not content:
                    return None
                content.append(
                    Node(
                        COMMENT,
                        text=child.text,
                        tail=child.tail,
                        line=child.sourceline,
                    )
                    if isinstance(child, etree._Comment)
                    else Node(
                        PROCESSING_INSTRUCTION,
                        attrs={"target": child.target},
                        text=child.text,
                        tail=child.tail,
                        line=child.sourceline,
                    )
                )
            elif child.tail:
                return None
            continue
        if child.get("position") == "move":
            moved = work.locate(child)
            if moved is None or len(child):
                return None
            content.append(Move(work.address(moved), tail=child.tail))
            continue
        node = _content_node(child, op)
        if node is None:
            return None
        content.append(node)
    return Patch(op, target_id, content=tuple(content), origin=origin, text=text)


def _content_node(element: etree._Element, op: str) -> Node | None:
    node = from_arch(element)
    if not _place_dollar_zero(node, op):
        return None
    return node


def _place_dollar_zero(node: Node, op: str) -> bool:
    if node.text is not None and "$0" in node.text:
        if node.text != "$0" or op != "replace":
            return False
        node.text = None
        node.children.insert(0, Node("$0"))
    for child in node.children:
        if child.tail and "$0" in child.tail:
            return False
        if not _place_dollar_zero(child, op):
            return False
    return True
