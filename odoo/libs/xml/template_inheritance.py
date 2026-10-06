import collections
import copy
import functools
import itertools
import logging
import re
from typing import TYPE_CHECKING, Any

import markupsafe
from lxml import etree
from lxml.builder import E

from odoo.libs.debug_log import DebugLog

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


class XPathExpressionError(ValueError):
    pass


__all__ = [
    "SKIPPED_ELEMENT_TYPES",
    "XPathExpressionError",
    "apply_inheritance_specs",
    "hasclass",
    "hoist_wrapped_attributes",
    "is_layout_whitespace",
    "is_locator_attribute",
    "locate_node",
    "merge_attribute_value",
]

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)
RSTRIP_REGEXP = re.compile(r"\n[ \t]*$")
_LAYOUT_RE = re.compile(r"[ \t\r\n]*\n[ \t\r\n]*")


def hasclass(context: Any, *classes: str) -> bool:
    return set(context.context_node.get("class", "").split()).issuperset(classes)


@functools.lru_cache(maxsize=1024)
def _compile_xpath(expr: str) -> etree.ETXPath:
    return etree.ETXPath(expr, extensions={(None, "hasclass"): hasclass})


SKIPPED_ELEMENT_TYPES = (
    etree._Comment,
    etree._ProcessingInstruction,
    etree._Entity,
)

_EXPRESSION_ATTRIBUTES = frozenset(
    {"readonly", "required", "invisible", "column_invisible", "t-if", "t-elif"}
)
_EXPRESSION_OPERATORS = ("and", "or", "&&", "||")
_ATTRIBUTE_KEYS = frozenset({"name", "add", "remove", "separator"})
_WHITESPACE_RE = re.compile(r"[ \t\n\r\f\v]+")
_WORD_CHAR_RE = re.compile(r"[A-Za-z0-9_$]")
_OPERATORS_TEXT = "'and', 'or', '&&' and '||'"


def _add_stripped_items_before(
    node: etree._Element,
    spec: etree._Element,
    extract: Callable[[etree._Element], etree._Element],
) -> None:
    prev = next(
        (
            n
            for n in node.itersiblings(preceding=True)
            if not (
                n.tag == etree.ProcessingInstruction
                and n.target == "apply-inheritance-specs-node-removal"
            )
        ),
        None,
    )
    parent = node.getparent()
    before = (parent.text if prev is None else prev.tail) or ""
    result = RSTRIP_REGEXP.search(before)
    before_text = result.group(0) if result else ""

    text = spec.text or ""
    if len(spec) > 0:
        spec[-1].tail = (spec[-1].tail or "").rstrip() + before_text
    else:
        text = text.rstrip() + before_text
    joined = (before.rstrip() + text) or None
    if prev is None:
        parent.text = joined
    else:
        prev.tail = joined

    for child in spec:
        if child.get("position") == "move":
            tail = child.tail
            child = extract(child)
            child.tail = tail
        node.addprevious(child)


def _add_text_before(
    node: etree._Element, text: str | None, *, strip_parent_text: bool = True
) -> None:
    if not text:
        return
    prev = node.getprevious()
    if prev is not None:
        prev.tail = (prev.tail or "") + text
    else:
        parent = node.getparent()
        before = parent.text or ""
        parent.text = (before.rstrip() if strip_parent_text else before) + text


def _remove_element(node: etree._Element) -> None:
    _add_text_before(node, node.tail)
    node.tail = None
    node.getparent().remove(node)


def locate_node(arch: etree._Element, spec: etree._Element) -> etree._Element | None:
    if spec.tag == "xpath":
        expr = spec.get("expr")
        if not expr:
            raise XPathExpressionError(
                "Invalid xpath specification: missing 'expr' attribute"
            )
        try:
            xPath = _compile_xpath(expr)
        except etree.XPathSyntaxError as e:
            raise XPathExpressionError(
                f'Invalid Expression while parsing xpath "{expr}"'
            ) from e
        nodes = xPath(arch)
        if not isinstance(nodes, list) or not all(
            isinstance(node, etree._Element) and isinstance(node.tag, str)
            for node in nodes
        ):
            _debug.logic(
                "template_inheritance.xpath_not_nodes",
                expr=expr,
                result=type(nodes).__name__,
            )
            raise XPathExpressionError(
                f'The xpath "{expr}" must select elements, not a value'
            )
        if len(nodes) > 1:
            _debug.logic(
                "template_inheritance.xpath_ambiguous", matches=len(nodes), expr=expr
            )
        return nodes[0] if nodes else None
    elif spec.tag == "field":
        for node in arch.iter("field"):
            if node.get("name") == spec.get("name"):
                return node
        return None

    wanted = [attr for attr in spec.attrib if is_locator_attribute(spec, attr)]
    for node in arch.iter(spec.tag):
        if all(node.get(attr) == spec.get(attr) for attr in wanted):
            return node
    return None


def is_locator_attribute(spec: etree._Element, attr: str) -> bool:
    if attr == "position" or attr.startswith(("data-oe-", "t-translation-context")):
        return False
    return not (attr == "mode" and spec.get("position") == "replace")


type _Extract = Callable[[etree._Element], etree._Element]


def is_layout_whitespace(text: str | None) -> bool:
    return bool(text and _LAYOUT_RE.fullmatch(text))


def _place_copies(spec: etree._Element, node: etree._Element, branding: bool) -> None:
    def replica() -> etree._Element:
        copied = copy.deepcopy(node)
        copied.tail = None
        if branding:
            copied.set("data-oe-no-branding", "1")
        return copied

    for loc in list(spec.iterdescendants()):
        if loc.text == "$0":
            loc.text = None
            loc.insert(0, replica())
        for child in list(loc):
            if child.tail == "$0":
                child.tail = None
                child.addnext(replica())


def _replace_in_place(
    spec: etree._Element,
    node: etree._Element,
    extract: _Extract,
    inherit_branding: bool,
) -> None:
    if inherit_branding and not node.get("data-oe-xpath"):
        node.addprevious(
            etree.ProcessingInstruction(
                "apply-inheritance-specs-node-removal", node.tag
            )
        )
    empty = (
        not any(isinstance(child.tag, str) for child in spec)
        and not "".join(
            [spec.text or "", *(child.tail or "" for child in spec)]
        ).strip()
    )
    if not is_layout_whitespace(spec.text):
        _add_text_before(node, spec.text, strip_parent_text=False)
    content = []
    for child in list(spec):
        if child.get("position") == "move":
            tail = child.tail
            child = extract(child)
            child.tail = tail
        node.addprevious(child)
        content.append(child)
    if content and is_layout_whitespace(content[-1].tail):
        content[-1].tail = None
    if not (empty and is_layout_whitespace(node.tail)):
        _add_text_before(node, node.tail, strip_parent_text=False)
    node.getparent().remove(node)


def _replace_outer(
    source: etree._Element,
    spec: etree._Element,
    node: etree._Element,
    extract: _Extract,
    inherit_branding: bool,
) -> etree._Element:
    _place_copies(spec, node, inherit_branding)
    if node.getparent() is not None:
        _replace_in_place(spec, node, extract, inherit_branding)
        return source

    elements = [content for content in spec if isinstance(content.tag, str)]
    if len(elements) != 1:
        _debug.logic(
            "template_inheritance.root_replace_refused",
            target=node.tag,
            elements=len(elements),
        )
        if not elements:
            raise ValueError(
                f"A replace of the root <{node.tag}> needs an element to put in its "
                "place, and this specification holds none."
            )
        raise ValueError(
            f"A replace of the root <{node.tag}> takes one element, and this "
            f"specification holds {len(elements)}."
        )
    spec_content = elements[0]
    comment = None
    for content in spec:
        if content is spec_content:
            break
        if content.tag is etree.Comment:
            comment = content
    if spec_content.get("position") == "move":
        spec_content = extract(spec_content)
    # a detached element stays in its old document, where an absolute xpath of
    # a later spec would resolve: the new root needs a document of its own
    source = copy.deepcopy(spec_content)
    source.tail = None
    if t_name := node.get("t-name"):
        source.set("t-name", t_name)
    if comment is not None:
        text = source.text
        source.text = None
        comment.tail = text
        source.insert(0, comment)
    return source


def _replace_inner(
    spec: etree._Element, node: etree._Element, extract: _Extract
) -> None:
    sentinel = E.sentinel()
    if len(node) > 0:
        node[0].addprevious(sentinel)
    else:
        node.append(sentinel)
    node.text = None
    _add_stripped_items_before(sentinel, spec, extract)
    for child in reversed(node):
        node.remove(child)
        if child == sentinel:
            break


def _scan(value: str) -> Iterator[tuple[int, int]]:
    depth = 0
    quote = ""
    index = 0
    while index < len(value):
        char = value[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = ""
        elif char in "'\"`":
            quote = char
        elif char in "([{":
            yield index, depth
            depth += 1
        elif char in ")]}":
            depth -= 1
            yield index, depth
        else:
            yield index, depth
        index += 1


def _is_word_char(value: str, index: int) -> bool:
    return 0 <= index < len(value) and bool(_WORD_CHAR_RE.match(value[index]))


def _split_operands(value: str, operator: str) -> list[str]:
    word = _is_word_char(operator, 0)
    operands = []
    start = 0
    for index, depth in _scan(value):
        if (
            depth == 0
            and index >= start
            and value.startswith(operator, index)
            and not (
                word
                and (
                    _is_word_char(value, index - 1)
                    or _is_word_char(value, index + len(operator))
                )
            )
        ):
            operands.append(value[start:index])
            start = index + len(operator)
    operands.append(value[start:])
    return operands


def _groups(value: str) -> Iterator[tuple[int, int]]:
    opened = None
    for index, depth in _scan(value):
        if value[index] == "(" and depth == 0:
            opened = index
        elif value[index] == ")" and depth == 0 and opened is not None:
            yield opened, index
            opened = None


def _normalize_operand(operand: str) -> str:
    operand = operand.strip()
    while operand.startswith("("):
        group = next(_groups(operand), None)
        if group != (0, len(operand) - 1):
            break
        operand = operand[1:-1].strip()
    return operand


def _remove_operands(
    value: str, target: list[str], operator: str, *, nested: bool
) -> str | None:
    operands = _split_operands(value, operator)
    normalized = [_normalize_operand(operand) for operand in operands]
    for index in range(len(operands) - len(target) + 1):
        if normalized[index : index + len(target)] == target:
            kept = operands[:index] + operands[index + len(target) :]
            if kept or not nested:
                return f" {operator} ".join(operand.strip() for operand in kept)
    for index, operand in enumerate(operands):
        for start, end in _groups(operand):
            inner = _remove_operands(
                operand[start + 1 : end], target, operator, nested=True
            )
            if inner is not None:
                operands[index] = f"{operand[: start + 1]}{inner}{operand[end:]}"
                return f" {operator} ".join(operand.strip() for operand in operands)
    return None


def _merge_expression(
    attribute: str, value: str, add: str, remove: str, separator: str | None
) -> str:
    if separator is None:
        raise ValueError(
            f"The expression attribute {attribute!r} needs a separator; "
            f"valid values are {_OPERATORS_TEXT}"
        )
    operator = separator.strip()
    if operator not in _EXPRESSION_OPERATORS:
        raise ValueError(
            f"Invalid separator {separator!r} for expression attribute "
            f"{attribute!r}; valid values are {_OPERATORS_TEXT}"
        )
    if remove:
        target = [
            _normalize_operand(operand) for operand in _split_operands(remove, operator)
        ]
        removed = _remove_operands(value, target, operator, nested=False)
        if removed is not None:
            value = removed
    if add:
        value = f"({value}) {operator} ({add})" if value else add
    return value


def _merge_list(value: str, add: str, remove: str, separator: str | None) -> str:
    if separator is None:
        separator = ","
    if separator.strip():
        joiner = separator

        def split(text: str) -> list[str]:
            return [part.strip() for part in text.split(separator)]

    else:
        joiner = " "

        def split(text: str) -> list[str]:
            return _WHITESPACE_RE.split(text)

    to_remove = set(split(remove))
    return joiner.join(
        itertools.chain(
            (part for part in split(value) if part and part not in to_remove),
            (part for part in split(add) if part),
        )
    )


def merge_attribute_value(
    attribute: str, current: str, add: str, remove: str, separator: str | None
) -> str:
    """The value ``attribute`` takes after an ``add``/``remove`` edit of
    ``current``: an expression joined by the separator's operator for the
    modifier, ``t-if``/``t-elif`` and ``decoration-*`` attributes, a separated
    list otherwise. One definition for the XML specs and the IR patches; the
    browser engine (``web/static/src/core/template_inheritance.js``) implements
    the same one, and ``web/static/tests/core/template_inheritance_cases.js``
    holds both to it."""
    if separator == "":
        raise ValueError(f"Invalid separator '' for attribute {attribute!r}")
    if attribute in _EXPRESSION_ATTRIBUTES or attribute.startswith("decoration-"):
        return _merge_expression(attribute, current, add, remove, separator)
    return _merge_list(current, add, remove, separator)


def hoist_wrapped_attributes(arch: etree._Element) -> bool:
    # an arch stored before c8bc61c298eb may wrap <attribute> in other
    # elements, which that engine read through and this one refuses: hoisting
    # every <attribute> to its spec keeps what the old engine applied
    changed = False
    specs = [node for node in arch.iter() if node.get("position") == "attributes"]
    for spec in specs:
        if all(
            child.tag == "attribute"
            for child in spec
            if not isinstance(child, SKIPPED_ELEMENT_TYPES)
        ):
            continue
        attributes = list(spec.iter("attribute"))
        for child in list(spec):
            spec.remove(child)
        spec.extend(attributes)
        changed = True
    return changed


def _apply_attributes(spec: etree._Element, node: etree._Element) -> None:
    for child in spec:
        if isinstance(child, SKIPPED_ELEMENT_TYPES):
            continue
        if child.tag != "attribute":
            raise ValueError(
                f'Invalid element <{child.tag}> in a position="attributes" '
                "specification; only <attribute> is allowed"
            )
        unknown = [
            key
            for key in child.attrib
            if key not in _ATTRIBUTE_KEYS and not key.startswith("data-oe-")
        ]
        if unknown:
            raise ValueError(
                f"Invalid attributes {', '.join(map(repr, unknown))} in element "
                f"<attribute>"
            )

        attribute = child.get("name")
        if not attribute:
            raise ValueError("Element <attribute> is missing its 'name' attribute")
        add = child.get("add", "")
        remove = child.get("remove", "")

        if add or remove:
            if child.text:
                raise ValueError(
                    f"Element <attribute> with 'add' or 'remove' cannot contain "
                    f"text {child.text!r}"
                )
            value = merge_attribute_value(
                attribute, node.get(attribute, ""), add, remove, child.get("separator")
            )
        else:
            value = child.text or ""

        if value:
            node.set(attribute, value)
        elif attribute in node.attrib:
            del node.attrib[attribute]


def _apply_around(
    spec: etree._Element,
    node: etree._Element,
    extract: _Extract,
    *,
    after: bool,
) -> None:
    sentinel = E.sentinel()
    if after:
        node.addnext(sentinel)
        if node.tail is not None:
            sentinel.tail = node.tail
            node.tail = None
    else:
        node.append(sentinel)
    _add_stripped_items_before(sentinel, spec, extract)
    _remove_element(sentinel)


def _prepare_unlocatable_error(spec: etree._Element) -> ValueError:
    attrs = "".join(
        f' {attr}="{markupsafe.escape(spec.get(attr))}"'
        for attr in spec.attrib
        if attr != "position"
    )
    return ValueError(f"Element '<{spec.tag}{attrs}>' cannot be located in parent view")


def apply_inheritance_specs(
    source: etree._Element,
    specs_tree: etree._Element | list[etree._Element],
    inherit_branding: bool = False,
) -> etree._Element:
    specs = collections.deque(
        specs_tree if isinstance(specs_tree, list) else [specs_tree]
    )

    def extract(spec: etree._Element) -> etree._Element:
        if len(spec):
            raise ValueError(
                f"Invalid specification for moved nodes: "
                f'"{etree.tostring(spec, encoding="unicode")}"'
            )
        to_extract = locate_node(source, spec)
        if to_extract is None:
            raise ValueError(
                f'Element "{etree.tostring(spec, encoding="unicode")}" cannot be '
                f"located in parent view"
            )
        if to_extract.getparent() is None:
            raise ValueError(
                f'Element "{etree.tostring(spec, encoding="unicode")}" is the root '
                f"of the parent view and cannot be moved"
            )
        _remove_element(to_extract)
        return to_extract

    applied = 0  # debuglog
    with _debug.perf("template_inheritance.specs", specs=len(specs)) as span:
        while specs:
            spec = specs.popleft()
            if isinstance(spec, SKIPPED_ELEMENT_TYPES):
                continue
            if spec.tag == "data":
                # a nested <data> applies where it stands, before its siblings
                specs.extendleft(reversed(spec))
                continue
            applied += 1  # debuglog

            node = locate_node(source, spec)
            if node is None:
                _debug.logic(
                    "template_inheritance.unlocatable",
                    spec_tag=spec.tag,
                    expr=spec.get("expr"),
                    position=spec.get("position", "inside"),
                )
                raise _prepare_unlocatable_error(spec)

            pos = spec.get("position", "inside")
            _debug.pipeline(
                "template_inheritance.apply",
                spec_tag=spec.tag,
                target=node.tag,
                position=pos,
                mode=spec.get("mode") if pos == "replace" else None,
                branding=inherit_branding,
            )
            if pos == "replace":
                mode = spec.get("mode", "outer")
                if mode == "outer":
                    source = _replace_outer(
                        source, spec, node, extract, inherit_branding
                    )
                elif mode == "inner":
                    _replace_inner(spec, node, extract)
                else:
                    raise ValueError(f'Invalid mode attribute: "{mode}"')
            elif pos == "attributes":
                _apply_attributes(spec, node)
            elif pos == "inside":
                _apply_around(spec, node, extract, after=False)
            elif pos in ("after", "before") and node.getparent() is None:
                _debug.logic("template_inheritance.root_sibling_refused", position=pos)
                raise ValueError(
                    f"Nothing can be placed {pos} the root <{node.tag}>: "
                    "an arch has one root element."
                )
            elif pos == "after":
                _apply_around(spec, node, extract, after=True)
            elif pos == "before":
                _add_stripped_items_before(node, spec, extract)
            else:
                raise ValueError(f"Invalid position attribute: '{pos}'")

        span.set(applied=applied)
    return source
