from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal, NamedTuple

from odoo.libs.xml import is_layout_whitespace, merge_attribute_value

from .node import Node

Op = Literal["replace", "replace_inner", "before", "after", "inside", "attributes"]


_INDENTATION = re.compile(r"\n[ \t]*$")


class PatchError(ValueError):
    pass


class _NodeLocation(NamedTuple):
    parent: Node
    child_index: int


@dataclass(frozen=True, slots=True)
class Move:
    target: str
    tail: str | None = None


@dataclass(frozen=True, slots=True)
class AttrChange:
    name: str
    value: str | None = None
    add: str = ""
    remove: str = ""
    separator: str | None = None


@dataclass(frozen=True, slots=True)
class Patch:
    op: Op
    target: str
    content: tuple[Node | Move, ...] = ()
    attributes: tuple[AttrChange, ...] = ()
    origin: str | None = None
    text: str | None = None


@dataclass(slots=True)
class Conflict:
    node: Node
    attribute: str
    origins: tuple[str | None, str | None]


@dataclass(slots=True)
class Applied:
    root: Node
    managed: dict[tuple[int, str], tuple[Node, str | None]] = field(
        default_factory=dict
    )
    conflicts: list[Conflict] = field(default_factory=list)

    def setter(self, node: Node, attribute: str) -> str | None:
        managed = self.managed.get((id(node), attribute))
        return node.origin if managed is None else managed[1]


def _get_parent_and_child_index(root: Node, target: Node) -> _NodeLocation:
    for _path, node in root.walk():
        for index, child in enumerate(node.children):
            if child is target:
                return _NodeLocation(node, index)
    raise PatchError(f"node {target.id!r} has no parent")


def _stamp(nodes: Iterable[Node], origin: str | None) -> None:
    for node in nodes:
        for _path, descendant in node.walk():
            if descendant.origin is None:
                descendant.origin = origin


def apply_one(result: Applied, patch: Patch, ids: dict[str, Node]) -> None:
    target = ids.get(patch.target)
    if target is None:
        raise PatchError(
            f"patch {patch.op!r} from {patch.origin!r}: no node {patch.target!r}"
        )
    if patch.op == "attributes":
        _apply_attributes(result, target, patch)
        return
    if target is result.root and patch.op not in ("inside", "replace_inner"):
        if patch.op != "replace":
            raise PatchError("only `replace` applies to the root")
        if len(patch.content) != 1:
            raise PatchError("replacing the root takes exactly one node")
    _check_moves(ids, patch, target)
    placed = _place(patch, target)
    if patch.op in ("inside", "before"):
        parent, index = (
            (target, len(target.children))
            if patch.op == "inside"
            else _get_parent_and_child_index(result.root, target)
        )
        trailing = _update_text_and_get_trailing_whitespace(
            parent, index, patch.text, bool(patch.content)
        )
        content = _materialise(result.root, ids, placed)
        index = (
            len(target.children)
            if patch.op == "inside"
            else _get_child_index(parent, target)
        )
        _insert_nodes_with_tail(parent, index, content, trailing)
        return
    if patch.op == "replace" and target is not result.root:
        parent, index = _get_parent_and_child_index(result.root, target)
        empty = _is_empty(patch)
        if not is_layout_whitespace(patch.text):
            _append_text(parent, index, patch.text)
        content = _materialise(result.root, ids, placed)
        _replace_node(parent, _get_child_index(parent, target), content, empty)
        return
    content = _materialise(result.root, ids, placed)
    if patch.op == "replace_inner":
        target.children = []
        target.text = None
        _insert(target, 0, content, patch.text)
    elif target is result.root:
        result.root = content[0]
        result.root.tail = None
        if "t-name" in target.attrs and "t-name" not in result.root.attrs:
            result.root.attrs["t-name"] = target.attrs["t-name"]
    else:
        parent, index = _get_parent_and_child_index(result.root, target)
        following = target.tail
        target.tail = None
        _insert(parent, index + 1, content, patch.text)
        last = content[-1] if content else target
        last.tail = (last.tail or "") + (following or "") or None


def _get_child_index(parent: Node, child: Node) -> int:
    return next(i for i, node in enumerate(parent.children) if node is child)


def _append_text(parent: Node, index: int, text: str | None) -> None:
    if not text:
        return
    if index:
        previous = parent.children[index - 1]
        previous.tail = (previous.tail or "") + text
    else:
        parent.text = (parent.text or "") + text


def _is_empty(patch: Patch) -> bool:
    return (
        all(isinstance(item, Node) and item.is_markup for item in patch.content)
        and not "".join(
            [patch.text or "", *(item.tail or "" for item in patch.content)]
        ).strip()
    )


def _replace_node(parent: Node, index: int, content: list[Node], empty: bool) -> None:
    target = parent.children[index]
    parent.children[index : index + 1] = content
    if content and is_layout_whitespace(content[-1].tail):
        content[-1].tail = None
    if not (empty and is_layout_whitespace(target.tail)):
        _append_text(parent, index + len(content), target.tail)


def _insert(parent: Node, index: int, content: list[Node], text: str | None) -> None:
    _insert_nodes_with_tail(
        parent,
        index,
        content,
        _update_text_and_get_trailing_whitespace(parent, index, text, bool(content)),
    )


def _update_text_and_get_trailing_whitespace(
    parent: Node, index: int, text: str | None, has_content: bool
) -> str:
    if index:
        previous = parent.children[index - 1]
        before = previous.tail or ""
    else:
        before = parent.text or ""
    indentation = _INDENTATION.search(before)
    trailing = indentation.group(0) if indentation else ""
    if not has_content:
        text = (text or "").rstrip() + trailing
    joined = before.rstrip() + (text or "")
    if index:
        parent.children[index - 1].tail = joined or None
    else:
        parent.text = joined or None
    return trailing


def _insert_nodes_with_tail(
    parent: Node, index: int, content: list[Node], trailing: str
) -> None:
    parent.children[index:index] = content
    if content:
        last = content[-1]
        last.tail = ((last.tail or "").rstrip() + trailing) or None


def _check_moves(ids: dict[str, Node], patch: Patch, target: Node) -> None:
    for item in patch.content:
        if not isinstance(item, Move):
            continue
        moved = ids.get(item.target)
        if moved is None:
            raise PatchError(
                f"patch {patch.op!r} from {patch.origin!r}: "
                f"nothing to move at {item.target!r}"
            )
        if _is_within_subtree(target, moved):
            raise PatchError(
                f"patch {patch.op!r} from {patch.origin!r}: "
                f"{item.target!r} cannot move into itself"
            )


def _is_within_subtree(node: Node, ancestor: Node) -> bool:
    return any(descendant is node for _path, descendant in ancestor.walk())


def _place(patch: Patch, target: Node) -> list[Node | Move]:
    _stamp((item for item in patch.content if isinstance(item, Node)), patch.origin)
    return [
        item if isinstance(item, Move) else _place_target(item, patch, target)
        for item in patch.content
    ]


def _materialise(
    root: Node, ids: dict[str, Node], placed: list[Node | Move]
) -> list[Node]:
    content: list[Node] = []
    for item in placed:
        if isinstance(item, Node):
            content.append(item)
            continue
        moved = ids[item.target]
        parent, index = _get_parent_and_child_index(root, moved)
        _leave_tail(parent, index)
        del parent.children[index]
        moved.tail = item.tail
        content.append(moved)
    return content


def _leave_tail(parent: Node, index: int) -> None:
    tail = parent.children[index].tail
    if not tail:
        return
    if index:
        previous = parent.children[index - 1]
        previous.tail = (previous.tail or "") + tail
    else:
        parent.text = (parent.text or "").rstrip() + tail


def _place_target(node: Node, patch: Patch, target: Node) -> Node:
    if node.kind == "$0":
        if patch.op != "replace":
            raise PatchError("`$0` stands for the replaced node only")
        replica = copy.deepcopy(target)
        replica.tail = None
        return replica
    node.children = [_place_target(child, patch, target) for child in node.children]
    return node


def _apply_attributes(result: Applied, target: Node, patch: Patch) -> None:
    attrs = dict(target.attrs)
    for change in patch.attributes:
        if change.add or change.remove:
            if change.value:
                raise PatchError(
                    f"attribute {change.name!r}: add/remove and a value are exclusive"
                )
            value = merge_attribute_value(
                change.name,
                attrs.get(change.name, ""),
                change.add,
                change.remove,
                change.separator,
            )
        else:
            value = change.value or ""
        if value:
            attrs[change.name] = value
        else:
            attrs.pop(change.name, None)
    for change in patch.attributes:
        key = (id(target), change.name)
        previous = result.setter(target, change.name)
        if (
            key in result.managed
            and previous != patch.origin
            and not (change.add or change.remove)
        ):
            result.conflicts.append(
                Conflict(target, change.name, (previous, patch.origin))
            )
        result.managed[key] = (target, patch.origin)
    target.attrs = attrs
