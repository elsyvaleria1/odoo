import ast
import base64
import functools
import hashlib
import logging
import math
import pprint
import re
import textwrap
import threading
import traceback
import urllib.parse
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence, Sized
from copy import deepcopy
from dataclasses import dataclass
from itertools import chain, count
from pathlib import Path
from types import FunctionType
from typing import Any, Literal, NamedTuple, NoReturn, Self

from dateutil.relativedelta import relativedelta
from lxml import etree
from markupsafe import Markup, escape
from psycopg.errors import TransactionRollback

from odoo import api, models, tools
from odoo.db.errors import PG_RECOVERABLE_EXCEPTIONS, PG_STALE_PLAN_EXCEPTIONS
from odoo.exceptions import UserError
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.libs.func import lazy
from odoo.libs.image import base64_image_subtype, image_data_uri
from odoo.libs.lru import LRU
from odoo.libs.text import VOID_ELEMENTS, escape_str
from odoo.modules import Manifest
from odoo.modules.registry import REGISTRY_CACHES
from odoo.tools import OrderedSet, config, frozendict, json, safe_eval
from odoo.tools.misc import file_open, file_path
from odoo.tools.profiler import ExecutionContext, QwebTracker
from odoo.tools.rendering_tools import (
    QWebError,
    QWebErrorInfo,
    restricted_binding_errors,
    restricted_expression_errors,
)
from odoo.tools.safe_eval import (
    _BLACKLIST,
    _BUILTINS,
    _EXPR_OPCODES,
    _SAFE_BUILTINS,
    check_code_object,
    guard_format_calls,
    to_opcodes,
)
from odoo.tools.translate import FORMAT_REGEX, is_translatable_attrib
from odoo.tools.urls import keep_query

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


_SAFE_QWEB_OPCODES = (
    _EXPR_OPCODES.union(
        to_opcodes(
            [
                "MAKE_FUNCTION",
                "CALL_FUNCTION_EX",
                "GET_ITER",
                "FOR_ITER",
                "YIELD_VALUE",
                "JUMP_FORWARD",
                "JUMP_BACKWARD",
                "POP_JUMP_IF_FALSE",
                "POP_JUMP_IF_TRUE",
                "LOAD_NAME",
                "LOAD_ATTR",
                "LOAD_FAST",
                "STORE_FAST",
                "UNPACK_SEQUENCE",
                "STORE_SUBSCR",
                "LOAD_GLOBAL",
                "EXTENDED_ARG",
                "CALL",
                "PUSH_NULL",
                "BUILD_STRING",
                "RETURN_GENERATOR",
                "END_FOR",
                "LOAD_FAST_AND_CLEAR",
                "POP_JUMP_IF_NOT_NONE",
                "POP_JUMP_IF_NONE",
                "RERAISE",
                "CALL_INTRINSIC_1",
                "STORE_SLICE",
                "CALL_KW",
                "LOAD_FAST_LOAD_FAST",
                "STORE_FAST_STORE_FAST",
                "STORE_FAST_LOAD_FAST",
                "CONVERT_VALUE",
                "FORMAT_SIMPLE",
                "FORMAT_WITH_SPEC",
                "SET_FUNCTION_ATTRIBUTE",
                "LOAD_FAST_BORROW",
                "POP_ITER",
                "LOAD_FAST_BORROW_LOAD_FAST_BORROW",
                "LOAD_COMMON_CONSTANT",
                "MAKE_CELL",
                "COPY_FREE_VARS",
                "LOAD_CLOSURE",
                "LOAD_DEREF",
                "STORE_DEREF",
            ]
        )
    )
    - _BLACKLIST
)


unsafe_eval = eval  # noqa: S307 -- Evaluator entry point; callers validate code and restrict the namespace.


FORBIDDEN_FIELD_TAGS = frozenset(
    [
        "table",
        "tbody",
        "thead",
        "tfoot",
        "tr",
        "td",
        "li",
        "ul",
        "ol",
        "dl",
        "dt",
        "dd",
    ]
)
ALLOWED_KEYWORD = frozenset(
    [
        "and",
        "as",
        "elif",
        "else",
        "for",
        "if",
        "in",
        "is",
        "not",
        "or",
    ]
    + list(_BUILTINS)
)
YIELD_LINE_REGEXP = re.compile(r"^\s*(?:yield|return)\b", re.MULTILINE)
BODY_INDENT_REGEXP = re.compile(r"^([ \t]+)\S", re.MULTILINE)
RSTRIP_REGEXP = re.compile(r"\n[ \t]*$")
LSTRIP_REGEXP = re.compile(r"^[ \t]*\n")
FIRST_RSTRIP_REGEXP = re.compile(r"^(\n[ \t]*)+(\n[ \t])")
VARNAME_REGEXP = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ELEMENT_MARKER_REGEXP = re.compile(r"\s*# element: (.*)")
TO_VARNAME_REGEXP = re.compile(r"[^A-Za-z0-9_]+")
SPECIAL_DIRECTIVES = {"t-translation", "t-ignore", "t-title"}
ETREE_REF = "etree._Element"
OUTPUT_DIRECTIVES = ("t-out", "t-field", "t-esc", "t-raw")
BOUND_NAME_TEMPLATE = "_qarg_%s"
T_CALL_SLOT = "0"

QWEB_MAX_RENDER_DEPTH = 50
RENDER_INTERNAL_PREFIXES = ("__qweb", "_qweb")
RENDER_PROCESS_OPTIONS = frozenset({"dev_mode"})

ETREE_TEMPLATE_REF = count()

XML_NAMESPACE_PREFIXES = frozendict({"http://www.w3.org/XML/1998/namespace": "xml"})

POST_PROCESSING_ATT_NAMES = frozenset(
    (
        "href",
        "src",
        "action",
        "formaction",
        "xlink:href",
        "data",
        "poster",
        "background",
        "cite",
        "ping",
        "longdesc",
        "codebase",
        "manifest",
    )
)

EXECUTABLE_URL_REGEXP = re.compile(
    r"(?:java|vb|live)script:"
    r"|data:(?:text/(?:html|xml|javascript|ecmascript)"
    r"|application/(?:xhtml\+?xml|xml|javascript|ecmascript))",
    re.IGNORECASE,
)
SVG_DATA_URL_REGEXP = re.compile(r"data:image/svg\+?xml", re.IGNORECASE)
IMAGE_ELEMENTS = frozenset(("img", "image", "input", "picture", "source", "video"))
HISTORY_BACK_URL_REGEXP = re.compile(
    r"javascript:(?:window\.)?history\.back\(\)", re.IGNORECASE
)
URL_IGNORED_CHARS = re.compile(r"[\s\x00-\x1f]+")
ATTRIBUTE_NAME_REGEXP = re.compile(r"[^\s\"'>/=\x00-\x1f\x7f-\x9f]+")


def _normalize_url_for_scheme_check(value: object) -> str:
    return URL_IGNORED_CHARS.sub("", urllib.parse.unquote_plus(str(value)))


def escape_text(text: str) -> str:
    if hasattr(text, "__html__"):
        return text.__html__()
    return escape_str(text)


def is_executable_url(value: object, tag_name: str) -> bool:
    url = _normalize_url_for_scheme_check(value)
    if HISTORY_BACK_URL_REGEXP.fullmatch(url):
        return False
    if EXECUTABLE_URL_REGEXP.match(url):
        return True
    return (
        SVG_DATA_URL_REGEXP.match(url) is not None
        and str(tag_name).lower() not in IMAGE_ELEMENTS
    )


def is_event_handler_attribute(name: object) -> bool:
    return str(name).lower().startswith("on")


class TemplateAttributeValue(str):
    __slots__ = ()


def srcdoc_value(value: Any) -> Markup:
    if hasattr(value, "__html__"):
        return Markup(value)
    return escape(to_text(value))


def mapping_value(value: Any) -> Mapping[Any, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, (list, tuple)) and value:
        if isinstance(value[0], (list, tuple)):
            return dict(value)
        return dict([value])
    return {}


def checked_attributes(computed: Any) -> dict[Any, Any]:
    attributes = {}
    for name, value in mapping_value(computed).items():
        if is_event_handler_attribute(name):
            _debug.logic("attribute_event_handler_dropped", attr=str(name)[:40])
            _logger.warning(
                "Dropped the event handler attribute %r computed while rendering: "
                "escaping cannot make a value safe as JavaScript",
                name,
            )
            continue
        attributes[name] = (
            srcdoc_value(value) if str(name).lower() == "srcdoc" else value
        )
    return attributes


def _checked_bindings(bindings: dict[Any, Any], directive: str) -> dict[Any, Any]:
    for name in bindings:
        if isinstance(name, str) and "__" in name:
            _debug.logic("binding_rejected", directive=directive, name=str(name)[:40])
            msg = f"{directive} value {name!r} is reserved for the renderer"
            raise ValueError(msg)
    return bindings


def checked_call_values(value: Any) -> dict[Any, Any]:
    return _checked_bindings(dict(mapping_value(value)), "t-call")


def checked_set_values(value: Any) -> dict[Any, Any]:
    return _checked_bindings(dict(value), "t-set")


def checked_render_options(
    options: Mapping[str, Any], source: str
) -> Mapping[str, Any]:
    for name in options:
        if isinstance(name, str) and (
            name.startswith(RENDER_INTERNAL_PREFIXES) or name in RENDER_PROCESS_OPTIONS
        ):
            _debug.logic("render_option_rejected", source=source, name=name[:40])
            msg = f"{source} option {name!r} is reserved for the renderer"
            raise ValueError(msg)
    return options


def checked_call_options(options: Mapping[str, Any]) -> Mapping[str, Any]:
    return checked_render_options(options, "t-call")


def _xmlns_attribute(prefix: str | None) -> str:
    return "xmlns" if prefix is None else f"xmlns:{prefix}"


def _id_or_xmlid(ref: str | int) -> str | int:
    return int(ref) if isinstance(ref, str) and ref.isdecimal() else ref


def to_text(value: Any) -> str:
    if value is None or value is False:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def indent_code(code: str, level: int) -> str:
    return textwrap.indent(textwrap.dedent(code).strip(), " " * 4 * level)


def block_code(lines: list[str], level: int) -> list[str]:
    if any(
        stripped and not stripped.startswith("#")
        for line in lines
        for stripped in (s.strip() for s in line.splitlines())
    ):
        return lines
    return [*lines, indent_code("pass", level)]


def format_attributes(attrs: Mapping[str, Any], *, strict: bool = True) -> str:
    name_html = _attribute_name_html if strict else _escaped_attribute_name
    return "".join(
        [
            f' {name_html(str(name))}="{escape_str(str(value))}"'
            for name, value in attrs.items()
            if value or isinstance(value, str)
        ]
    )


def _escaped_attribute_name(name: str) -> str:
    return str(escape(name))


@functools.lru_cache(maxsize=4096)
def _attribute_name_html(name: str) -> str:
    if not ATTRIBUTE_NAME_REGEXP.fullmatch(name):
        msg = f"Invalid attribute name {name!r}"
        raise ValueError(msg)
    return str(escape(name))


AUTHORING_DIRECTIVES = frozendict(
    {
        **dict.fromkeys(
            (
                "t-att",
                "t-elif",
                "t-esc",
                "t-foreach",
                "t-if",
                "t-lang",
                "t-options",
                "t-out",
                "t-raw",
                "t-value",
            ),
            "expression",
        ),
        **dict.fromkeys(("t-call", "t-valuef", "t-valuef.translate"), "format"),
        **dict.fromkeys(
            (
                "t-autoprefix",
                "t-call-assets",
                "t-consumed-options",
                "t-css",
                "t-debug",
                "t-else",
                "t-groups",
                "t-ignore",
                "t-inner-content",
                "t-js",
                "t-name",
                "t-tag-close",
                "t-tag-open",
                "t-title",
                "t-translation",
            ),
            "constant",
        ),
        "t-args": "mapping",
        "t-as": "binding",
        "t-field": "field",
        "t-set": "set",
    }
)
AUTHORING_DIRECTIVE_PREFIXES = (
    ("t-att-", "expression"),
    ("t-attf-", "format"),
    ("t-options-", "expression"),
)
COMPUTED_BINDING_PREFIX = "*"


def _directive_kind(name: str, directives: Mapping[str, str]) -> str | None:
    if kind := directives.get(name):
        return kind
    return next(
        (
            kind
            for prefix, kind in AUTHORING_DIRECTIVE_PREFIXES
            if name.startswith(prefix)
        ),
        None,
    )


def _authored_attributes(
    root: etree._Element,
) -> Iterator[tuple[bool | None, str, str]]:
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        parent = el.getparent()
        if (
            el.tag == "attribute"
            and parent is not None
            and parent.get("position") == "attributes"
        ):
            if name := el.get("name"):
                for value in (el.text, el.get("add")):
                    if value:
                        yield None, name, value
            continue
        is_call = "t-call" in el.attrib
        for name, value in el.attrib.items():
            yield is_call, name, value


def _parses_as_expression(value: str) -> bool:
    try:
        ast.parse(f"({value})", mode="eval")
    except SyntaxError:
        return False
    return True


def _format_expressions(value: str) -> Iterator[str]:
    for match in FORMAT_REGEX.finditer(value):
        yield match.group(1) or match.group(2)


def mapping_binding_names(expression: str) -> list[str]:
    try:
        node = ast.parse(f"({expression})", mode="eval").body
    except SyntaxError:
        node = None
    if isinstance(node, ast.Dict) and all(
        isinstance(key, ast.Constant) and isinstance(key.value, str)
        for key in node.keys
    ):
        return [key.value for key in node.keys]
    return [f"{COMPUTED_BINDING_PREFIX}{expression}"]


def iter_template_expressions(
    root: etree._Element, directives: Mapping[str, str] = AUTHORING_DIRECTIVES
) -> Iterator[str]:
    for is_call, name, value in _authored_attributes(root):
        match _directive_kind(name, directives):
            case "expression" | "mapping":
                yield value
            case "field":
                yield value.rpartition(".")[0]
            case "format":
                yield from _format_expressions(value)
            case "set" if value.lstrip().startswith("{"):
                yield value
            case None if is_call is not False and not name.startswith("t-"):
                if name.endswith((".f", ".translate")):
                    yield from _format_expressions(value)
                elif is_call or _parses_as_expression(value):
                    yield value


def iter_template_bindings(
    root: etree._Element, directives: Mapping[str, str] = AUTHORING_DIRECTIVES
) -> Iterator[str]:
    for is_call, name, value in _authored_attributes(root):
        match _directive_kind(name, directives):
            case "set" if value.lstrip().startswith("{"):
                yield from mapping_binding_names(value)
            case "set" | "binding":
                yield value
            case "mapping":
                yield from mapping_binding_names(value)
            case None if is_call is not False and not name.startswith("t-"):
                yield name.removesuffix(".f").removesuffix(".translate")


def _trust_value(name: str, value: str, el: etree._Element) -> str:
    if name.endswith(".translate") or (
        name.startswith("t-attf-") and is_translatable_attrib(name, el)
    ):
        return "".join(f"{{{{{expr}}}}}" for expr in sorted(_format_expressions(value)))
    return value


def _is_evaluated_attribute(name: str, el: etree._Element) -> bool:
    return name.startswith("t-") or name == "groups" or "t-call" in el.attrib


def _trust_skeleton(el: etree._Element) -> list[tuple]:
    children = [
        node
        for child in el
        if isinstance(child.tag, str)
        for node in _trust_skeleton(child)
    ]
    spec = el.tag in ("xpath", "attribute") or "position" in el.attrib
    attributes = tuple(
        sorted(
            (name, _trust_value(name, value, el))
            for name, value in el.attrib.items()
            if spec or _is_evaluated_attribute(name, el)
        )
    )
    if not (attributes or spec):
        return children
    text = (
        _trust_value(el.get("name", ""), el.text or "", el)
        if el.tag == "attribute"
        else None
    )
    return [(el.tag, attributes, text, tuple(children))]


def trust_digest(*parts: object) -> str:
    return hashlib.sha256(repr(parts).encode()).hexdigest()


def template_trust_digest(root: etree._Element, *context: str) -> str:
    return trust_digest(*context, _trust_skeleton(root))


TEMPLATE_REF = "__template_ref__"


class TemplateContext(NamedTuple):
    directives: tuple[tuple[str, str], ...]
    ancestors: tuple[tuple[str | None, tuple[tuple[str, str], ...]], ...]
    conditions: tuple[tuple[str | None, tuple[tuple[str, str], ...]], ...]
    bindings: tuple[tuple[str | None, tuple[str, ...] | None], ...]
    body: tuple[str, ...]
    parameters: tuple[tuple[str | None, tuple[str, ...] | None], ...]


def evaluated_attributes(el: etree._Element) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (name, value)
            for name, value in el.attrib.items()
            if name != TEMPLATE_REF and _is_evaluated_attribute(name, el)
        )
    )


def _read_names(
    el: etree._Element, directives: Mapping[str, str]
) -> frozenset[str] | None:
    if any(name.startswith("t-call") for name in el.attrib):
        return None
    names: set[str] = set()
    for expression in iter_template_expressions(
        etree.Element(el.tag, dict(el.attrib)), directives
    ):
        try:
            tree = ast.parse(f"({expression})", mode="eval")
        except SyntaxError:
            return None
        names.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
    return frozenset(names)


def _set_names(el: etree._Element) -> tuple[str, ...] | None:
    value = el.get("t-set", "")
    names = mapping_binding_names(value) if value.lstrip().startswith("{") else [value]
    if any(name.startswith(COMPUTED_BINDING_PREFIX) for name in names):
        return None
    return tuple(names)


def _is_set(el: etree._Element) -> bool:
    return isinstance(el.tag, str) and "t-set" in el.attrib


def _binding(el: etree._Element) -> tuple[str | None, tuple[str, ...] | None]:
    return el.get(TEMPLATE_REF), _set_names(el)


def _conditions(el: etree._Element) -> list[tuple[str | None, tuple]]:
    conditions = []
    if "t-elif" in el.attrib or "t-else" in el.attrib:
        previous = el.getprevious()
        while previous is not None:
            if isinstance(previous.tag, str):
                conditions.append(
                    (previous.get(TEMPLATE_REF), evaluated_attributes(previous))
                )
                if "t-elif" not in previous.attrib:
                    break
            previous = previous.getprevious()
    return conditions


def template_contexts(
    root: etree._Element, directives: Mapping[str, str] = AUTHORING_DIRECTIVES
) -> dict[str, list[tuple[TemplateContext, etree._Element]]]:
    contexts: dict[str, list[tuple[TemplateContext, etree._Element]]] = defaultdict(
        list
    )
    ancestors: list[tuple[str | None, tuple[tuple[str, str], ...]]] = []
    loops: list[etree._Element] = []
    bindings_of = {el: _binding(el) for el in root.iter() if _is_set(el)}
    loop_sets: dict[etree._Element, list[etree._Element]] = {}
    bound: list[etree._Element] = []

    def sets_in(loop: etree._Element) -> list[etree._Element]:
        if loop not in loop_sets:
            loop_sets[loop] = [el for el in loop.iter() if el in bindings_of]
        return loop_sets[loop]

    def context(
        el: etree._Element, directives_of: tuple[tuple[str, str], ...]
    ) -> TemplateContext:
        reads = _read_names(el, directives)
        candidates = dict.fromkeys(
            [*bound, *(s for loop in loops for s in sets_in(loop))]
        )
        bindings = tuple(
            binding
            for candidate in candidates
            if (binding := bindings_of[candidate])[1] is None
            or reads is None
            or not reads.isdisjoint(binding[1])
        )
        body: tuple[str, ...] = ()
        if "t-set" in el.attrib:
            body = (
                el.text or "",
                *(etree.tostring(child, encoding="unicode") for child in el),
            )
        parameters: tuple[tuple[str | None, tuple[str, ...] | None], ...] = ()
        if "t-call" in el.attrib:
            parameters = tuple(
                bindings_of[child]
                for child in el.iter()
                if child is not el and child in bindings_of
            )
        return TemplateContext(
            directives_of,
            tuple(ancestors),
            tuple(_conditions(el)),
            bindings,
            body,
            parameters,
        )

    def visit(el: etree._Element) -> None:
        directives_of = evaluated_attributes(el)
        ref = el.get(TEMPLATE_REF)
        if ref is not None and directives_of:
            contexts[ref].append((context(el, directives_of), el))
        if directives_of:
            ancestors.append((ref, directives_of))
        is_loop = "t-foreach" in el.attrib
        if is_loop:
            loops.append(el)
        for child in el:
            if isinstance(child.tag, str):
                visit(child)
        if is_loop:
            loops.pop()
        if directives_of:
            ancestors.pop()
        if "t-set" in el.attrib:
            bound.append(el)

    visit(root)
    return contexts


def template_context_changes(
    served: etree._Element,
    trusted: etree._Element | None,
    directives: Mapping[str, str] = AUTHORING_DIRECTIVES,
) -> dict[str, tuple[str, str]]:
    served_contexts = template_contexts(served, directives)
    trusted_contexts = (
        template_contexts(trusted, directives) if trusted is not None else {}
    )
    changes = {}
    for ref in served_contexts.keys() | trusted_contexts.keys():
        now = served_contexts.get(ref, [])
        before = trusted_contexts.get(ref, [])
        delta = Counter(context for context, _el in now)
        delta.subtract(context for context, _el in before)
        if not any(delta.values()):
            continue
        if len(now) != len(before):
            how = "removed" if len(now) < len(before) else "added"
        else:
            new = next(context for context, count in delta.items() if count > 0)
            old = next(context for context, count in delta.items() if count < 0)
            if old.directives != new.directives:
                how = "directives"
            elif (old.ancestors, old.conditions) != (new.ancestors, new.conditions):
                how = "placed"
            else:
                how = "bindings"
        element = (now or before)[0][1]
        label = " ".join(
            [
                element.tag,
                *(f'{name}="{value}"' for name, value in evaluated_attributes(element)),
            ]
        )
        changes[ref] = (how, f"<{textwrap.shorten(label, 120)}>")
    return changes


def _unknown_directives(
    root: etree._Element, directives: Mapping[str, str] = AUTHORING_DIRECTIVES
) -> Iterator[str]:
    for _is_call, name, _value in _authored_attributes(root):
        if name.startswith("t-") and _directive_kind(name, directives) is None:
            yield name


def template_binding_errors(name: str) -> list[str]:
    if name.startswith(COMPUTED_BINDING_PREFIX):
        return ["a template must spell out the names it binds"]
    return restricted_binding_errors(name)


def restricted_template_errors(
    root: etree._Element, directives: Mapping[str, str] = AUTHORING_DIRECTIVES
) -> list[str]:
    errors = [
        f"{name}: the directive is not available"
        for name in dict.fromkeys(_unknown_directives(root, directives))
    ]
    errors += [
        f"{binding}: {error}"
        for binding in dict.fromkeys(iter_template_bindings(root, directives))
        for error in template_binding_errors(binding)
    ]
    errors += [
        f"{expression}: {'; '.join(refused)}"
        for expression in dict.fromkeys(iter_template_expressions(root, directives))
        if (refused := restricted_expression_errors(expression))
    ]
    return errors


class ExpressionRewriter(ast.NodeTransformer):
    def __init__(self, raise_on_missing: bool) -> None:
        self.raise_on_missing = raise_on_missing
        self.scopes: list[set[str]] = []

    def _is_bound(self, name: str) -> bool:
        return any(name in scope for scope in self.scopes)

    def _resolve(self, node: ast.Name, *, walked_into: bool) -> ast.expr:
        name = node.id
        if self._is_bound(name):
            return ast.copy_location(
                ast.Name(BOUND_NAME_TEMPLATE % name, node.ctx), node
            )
        if name in ALLOWED_KEYWORD:
            return node
        values = ast.Name("values", ast.Load())
        key = ast.Constant(name)
        if walked_into or self.raise_on_missing:
            _debug.logic("compile_expr.name_resolved", name=name, strict=True)
            lookup: ast.expr = ast.Subscript(values, key, ast.Load())
        else:
            _debug.logic("compile_expr.name_resolved", name=name, strict=False)
            lookup = ast.Call(ast.Attribute(values, "get", ast.Load()), [key], [])
        return ast.copy_location(lookup, node)

    def visit_Name(self, node: ast.Name) -> ast.expr:
        return self._resolve(node, walked_into=False)

    def _visit_walked(self, node: ast.expr) -> ast.expr:
        if isinstance(node, ast.Name):
            return self._resolve(node, walked_into=True)
        return self.visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        node.value = self._visit_walked(node.value)
        return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.Subscript:
        node.value = self._visit_walked(node.value)
        node.slice = self.visit(node.slice)
        return node

    def visit_Call(self, node: ast.Call) -> ast.Call:
        node.func = self._visit_walked(node.func)
        node.args = [self.visit(arg) for arg in node.args]
        node.keywords = [self.visit(keyword) for keyword in node.keywords]
        return node

    def visit_NamedExpr(self, node: ast.NamedExpr) -> NoReturn:
        _debug.logic("compile_expr.rejected", reason="assignment")
        msg = "Assignment expressions are not allowed in QWeb expressions"
        raise SyntaxError(msg)

    def visit_Lambda(self, node: ast.Lambda) -> ast.Lambda:
        arguments = node.args
        arguments.defaults = [self.visit(default) for default in arguments.defaults]
        arguments.kw_defaults = [
            default if default is None else self.visit(default)
            for default in arguments.kw_defaults
        ]
        parameters = [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            *filter(None, (arguments.vararg, arguments.kwarg)),
        ]
        self.scopes.append({parameter.arg for parameter in parameters})
        for parameter in parameters:
            parameter.arg = BOUND_NAME_TEMPLATE % parameter.arg
        node.body = self.visit(node.body)
        self.scopes.pop()
        _debug.logic("compile_expr.lambda", args=len(parameters))
        return node

    def _visit_comprehension(
        self, node: ast.expr, results: tuple[str, ...]
    ) -> ast.expr:
        generators = node.generators
        generators[0].iter = self.visit(generators[0].iter)
        scope: set[str] = set()
        self.scopes.append(scope)
        for index, generator in enumerate(generators):
            if index:
                generator.iter = self.visit(generator.iter)
            scope.update(
                target.id
                for target in ast.walk(generator.target)
                if isinstance(target, ast.Name)
            )
            generator.target = self.visit(generator.target)
            generator.ifs = [self.visit(condition) for condition in generator.ifs]
        for field in results:
            setattr(node, field, self.visit(getattr(node, field)))
        self.scopes.pop()
        return node

    def visit_ListComp(self, node: ast.ListComp) -> ast.expr:
        return self._visit_comprehension(node, ("elt",))

    def visit_SetComp(self, node: ast.SetComp) -> ast.expr:
        return self._visit_comprehension(node, ("elt",))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> ast.expr:
        return self._visit_comprehension(node, ("elt",))

    def visit_DictComp(self, node: ast.DictComp) -> ast.expr:
        return self._visit_comprehension(node, ("key", "value"))


def check_dunder_identifiers(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        match node:
            case ast.Name(id=name) | ast.Attribute(attr=name) | ast.arg(arg=name):
                pass
            case ast.keyword(arg=str() as name):
                pass
            case _:
                continue
        if "__" in name:
            _debug.logic("compile_expr.rejected", reason="dunder_name", name=name)
            raise SyntaxError(
                f"Using variable names with '__' is not allowed: {name!r}"
            )


class QwebCallParameters(NamedTuple):
    context: dict[str, Any]
    view_ref: str | int
    method: FunctionType | str | None
    values: dict[str, Any] | None
    scope: bool | Literal["root"]
    directive: str
    path_xml: tuple[str | int, str, str] | None

    def __repr__(self) -> str:
        context = {k: v for k, v in self.context.items() if not k.startswith("_")}
        qweb_root_values = (self.values or {}).get("__qweb_root_values") or {}
        values = self.values and {
            k: v
            for k, v in self.values.items()
            if k not in ("__qweb_root_values", "__qweb_attrs__")
            if v is not qweb_root_values.get(k)
        }
        method = getattr(self.method, "__name__", self.method)
        return (
            f"<QwebCallParameters context={context!r} view_ref={self.view_ref!r}"
            f" method={method!r} values={values!r} scope={self.scope!r}"
            f" directive={self.directive!r} path_xml={self.path_xml!r}>"
        )


class QwebStackFrame(NamedTuple):
    params: QwebCallParameters
    qweb: IrQweb
    iterator: Iterable[str | QwebCallParameters | QwebContent]
    values: dict[str, Any]
    options: Mapping[str, Any] | None
    cache_signature: tuple
    location_only: bool = False

    def __repr__(self) -> str:
        return f"<QwebStackFrame {self.params!r}>"


class QwebContent:
    __qweb: IrQweb
    html: str | None
    params__: QwebCallParameters

    def __init__(self, qweb: IrQweb, params: QwebCallParameters) -> None:
        self.__qweb = qweb
        self.html = None
        self.params__ = params

    @property
    def qweb(self) -> IrQweb | None:
        qweb = self.__qweb
        thread_dbname = getattr(threading.current_thread(), "dbname", None)
        cr_dbname = qweb.env.cr.dbname
        if thread_dbname and cr_dbname and thread_dbname != cr_dbname:
            return None
        return qweb

    def __str__(self) -> str:
        if self.html is None:
            if self.qweb is None:
                return ""
            params = self.params__
            self.html = self.qweb._render_stack(params, params.values)
        return self.html

    def __repr__(self) -> str:
        return f"<QwebContent {self.params__!r}>"

    def __len__(self) -> int:
        return len(str(self))

    def __html__(self) -> str:
        return self.__str__()

    def __contains__(self, key: str) -> bool:
        return key in Markup(self)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return getattr(Markup(self), name)

    def __getitem__(self, key: int | slice) -> Any:
        return Markup(self)[key]

    def __eq__(self, other: object) -> bool:
        return Markup(self) == other

    def __ne__(self, other: object) -> bool:
        return Markup(self) != other

    def __lt__(self, other: Any) -> bool:
        return Markup(self) < other

    def __le__(self, other: Any) -> bool:
        return Markup(self) <= other

    def __gt__(self, other: Any) -> bool:
        return Markup(self) > other

    def __ge__(self, other: Any) -> bool:
        return Markup(self) >= other

    def __hash__(self) -> int:
        return hash(Markup(self))

    def __add__(self, other: Any) -> Markup:
        return Markup(self).__add__(other)

    def __radd__(self, other: Any) -> Markup:
        return Markup(self).__radd__(other)

    def __mod__(self, other: Any) -> Markup:
        return Markup(self).__mod__(other)

    def __rmod__(self, other: Any) -> Markup:
        return Markup(self).__rmod__(other)


class RenderScopedDict(dict):
    __slots__ = ()
    __hash__ = object.__hash__
    __eq__ = object.__eq__
    __ne__ = object.__ne__


class RenderScopedList(list):
    __slots__ = ()
    __hash__ = object.__hash__
    __eq__ = object.__eq__
    __ne__ = object.__ne__


class QwebJSON(json.JSON):
    def dumps(self, *args: Any, **kwargs: Any) -> str:
        prev_default = kwargs.pop("default", None)

        def default(obj: Any) -> Any:
            if isinstance(obj, QwebContent):
                return str(obj)
            if prev_default is not None:
                return prev_default(obj)
            raise TypeError(
                f"Object of type {type(obj).__name__} is not JSON serializable"
            )

        return super().dumps(*args, **kwargs, default=default)


qweb_json = QwebJSON()


@dataclass(slots=True)
class CompileContext:
    context: dict[str, Any]

    ref: str | int | None
    ref_name: str | None
    ref_xml: str | lazy | None
    template: int | str | etree._Element | None
    root: etree._ElementTree
    make_name: Callable[[str], str]
    template_functions: dict[str, list[str]]
    text_concat: list[str]
    nsmap: dict[str | None, str]
    directives: Iterator[str] | None = None
    element_path: str | None = None
    element_xml: str | None = None

    def get(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.context


class IrQweb(models.AbstractModel):
    _name = "ir.qweb"
    _description = "Qweb"

    @api.model
    def _render(
        self,
        template: int | str | etree._Element,
        values: dict[str, Any] | None = None,
        **options: Any,
    ) -> Markup:
        values = values.copy() if values else {}
        qweb = self._render_prepare(values, options)
        with _debug.perf(
            "render",
            cr=self.env.cr,
            template=template if isinstance(template, (int, str)) else "etree",
            lang=self.env.context.get("lang"),
        ) as span:
            html = qweb._render_prepared(template, values)
            span.set(chars=len(html))
        return html

    @api.model
    def _render_batch(
        self,
        template: int | str | etree._Element,
        shared_values: dict[str, Any] | None,
        varying_values: Iterable[dict[str, Any]],
        **options: Any,
    ) -> list[Markup]:
        shared = dict(shared_values) if shared_values else {}
        qweb = self._render_prepare(shared, options)
        results = []
        with _debug.perf(
            "render_batch",
            cr=self.env.cr,
            template=template if isinstance(template, (int, str)) else "etree",
        ) as span:
            for varying in varying_values:
                safe_eval.check_no_modules_in_values(varying)
                results.append(qweb._render_prepared(template, {**shared, **varying}))
            span.set(count=len(results))
        return results

    def _render_prepare(self, values: dict[str, Any], options: dict[str, Any]) -> Self:
        current_thread = threading.current_thread()
        execution_context_enabled = getattr(current_thread, "profiler_params", {}).get(
            "execution_context_qweb"
        )
        qweb_hooks = getattr(current_thread, "qweb_hooks", ())
        if execution_context_enabled or qweb_hooks:
            options["profile"] = True
            _debug.logic(
                "render.profile_enabled",
                execution_context=bool(execution_context_enabled),
                hooks=len(qweb_hooks),
            )

        if T_CALL_SLOT in values or 0 in values:
            _logger.warning(
                "values[0] should be unset when call the _render method and only set into the template."
            )
            _debug.logic("render.slot_value_dropped", reason="set_by_caller")
            values.pop(T_CALL_SLOT, None)
            values.pop(0, None)

        qweb = self.with_context(**options)._prepare_environment(values)
        compiled_cache = qweb.env.context.get("__qweb_compiled_cache")
        cache_shared = compiled_cache is not None
        if not cache_shared:
            compiled_cache = RenderScopedDict()
        render_depth = qweb.env.context.get("_qweb_render_depth")
        if render_depth is None:
            render_depth = RenderScopedList([0])
        qweb = qweb.with_context(
            __qweb_compiled_cache=compiled_cache,
            __qweb_loaded_codes=RenderScopedDict(),
            __qweb_loaded_options=RenderScopedDict(),
            _qweb_error_path_xml=RenderScopedList((None, None, None)),
            _qweb_render_depth=render_depth,
        )

        safe_eval.check_no_modules_in_values(values)
        _debug.pipeline(
            "render.prepared",
            cache_shared=cache_shared,
            values=len(values),
            options=sorted(options),
        )
        return qweb

    def _render_prepared(
        self, template: int | str | etree._Element, values: dict[str, Any]
    ) -> Markup:
        self.env.context["_qweb_error_path_xml"][:] = [None, None, None]

        root_values = values.copy()
        values["__qweb_root_values"] = root_values["__qweb_root_values"] = root_values

        params = QwebCallParameters(
            context={},
            view_ref=template,
            method=None,
            values=None,
            scope=False,
            directive="render",
            path_xml=None,
        )
        return Markup(self._render_stack(params, values))

    def _render_stack(self, params: QwebCallParameters, values: dict[str, Any]) -> str:
        view_ref = params.view_ref
        root_values = values["__qweb_root_values"]
        compiled_cache = self.env.context["__qweb_compiled_cache"]

        item = params._replace(context={}, values=None, scope=False, path_xml=None)
        stack = [
            QwebStackFrame(
                params,
                self,
                iter([item]),
                values,
                None,
                self._get_template_cache_signature(),
            )
        ]

        render_depth = self.env.context["_qweb_render_depth"]
        base_depth = render_depth[0]
        depth = base_depth + 1
        frame = stack[-1]
        out: list[str] = []
        append = out.append
        capturing: list[tuple[QwebContent, int, int]] = []
        try:
            while stack:
                render_depth[0] = depth
                if depth > QWEB_MAX_RENDER_DEPTH:
                    _debug.logic(
                        "render.recursion_exceeded",
                        depth=depth,
                        limit=QWEB_MAX_RENDER_DEPTH,
                    )
                    msg = "Qweb template infinite recursion"
                    raise RecursionError(msg)

                frame = stack[-1]

                for item in frame.iterator:
                    if isinstance(item, str):
                        append(item)
                        continue

                    if isinstance(item, QwebContent) and item.html is not None:
                        append(item.html)
                        continue

                    self._push_render_frame(
                        stack, frame, item, compiled_cache, root_values
                    )
                    depth += 1
                    if isinstance(item, QwebContent):
                        capturing.append((item, len(stack), len(out)))
                    break

                else:
                    if capturing and capturing[-1][1] == len(stack):
                        content, _stack_len, start = capturing.pop()
                        content.html = "".join(out[start:])
                    if not stack.pop().location_only:
                        depth -= 1

        except (
            TransactionRollback,
            *PG_RECOVERABLE_EXCEPTIONS,
            *PG_STALE_PLAN_EXCEPTIONS,
        ):
            raise

        except Exception as error:
            _debug.logic(
                "render_error",
                template=view_ref if isinstance(view_ref, (int, str)) else "etree",
                depth=len(stack),
                error=type(error).__name__,
            )
            self._wrap_render_error(error, stack, frame, view_ref)

        finally:
            render_depth[0] = base_depth

        return "".join(out)

    def _push_render_frame(
        self,
        stack: list[QwebStackFrame],
        frame: QwebStackFrame,
        item: Any,
        compiled_cache: dict[Any, Any],
        root_values: dict[str, Any],
    ) -> None:
        is_content = isinstance(item, QwebContent)
        params = item.params__ if is_content else item

        values = frame.values
        qweb = frame.qweb
        cache_signature = frame.cache_signature

        context_switched = bool(params.context) and not (
            params.context.items() <= qweb.env.context.items()
        )
        if context_switched:
            qweb = qweb.with_context(**params.context)
            cache_signature = qweb._get_template_cache_signature()

        if params.scope:
            if params.scope == "root":
                values = root_values
            values = values.copy()

        if params.values:
            values.update(params.values)

        _debug.pipeline(
            "render.frame_pushed",
            template=params.view_ref
            if isinstance(params.view_ref, int | str)
            else "etree",
            directive=params.directive,
            scope=params.scope,
            depth=len(stack),
            content=is_content,
            context_switched=context_switched,
        )

        iterator: Iterable[Any] = ()
        options = None
        try:
            render_template, options = self._resolve_render_template(
                qweb, params, compiled_cache, cache_signature
            )
            iterator = render_template(qweb, values)
        finally:
            if is_content and self.env.context["_qweb_error_path_xml"][1]:
                log_params = params._replace(
                    path_xml=tuple(self.env.context["_qweb_error_path_xml"])
                )
                stack.append(
                    QwebStackFrame(
                        log_params,
                        qweb,
                        (),
                        values,
                        options,
                        cache_signature,
                        location_only=True,
                    )
                )
            stack.append(
                QwebStackFrame(params, qweb, iterator, values, options, cache_signature)
            )

    @staticmethod
    def _resolve_render_template(
        qweb: IrQweb,
        params: QwebCallParameters,
        compiled_cache: dict[Any, Any],
        cache_signature: tuple,
    ) -> tuple[Any, Mapping[str, Any] | None]:
        if callable(params.method):
            _debug.logic("render.method_callable", directive=params.directive)
            return params.method, None

        compile_key = (params.view_ref, cache_signature)
        compiled = compiled_cache.get(compile_key)
        if compiled is None:
            compiled = qweb._compile(params.view_ref)
            compiled_cache[compile_key] = compiled
            _debug.perf.count(
                "render_compiled_memo_miss",
                template=params.view_ref
                if isinstance(params.view_ref, int | str)
                else "etree",
            )
        template_functions, def_name, options = compiled
        return template_functions[params.method or def_name], options

    def _wrap_render_error(
        self,
        error: Exception,
        stack: list[QwebStackFrame],
        frame: QwebStackFrame,
        view_ref: int | str | etree._Element,
    ) -> NoReturn:
        qweb_error_info = self._get_error_info(error, stack)
        if qweb_error_info.template is None and qweb_error_info.ref is None:
            qweb_error_info.ref = view_ref

        if hasattr(error, "qweb"):
            _debug.logic(
                "render_error_rewrapped",
                error=type(error).__name__,
                sources=len(qweb_error_info.source or ()),
            )
            if qweb_error_info.source:
                error.qweb.source = qweb_error_info.source + error.qweb.source
            if not error.qweb.ref and frame.params.view_ref:
                error.qweb.ref = frame.params.view_ref
            qweb_error_info = error.qweb
        elif not isinstance(error, UserError):
            if self._is_error_raised_in_qweb(error):
                _debug.logic(
                    "render_error_wrapped",
                    error=type(error).__name__,
                    template=str(qweb_error_info.ref)[:80],
                    depth=len(stack),
                )
                raise QWebError(qweb_error_info) from error

        _debug.logic(
            "render_error_annotated",
            error=type(error).__name__,
            template=str(qweb_error_info.ref)[:80],
            user_error=isinstance(error, UserError),
        )
        error.qweb = qweb_error_info
        raise error

    def _is_error_raised_in_qweb(self, error: Exception) -> bool:
        trace = error.__traceback__
        tb_frames = [trace.tb_frame]
        while trace.tb_next is not None:
            trace = trace.tb_next
            tb_frames.append(trace.tb_frame)
        for tb_frame in tb_frames[::-1]:
            if tb_frame.f_globals.get("__name__") == __name__ or (
                isinstance(tb_frame.f_locals.get("self"), models.AbstractModel)
                and tb_frame.f_locals["self"]._name == self._name
            ):
                return True
            if any(
                path in tb_frame.f_code.co_filename
                for path in tools.config["addons_path"]
            ):
                return False
        return False

    def _get_error_info(
        self, error: Exception, stack: list[QwebStackFrame]
    ) -> QWebErrorInfo:
        compile_location = getattr(error, "qweb_compile_location", None)
        if compile_location is not None:
            ref, ref_name, path, html = compile_location
            code_lines, line_nb = [], 0
            _debug.logic("render_error_frame", ref=ref, via="compile", path=path)
        else:
            ref, ref_name, code, path, html = self._get_error_frame(error, stack)
            code_lines = (code or "").split("\n")
            line_nb = self._get_error_line_number(error, ref)

        source = [info.params.path_xml for info in stack if info.params.path_xml]

        path, html = self._get_error_source(
            code_lines, line_nb, ref, source, path, html
        )

        if path and (not source or source[-1] != (ref, path, html)):
            source.append((ref, path, html))

        surrounding = None
        if self.env.context.get("dev_mode") and line_nb:
            surrounding = self._get_error_surrounding_code(code_lines, line_nb, html)

        _debug.logic(
            "render_error_located",
            template=str(ref)[:80],
            line=line_nb,
            path=path,
            sources=len(source),
            surrounding=surrounding is not None,
        )
        return QWebErrorInfo(
            f"{error.__class__.__name__}: {error}",
            ref if ref_name is None else ref_name,
            ref,
            path,
            html,
            source,
            surrounding,
            self._get_error_origin(ref, path),
        )

    def _get_error_origin(self, ref: Any, path: str | None) -> str | None:
        if not isinstance(ref, int) or not path:
            return None
        try:
            views = self.env["ir.ui.view"]
            root = views.browse(ref).with_context(inherit_branding=True)
            tree = root._get_combined_arch()
            nodes = tree.xpath(path)
            if not nodes:
                return None
            origin_id = next(
                (
                    int(node.get("data-oe-id"))
                    for node in chain([nodes[0]], nodes[0].iterancestors())
                    if node.get("data-oe-id")
                ),
                ref,
            )
            if origin_id == ref:
                return None
            origin = views.browse(origin_id)
            label = f"{origin.key or origin.name} (view {origin.id})"
        except PG_RECOVERABLE_EXCEPTIONS:
            raise
        except Exception as error:
            _debug.logic(
                "render_error_origin_unknown", ref=ref, error=type(error).__name__
            )
            return None
        _debug.logic("render_error_origin", ref=ref, origin=origin_id)
        return label

    def _get_error_frame(
        self, error: Exception, stack: list[QwebStackFrame]
    ) -> tuple[Any, str | None, str | None, str | None, str | None]:
        frame = stack[-1]
        loaded_codes = self.env.context["__qweb_loaded_codes"]
        path = html = None
        if (
            frame.params.view_ref in loaded_codes
            and not isinstance(error, RecursionError)
        ) or len(stack) <= 1:
            options = frame.options or {}
            if "ref" not in options:
                options = (
                    self.env.context["__qweb_loaded_options"].get(frame.params.view_ref)
                    or {}
                )
            ref = options.get("ref") or frame.params.view_ref
            ref_name = options.get("ref_name") or None
            code = (
                loaded_codes.get(ref)
                or loaded_codes.get(frame.params.view_ref)
                or loaded_codes.get(ETREE_REF)
            )
            if ref == self.env.context["_qweb_error_path_xml"][0]:
                path = self.env.context["_qweb_error_path_xml"][1]
                html = self.env.context["_qweb_error_path_xml"][2]
            _debug.logic(
                "render_error_frame",
                ref=ref,
                via="frame",
                has_code=code is not None,
                has_path=path is not None,
                depth=len(stack),
            )
        else:
            options = stack[-2].options or frame.options or {}
            ref = options.get("ref")
            ref_name = options.get("ref_name")
            code = loaded_codes.get(ref) or loaded_codes.get(ETREE_REF)
            if frame.params.path_xml:
                path = frame.params.path_xml[1]
                html = frame.params.path_xml[2]
            _debug.logic(
                "render_error_frame",
                ref=ref,
                via="parent",
                has_code=code is not None,
                has_path=path is not None,
                depth=len(stack),
            )
        return ref, ref_name, code, path, html

    @staticmethod
    def _get_error_line_number(error: Exception, ref: Any) -> int:
        filename = f"<{ref}>"
        line_nb = 0
        trace = error.__traceback__
        while trace is not None:
            code_filename = trace.tb_frame.f_code.co_filename
            if code_filename == filename or (
                ref is None and code_filename.startswith("<")
            ):
                line_nb = trace.tb_lineno
            trace = trace.tb_next
        _debug.logic(
            "render_error_line",
            ref=ref,
            line=line_nb,
            reason=None if line_nb else "not_in_trace",
        )
        return line_nb

    def _get_error_source(
        self,
        code_lines: list[str],
        line_nb: int,
        ref: Any,
        source: list[tuple[Any, str, str]],
        path: str | None,
        html: str | None,
    ) -> tuple[str | None, str | None]:
        found = False
        for code_line in reversed(code_lines[:line_nb]):
            if code_line.startswith("def "):
                break
            match = ELEMENT_MARKER_REGEXP.match(code_line)
            if match:
                path, html = ast.literal_eval(match[1])
                found = True
                break
        _debug.logic("render_error_source", ref=ref, found=found, sources=len(source))
        return path, html

    def _get_error_surrounding_code(
        self, code_lines: list[str], line_nb: int, html: str | None
    ) -> str:
        previous_lines = "\n".join(code_lines[max(line_nb - 25, 0) : line_nb - 1])
        line = code_lines[line_nb - 1]
        next_lines = "\n".join(code_lines[line_nb : line_nb + 5])
        indent = re.search(r"^(\s*)", line).group(0)
        return textwrap.indent(
            textwrap.dedent(
                f"{previous_lines}\n"
                f"{indent}########### Line triggering the error ############\n{line}\n"
                f"{indent}##################################################\n{next_lines}"
            ),
            " " * 8,
        )

    def _get_template_cache_keys(self) -> list[str]:
        return [
            "lang",
            "inherit_branding",
            "inherit_branding_auto",
            "edit_translations",
            "profile",
            "preserve_comments",
            "nsmap",
        ]

    def _get_template_cache_signature(self) -> tuple:
        context = self.env.context
        return tuple(
            self._get_cache_signature_value(context.get(k))
            for k in self._get_template_cache_keys()
        )

    @staticmethod
    def _get_cache_signature_value(value: Any) -> Any:
        if not value:
            return False
        if isinstance(value, Mapping):
            return tuple(sorted(value.items(), key=repr))
        return value

    def _get_template_info(self, template: int | str) -> dict[str, Any]:
        return self.env["ir.ui.view"]._get_cached_template_info(template)

    def _compile(
        self, template: int | str | etree._Element
    ) -> tuple[dict[str, Any], str, frozendict]:
        if isinstance(template, str) and template.endswith(".xml"):
            _debug.logic("compile.route", route="file", template=template)
            template_functions, def_name, options = self._generate_code_file_cached(
                template
            )
        elif isinstance(template, etree._Element) or not (
            ref := self._get_template_info(template)["id"]
        ):
            _debug.logic(
                "compile.route",
                route="uncached",
                template=template if isinstance(template, int | str) else "etree",
            )
            template_functions, def_name, options = self._generate_code_uncached(
                template
            )
        else:
            _debug.logic("compile.route", route="cached", template=ref)
            template_functions, def_name, options = self._generate_code_cached(ref)

        if options.get("profile"):
            template_functions = self._wrap_profiled_functions(
                template_functions, options
            )

        return (template_functions, def_name, options)

    @staticmethod
    def _wrap_profiled_functions(
        template_functions: dict[str, Any], options: Mapping[str, Any]
    ) -> dict[str, Any]:
        ref = options.get("ref")
        ref_xml = str(val) if (val := options.get("ref_xml")) else None

        def wrap(function: FunctionType) -> FunctionType:
            def profiled_method_compile(self: Any, values: dict[str, Any]) -> Any:
                qweb_tracker = QwebTracker(ref, ref_xml, self.env.cr)
                self = self.with_context(qweb_tracker=qweb_tracker)
                if qweb_tracker.execution_context_enabled:
                    with ExecutionContext(template=ref):
                        return function(self, values)
                return function(self, values)

            return profiled_method_compile

        _debug.logic(
            "compile.profiled_wrap", template=ref, functions=len(template_functions)
        )
        return {
            key: wrap(function) if isinstance(function, FunctionType) else function
            for key, function in template_functions.items()
        }

    @tools.conditional(
        "xml" not in tools.config["dev_mode"],
        tools.ormcache(
            "ref",
            "self._get_template_cache_signature()",
            cache="templates",
        ),
    )
    def _generate_code_cached(self, ref: int) -> tuple[dict[str, Any], str, frozendict]:
        return self._generate_code_uncached(ref)

    @tools.conditional(
        "xml" not in tools.config["dev_mode"],
        tools.ormcache(
            "path",
            "self._get_template_cache_signature()",
            cache="templates",
        ),
    )
    def _generate_code_file_cached(
        self, path: str
    ) -> tuple[dict[str, Any], str, frozendict]:
        module = Path(path).parts[0]
        manifest = Manifest.for_addon(module, display_warning=False)
        if manifest is None:
            msg = (
                f"Cannot load template file {path!r}: "
                f"{module!r} is not a known Odoo module"
            )
            _debug.logic("template_file_rejected", path=path, reason="unknown_module")
            raise ValueError(msg)
        if "templates" not in Path(file_path(path)).relative_to(manifest.path).parts:
            msg = (
                f"The templates file {path!r} must be under a subfolder "
                "'templates' of a module"
            )
            _debug.logic(
                "template_file_rejected", path=path, reason="outside_templates"
            )
            raise ValueError(msg)
        with file_open(path, "rb", filter_ext=(".xml",)) as file:
            element = etree.fromstring(memoryview(file.read()))
        _debug.logic("template_file_loaded", path=path, module=module)
        return self._generate_code_uncached(element)

    def _generate_code_uncached(
        self, template: int | str | etree._Element
    ) -> tuple[dict[str, Any], str, frozendict]:
        ref = (
            self._get_template_info(template)["id"]
            if isinstance(template, (int, str))
            else None
        )

        with _debug.perf("compile", template=ref if ref is not None else "etree"):
            code, options, def_name = self._generate_code(template)
        _debug.logic(
            "compiled", template=options.get("ref", ref), found=code is not None
        )

        if code is None:
            Error, message, stack = options["error"]
            _debug.logic(
                "compile.not_found",
                template=template if isinstance(template, int | str) else "etree",
                error=Error.__name__,
            )

            def not_found_template(self: Any, values: dict[str, Any]) -> str:
                if tools.config["dev_mode"]:
                    _logger.info(stack)
                if self.env.context.get("raise_if_not_found", True):
                    raise Error(message)
                _logger.warning("Cannot load template %s: %s", template, message)
                return ""

            return (
                {"not_found_template": not_found_template},
                "not_found_template",
                frozendict(options),
            )

        with _debug.perf(
            "compile.exec", template=options.get("ref", ref), chars=len(code)
        ):
            compiled = compile(code, f"<{options.get('ref', ref)}>", "exec")
            globals_dict = self._prepare_globals()
            globals_dict["__builtins__"] = globals_dict
            globals_dict["code"] = code
            unsafe_eval(compiled, globals_dict)
        return (
            globals_dict["template_functions"],
            def_name,
            frozendict(options),
        )

    def _generate_code(
        self, template: int | str | etree._Element
    ) -> tuple[str | None, dict[str, Any], str]:
        if template is not None and not isinstance(
            template, (int, str, etree._Element)
        ):
            _debug.logic(
                "compile.rejected",
                reason="bad_template_type",
                type=type(template).__name__,
            )
            raise TypeError(
                "A qweb template is an id, an xml id/key or an etree element, "
                f"got {type(template).__name__}: {template!r}"
            )
        context = self.env.context.copy()

        try:
            element, document, ref = self._get_template(template)
        except (ValueError, UserError) as e:
            _debug.logic(
                "compile.template_missing",
                template=template if isinstance(template, int | str) else "etree",
                error=type(e).__name__,
            )
            return (None, self._get_not_found_options(context, e), "not_found_template")

        context.pop("raise_if_not_found", None)

        compile_context, options, def_name = self._prepare_compile_context(
            template, element, document, ref, context
        )

        if element.text:
            element.text = FIRST_RSTRIP_REGEXP.sub(r"\2", element.text)

        compile_context.text_concat = []
        try:
            compile_context.template_functions[f"{def_name}_content"] = (
                [f"def {def_name}_content(self, values):"]
                + self._compile_node(element, compile_context, 2)
                + self._flush_text(compile_context, 2, rstrip=True)
            )
        except Exception as error:
            error.qweb_compile_location = (
                compile_context.ref,
                compile_context.ref_name,
                compile_context.element_path,
                compile_context.element_xml,
            )
            raise

        compile_context.template_functions[def_name] = self._compile_entry_point(
            def_name, options
        )
        _debug.pipeline(
            "compile.functions_generated",
            template=ref,
            def_name=def_name,
            functions=len(compile_context.template_functions),
            expr_cache=len(self._compile_expr_cache),
        )

        if options.get("profile"):
            ref_xml = compile_context.ref_xml
            options["ref_xml"] = str(ref_xml) if ref_xml is not None else None

        return (
            self._get_module_source(compile_context.template_functions, options),
            options,
            def_name,
        )

    def _get_not_found_options(
        self, context: dict[str, Any], error: Exception
    ) -> dict[str, Any]:
        options = {k: context.get(k, False) for k in self._get_template_cache_keys()}
        message = str(error)
        if hasattr(error, "context") and error.context.get("view"):
            message = f"{message} (view: {error.context['view'].key})"
        options["error"] = (error.__class__, message, traceback.format_exc())
        return options

    def _prepare_compile_context(
        self,
        template: int | str | etree._Element,
        element: etree._Element,
        document: Any,
        ref: int | str | None,
        context: dict[str, Any],
    ) -> tuple[CompileContext, dict[str, Any], str]:
        ref_name = element.attrib.pop("t-name", None)
        if isinstance(ref, int) or isinstance(template, str):
            ref_name = self._get_template_info(ref)["key"] or ref_name

        compile_context = CompileContext(
            context=context,
            ref=ref,
            ref_name=ref_name,
            ref_xml=document,
            template=template,
            root=element.getroottree(),
            make_name=None,
            template_functions={},
            text_concat=[],
            nsmap={
                ns_prefix: str(ns_definition)
                for ns_prefix, ns_definition in context.get("nsmap", {}).items()
            },
        )

        cache_values = {**context, "nsmap": compile_context.nsmap}
        options = {
            key: cache_values.get(key, False) for key in self._get_template_cache_keys()
        }
        options["ref"] = compile_context.ref
        options["ref_name"] = compile_context.ref_name

        ref_name = compile_context.ref_name or ""
        if isinstance(template, etree._Element):
            def_name = f"template_etree_{next(ETREE_TEMPLATE_REF)}"
        else:
            def_name = TO_VARNAME_REGEXP.sub(r"_", f"template_{ref_name}_{ref}")

        name_gen = count()
        compile_context.make_name = lambda prefix: (
            f"{def_name}_{prefix}_{next(name_gen)}"
        )
        _debug.logic(
            "compile.context_prepared",
            template=ref,
            ref_name=ref_name,
            etree=isinstance(template, etree._Element),
            nsmap=len(compile_context.nsmap),
            profile=bool(options.get("profile")),
        )
        return compile_context, options, def_name

    @staticmethod
    def _compile_entry_point(def_name: str, options: dict[str, Any]) -> list[str]:
        return [
            indent_code(
                f"""
            def {def_name}(self, values):
                if 'xmlid' not in values:
                    values['xmlid'] = {options["ref_name"]!r}
                    values['viewid'] = {options["ref"]!r}
                loaded_codes = self.env.context['__qweb_loaded_codes']
                if loaded_codes.get({options["ref"]!r}) is not code:
                    loaded_options = self.env.context['__qweb_loaded_options']
                    loaded_options[{options["ref"]!r}] = loaded_options[{options["ref_name"]!r}] = template_options
                    loaded_codes[{options["ref"]!r}] = loaded_codes[{options["ref_name"]!r}] = code
                return {def_name}_content(self, values)
                """,
                0,
            )
        ]

    @staticmethod
    def _get_module_source(
        template_functions: dict[str, list[str]], options: dict[str, Any]
    ) -> str:
        code_lines = [
            f"template_options = {pprint.pformat(options, indent=4)}",
            "template_functions = {}",
        ]
        for lines in template_functions.values():
            code_lines.extend(lines)
            body = "\n".join(lines).split("\n", 1)[1]
            if not YIELD_LINE_REGEXP.search(body):
                match = BODY_INDENT_REGEXP.search(body)
                code_lines.append(f"{match[1] if match else '    '}yield ''")
        code_lines.extend(
            f"template_functions[{name!r}] = {name}" for name in template_functions
        )
        return "\n".join(code_lines)

    def _get_template(
        self, template: int | str | etree._Element
    ) -> tuple[etree._Element, str, str | int]:
        if template in (False, None, ""):
            _debug.logic("template.rejected", reason="empty")
            raise ValueError("template is required")

        if isinstance(template, etree._Element):
            document = lazy(etree.tostring, template, encoding="unicode")
            element = deepcopy(template)

            for node in element.iter():
                ref = node.get("t-name")
                if ref:
                    _debug.logic("template.etree_named", ref=ref)
                    return (node, document, _id_or_xmlid(ref))

            _debug.logic("template.etree_anonymous", tag=element.tag)
            return (element, document, ETREE_REF)

        if isinstance(template, str) and "<" in template:
            _debug.logic("template.rejected", reason="inline_string")
            msg = "Inline templates must be passed as `etree` documents"
            raise ValueError(msg)

        id_or_xmlid = _id_or_xmlid(template)
        value = self._preload_trees([id_or_xmlid]).get(id_or_xmlid)
        if value.get("error"):
            _debug.logic("template_cached_error", template=id_or_xmlid)
            raise self.env["ir.ui.view"]._prepare_cached_template_error(value["error"])

        value_tree = deepcopy(value["tree"])
        return (value_tree, value["template"], value["ref"])

    @api.model
    def _get_preload_attribute_xmlids(self) -> list[str]:
        return ["t-call"]

    def _preload_trees(
        self, refs: Sequence[int | str]
    ) -> dict[int | str, dict[str, Any]]:
        compile_batch = self.env["ir.ui.view"]._preload_views(refs)

        refs = list(map(_id_or_xmlid, refs))
        missing_refs = {
            ref: compile_batch[ref]
            for ref in refs
            if "template" not in compile_batch[ref] and not compile_batch[ref]["error"]
        }
        if not missing_refs:
            _debug.perf.count("preload_trees.all_cached", refs=len(refs))
            return compile_batch

        views = (
            self.env["ir.ui.view"]
            .sudo()
            .union(*[data["view"] for data in missing_refs.values()])
        )

        with _debug.perf("preload_trees", cr=self.env.cr, views=len(views)):
            trees = views._get_view_etrees()

        data_by_view_id = {
            view.id: {
                "tree": tree,
                "template": lazy(etree.tostring, tree, encoding="unicode"),
            }
            for view, tree in zip(views, trees, strict=True)
        }
        for ref, ref_data in missing_refs.items():
            data = data_by_view_id[ref_data["view"].id]
            compile_batch[ref_data["view"].id].update(data)
            compile_batch[ref].update(data)

        ref_names = self._get_preload_attribute_xmlids()
        sub_refs = OrderedSet()
        for view, tree in zip(views, trees, strict=True):
            for ref_name in ref_names:
                for el in tree.xpath(f"//*[@{ref_name}]"):
                    if any(
                        att.startswith("t-options-") or att in {"t-options", "t-lang"}
                        for att in el.attrib
                    ):
                        continue
                    sub_ref = el.get(ref_name)
                    if not sub_ref:
                        _debug.logic(
                            "preload_trees.empty_ref",
                            attribute=ref_name,
                            view=view.key or view.id,
                        )
                        raise ValueError(
                            f"template is required: empty {ref_name!r} value "
                            f"in template {view.key or view.id!r}"
                        )
                    if "{" not in sub_ref and "<" not in sub_ref and "/" not in sub_ref:
                        sub_refs.add(sub_ref)
        _debug.pipeline(
            "preload_trees",
            refs=len(refs),
            missing=len(missing_refs),
            sub_refs=len(sub_refs),
        )
        if sub_refs:
            self._preload_trees(list(sub_refs))

        return compile_batch

    def _get_converted_image_data_uri(self, base64_source: str | bytes) -> str:
        if isinstance(base64_source, str):
            base64_source = base64_source.encode()
        if self.env.context.get("webp_as_jpg"):
            if base64_image_subtype(base64_source) == "webp":
                base64_source = self._get_jpg_for_webp(base64_source) or base64_source
        return image_data_uri(base64_source)

    def _get_jpg_for_webp(self, base64_webp: str | bytes) -> bytes | None:
        Attachment = (
            self.env["ir.attachment"].sudo().with_context(skip_res_field_check=True)
        )
        checksum = Attachment._get_content_checksum(base64.b64decode(base64_webp))
        converted_cache = self.env.cr.cache.setdefault("_webp_as_jpg_datas_", {})
        _debug.perf.count("webp_as_jpg_checked", cached=checksum in converted_cache)
        if checksum not in converted_cache:
            origins = Attachment._search([("checksum", "=", checksum)])
            converted = Attachment.search(
                [
                    ("res_model", "=", "ir.attachment"),
                    ("res_id", "in", origins),
                    ("mimetype", "=", "image/jpeg"),
                ],
                limit=1,
            )
            converted_cache[checksum] = converted.datas if converted else None
            _debug.logic(
                "webp_as_jpg_lookup", checksum=checksum[:12], converted=bool(converted)
            )
        return converted_cache[checksum]

    def _prepare_environment(self, values: dict[str, Any]) -> Self:
        values.update(
            true=True,
            false=False,
        )
        if not self.env.context.get("minimal_qcontext"):
            values.setdefault("debug", (request and request.session.debug) or "")
            values.setdefault("user_id", self.env.user.with_env(self.env))
            values.setdefault("res_company", self.env.company.sudo())
            values.update(
                request=request,
                test_mode_enabled=config["test_enable"],
                json=qweb_json,
                quote_plus=urllib.parse.quote_plus,
                time=safe_eval.time,
                datetime=safe_eval.datetime,
                relativedelta=relativedelta,
                image_data_uri=self._get_converted_image_data_uri,
                floor=math.floor,
                ceil=math.ceil,
                env=self.env,
                lang=self.env.context.get("lang"),
                keep_query=keep_query,
            )

        context = {"dev_mode": "qweb" in tools.config["dev_mode"]}
        _debug.logic(
            "render.environment_prepared",
            minimal=bool(self.env.context.get("minimal_qcontext")),
            dev_mode=context["dev_mode"],
            values=len(values),
        )
        return self.with_context(**context)

    def _prepare_globals(self) -> dict[str, Any]:
        return {
            "__name__": __name__,
            "Sized": Sized,
            "Mapping": Mapping,
            "Markup": Markup,
            "escape": escape,
            "escape_str": escape_str,
            "escape_text": escape_text,
            "format_attributes": format_attributes,
            "srcdoc_value": srcdoc_value,
            "TemplateAttributeValue": TemplateAttributeValue,
            "checked_attributes": checked_attributes,
            "checked_call_values": checked_call_values,
            "checked_set_values": checked_set_values,
            "checked_call_options": checked_call_options,
            "VOID_ELEMENTS": VOID_ELEMENTS,
            "QwebCallParameters": QwebCallParameters,
            "QwebContent": QwebContent,
            **_SAFE_BUILTINS,
        }

    def _add_text(
        self, text: str | bytes | None, compile_context: CompileContext
    ) -> None:
        compile_context.text_concat.append(to_text(text))

    def _strip_pending_trailing_ws(self, compile_context: CompileContext) -> None:
        text_concat = compile_context.text_concat
        if text_concat and text_concat[-1].isspace():
            text_concat[-1] = text_concat[-1].rstrip(" \t")

    def _rstrip_text(self, compile_context: CompileContext) -> str:
        text_concat = compile_context.text_concat
        if not text_concat:
            return ""

        result = RSTRIP_REGEXP.search(text_concat[-1])
        strip = result.group(0) if result else ""
        text_concat[-1] = RSTRIP_REGEXP.sub("", text_concat[-1])

        return strip

    def _flush_text(
        self, compile_context: CompileContext, level: int, rstrip: bool = False
    ) -> list[str]:
        text_concat = compile_context.text_concat
        if not text_concat:
            return []
        if rstrip:
            self._rstrip_text(compile_context)
        text = "".join(text_concat)
        text_concat.clear()
        if not text:
            return []
        return [f"{'    ' * level}yield {text!r}"]

    def _is_static_node(
        self, el: etree._Element, compile_context: CompileContext
    ) -> bool:
        return (
            el.tag != "t"
            and "groups" not in el.attrib
            and not any(
                att.startswith("t-") and att not in ("t-tag-open", "t-inner-content")
                for att in el.attrib
            )
        )

    def _new_namespaces(
        self, el: etree._Element, compile_context: CompileContext
    ) -> list[tuple[str | None, str]]:
        return sorted(
            set(el.nsmap.items()) - set(compile_context.nsmap.items()),
            key=lambda item: item[0] or "",
        )

    @staticmethod
    def _get_qualified_attribute_name(key: str, nsprefixmap: Mapping[str, str]) -> str:
        name = key.removesuffix(".translate")
        if name[0] != "{":
            return name
        qname = etree.QName(name)
        prefix = nsprefixmap.get(qname.namespace) or XML_NAMESPACE_PREFIXES.get(
            qname.namespace
        )
        if prefix is None:
            raise KeyError(f"No prefix is declared for the namespace of {name!r}")
        return f"{prefix}:{qname.localname}"

    def _get_ns_prefix_map(
        self, el: etree._Element, compile_context: CompileContext
    ) -> dict[str, str]:
        return {
            uri: prefix
            for prefix, uri in chain(compile_context.nsmap.items(), el.nsmap.items())
            if prefix is not None
        }

    def _get_element_marker(self, path: str | None, xml: str | None) -> str:
        return f"# element: {path!r} , {xml!r}"

    def _compile_format(self, expr: str, *, markup: bool = False) -> str:
        values = [
            f"self._compile_to_str({self._compile_expr(m.group(1) or m.group(2))})"
            for m in FORMAT_REGEX.finditer(expr)
        ]
        if not values:
            return f"Markup({expr!r})" if markup else repr(expr)
        code = repr(FORMAT_REGEX.sub("%s", expr.replace("%", "%%")))
        if markup:
            code = f"Markup({code})"
        return code + f" % ({', '.join(values)},)"

    def _compile_translatable_format(self, expr: str) -> str:
        return self._compile_format(
            expr, markup=bool(self.env.context.get("edit_translations"))
        )

    def _compile_dict_merge(
        self, target: str, expr: str, level: int, checker: str
    ) -> str:
        return indent_code(
            f"{target}.update({checker}({self._compile_expr(expr)}))", level
        )

    _compile_expr_cache = LRU(8192)

    def _compile_expr(self, expr: str, raise_on_missing: bool = False) -> str:
        cache_key = (expr, raise_on_missing)
        result = self._compile_expr_cache.get(cache_key)
        if result is not None:
            return result

        _debug.perf.count("compile_expr.cache_miss", chars=len(expr or ""))
        try:
            tree = ast.parse(f"({expr or ''})", mode="eval")
        except SyntaxError as e:
            _debug.logic("compile_expr.rejected", reason="syntax", chars=len(expr))
            raise SyntaxError(f"Can not compile expression: {expr} ({e.msg})") from e

        check_dunder_identifiers(tree)
        tree = ExpressionRewriter(raise_on_missing).visit(tree)
        expression = ast.unparse(tree)

        if "\n" in expression:
            _debug.logic("compile_expr.rejected", reason="multiline", chars=len(expr))
            raise SyntaxError(
                "QWeb expressions must compile to a single line; "
                f"cannot flatten a multi-line literal in: {expr!r}"
            )

        try:
            expression = guard_format_calls(expression)
            code = compile(expression, "<>", "eval")
        except SyntaxError as e:
            _debug.logic("compile_expr.rejected", reason="syntax", chars=len(expr))
            raise SyntaxError(f"Can not compile expression: {expr} ({e.msg})") from e
        check_code_object(_SAFE_QWEB_OPCODES, code, expr)

        result = f"({expression})"
        self._compile_expr_cache[cache_key] = result
        return result

    def _compile_bool(self, attr: str | bool | None) -> bool:
        if attr:
            if attr is True:
                return True
            attr = attr.lower()
            if attr in ("false", "0"):
                return False
            elif attr in ("true", "1"):
                return True
        return False

    def _compile_to_str(self, expr: Any) -> str:
        return to_text(expr)

    def _get_authoring_directives(self) -> Mapping[str, str]:
        return AUTHORING_DIRECTIVES

    def _get_directive_eval_order(self) -> list[str]:
        return [
            "elif",
            "else",
            "debug",
            "groups",
            "as",
            "foreach",
            "if",
            "call-assets",
            "lang",
            "options",
            "call",
            "att",
            "field",
            "esc",
            "raw",
            "out",
            "tag-open",
            "set",
            "inner-content",
            "tag-close",
        ]

    def _compile_node(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        if "t-qweb-skip" in el.attrib:
            _debug.logic("compile_node.skipped", tag=el.tag)
            return []

        self._normalize_deprecated_attributes(el, compile_context)
        if el.tag == "script":
            el.attrib.pop("nonce", None)

        if self._is_static_node(el, compile_context):
            return self._compile_static_node(el, compile_context, level)

        path = compile_context.root.getpath(el)
        xml = etree.tostring(
            etree.Element(el.tag, el.attrib, nsmap=el.nsmap), encoding="unicode"
        )
        compile_context.element_path = path
        compile_context.element_xml = xml
        body = [indent_code(self._get_element_marker(path, xml), level)]

        compile_context.directives = iter(self._get_directive_eval_order())

        unqualified_el_tag, el_tag = self._get_tag_names(el)

        if unqualified_el_tag != "t":
            el.set("t-tag-open", el_tag)
            if el_tag not in VOID_ELEMENTS:
                el.set("t-tag-close", el_tag)

        if not any(name in el.attrib for name in OUTPUT_DIRECTIVES):
            el.set("t-inner-content", "True")

        return body + self._compile_directives(el, compile_context, level)

    def _normalize_deprecated_attributes(
        self, el: etree._Element, compile_context: CompileContext
    ) -> None:
        if "t-call-options" in el.attrib:
            _logger.warning(
                "Found deprecated attribute @t-call-options=%r in template %r. "
                "Replace by @t-options",
                el.get("t-call-options"),
                compile_context.ref or "<unknown>",
            )
            el.attrib["t-options"] = el.attrib.pop("t-call-options")

    @classmethod
    def _is_t_element(cls, el: etree._Element) -> bool:
        return cls._get_tag_names(el)[0] == "t"

    @staticmethod
    def _get_tag_names(el: etree._Element) -> tuple[str, str]:
        if not el.nsmap:
            return el.tag, el.tag
        unqualified_el_tag = etree.QName(el.tag).localname
        if el.prefix:
            return unqualified_el_tag, f"{el.prefix}:{unqualified_el_tag}"
        return unqualified_el_tag, unqualified_el_tag

    def _compile_static_node(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        unqualified_el_tag, el_tag = self._get_tag_names(el)
        attrib = {}
        if el.nsmap:
            for ns_prefix, ns_definition in self._new_namespaces(el, compile_context):
                attrib[_xmlns_attribute(ns_prefix)] = ns_definition
        nsprefixmap = self._get_ns_prefix_map(el, compile_context)
        for key, value in el.attrib.items():
            attrib[self._get_qualified_attribute_name(key, nsprefixmap)] = value
        attrib = self._post_processing_att(el.tag, attrib, is_static=True)

        _debug.pipeline(
            "compile_static_node",
            tag=el_tag,
            attributes=len(attrib),
            namespaced=bool(el.nsmap),
            void=el_tag in VOID_ELEMENTS,
        )
        nonce_code = []
        if unqualified_el_tag != "t":
            self._add_text(
                f"<{el_tag}{format_attributes(attrib, strict=False)}", compile_context
            )
            if el_tag in VOID_ELEMENTS:
                self._add_text("/>", compile_context)
            else:
                if el_tag == "script":
                    nonce_code = [
                        *self._flush_text(compile_context, level),
                        indent_code("yield self._script_nonce_attribute()", level),
                    ]
                self._add_text(">", compile_context)

        el.attrib.clear()

        body = nonce_code + self._compile_directive(
            el, compile_context, "inner-content", level
        )

        if unqualified_el_tag != "t" and el_tag not in VOID_ELEMENTS:
            self._add_text(f"</{el_tag}>", compile_context)

        return body

    def _compile_directives(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        if self._is_static_node(el, compile_context):
            el.attrib.pop("t-tag-open", None)
            el.attrib.pop("t-inner-content", None)
            el.attrib.pop("t-tag-close", None)
            return self._compile_static_node(el, compile_context, level)

        code = []

        for directive in compile_context.directives:
            if (
                ("t-" + directive) in el.attrib
                or directive == "att"
                or (directive == "groups" and "groups" in el.attrib)
                or (
                    directive == "options"
                    and any(name.startswith("t-options-") for name in el.attrib)
                )
            ):
                code.extend(
                    self._compile_directive(el, compile_context, directive, level)
                )

        for att in list(el.attrib):
            if (
                att not in SPECIAL_DIRECTIVES
                and att.startswith("t-")
                and getattr(
                    self,
                    f"_compile_directive_{att[2:].replace('-', '_')}",
                    None,
                )
            ):
                code.extend(
                    self._compile_directive(el, compile_context, att[2:], level)
                )

        remaining = set(el.attrib) - SPECIAL_DIRECTIVES
        if remaining:
            _debug.logic(
                "compile_directives.unknown",
                tag=el.tag,
                attributes=sorted(remaining),
                template=compile_context.ref,
            )
            _logger.warning(
                "Unknown directives or unused attributes: %s in %s",
                remaining,
                compile_context.template,
            )

        return code

    def _compile_directive(
        self,
        el: etree._Element,
        compile_context: CompileContext,
        directive: str,
        level: int,
    ) -> list[str]:
        compile_handler = getattr(
            self, f"_compile_directive_{directive.replace('-', '_')}", None
        )
        if compile_context.get("profile") and directive not in (
            "inner-content",
            "tag-open",
            "tag-close",
        ):
            enter = f"{' ' * 4 * level}self.env.context['qweb_tracker'].enter_directive({directive!r}, {el.attrib!r}, {compile_context.element_path!r})"
            leave = f"{' ' * 4 * level}self.env.context['qweb_tracker'].leave_directive({directive!r}, {el.attrib!r}, {compile_context.element_path!r})"
            code_directive = compile_handler(el, compile_context, level)
            if code_directive:
                code_directive = [enter, *code_directive, leave]
        else:
            code_directive = compile_handler(el, compile_context, level)
        return code_directive

    def _compile_directive_debug(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        debugger = el.attrib.pop("t-debug")
        code = []
        if compile_context.get("dev_mode"):
            _debug.logic("directive_debug.emitted", debugger=debugger or "builtin")
            code.append(indent_code(f"self._debug_trace({debugger!r}, values)", level))
        else:
            _debug.logic("directive_debug.ignored", reason="not_dev_mode")
            _logger.warning("@t-debug in template is only available in qweb dev mode")
        return code

    def _compile_directive_options(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        t_options = el.attrib.pop("t-options", None)
        entries = [f"**{self._compile_expr(t_options)}"] if t_options else []
        for key in list(el.attrib):
            if key.startswith("t-options-"):
                value = el.attrib.pop(key)
                option_name = key.removeprefix("t-options-")
                entries.append(f"{option_name!r}: {self._compile_expr(value)}")

        _debug.logic(
            "directive_options.compiled",
            tag=el.tag,
            dict_options=len(entries) - bool(t_options),
            t_options=bool(t_options),
        )
        el.set("t-consumed-options", "True")
        return [
            indent_code(f"values['__qweb_options__'] = {{{', '.join(entries)}}}", level)
        ]

    def _compile_directive_consumed_options(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        msg = "the t-options must be on the same tag as a directive that consumes it (for example: t-out, t-field, t-call)"
        _debug.logic("directive_options.rejected", reason="unconsumed", tag=el.tag)
        raise SyntaxError(msg)

    def _compile_directive_att(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        if "t-tag-open" not in el.attrib and not any(
            name in el.attrib for name in OUTPUT_DIRECTIVES
        ):
            dropped = [
                key
                for key in el.attrib
                if not key.startswith("t-") or key.startswith("t-att")
            ]
            for key in dropped:
                del el.attrib[key]
            if dropped:
                _debug.logic("directive_att.dropped", tag=el.tag, attributes=dropped)
            return []

        code = [indent_code("attrs = values['__qweb_attrs__'] = {}", level)]

        if el.nsmap:
            for ns_prefix, ns_definition in self._new_namespaces(el, compile_context):
                code.append(
                    indent_code(
                        f"attrs[{_xmlns_attribute(ns_prefix)!r}] = {ns_definition!r}",
                        level,
                    )
                )

        static_keys = [key for key in el.attrib if not key.startswith("t-")]
        if static_keys:
            nsprefixmap = self._get_ns_prefix_map(el, compile_context)
            for key in static_keys:
                value = el.attrib.pop(key)
                name = self._get_qualified_attribute_name(key, nsprefixmap)
                if name.lower() == "srcdoc":
                    value_code = f"Markup({value!r})"
                else:
                    value_code = f"TemplateAttributeValue({value!r})"
                code.append(indent_code(f"attrs[{name!r}] = {value_code}", level))

        for key in list(el.attrib):
            if key.startswith("t-attf-"):
                value = el.attrib.pop(key)
                name = key[7:].removesuffix(".translate")
                value_code = self._compile_format(value)
            elif key.startswith("t-att-"):
                value = el.attrib.pop(key)
                name = key.removeprefix("t-att-")
                value_code = self._compile_expr(value)
            elif key == "t-att":
                value = el.attrib.pop(key)
                code.append(
                    self._compile_dict_merge(
                        "attrs", value, level, "checked_attributes"
                    )
                )
                continue
            else:
                continue
            if is_event_handler_attribute(name):
                _debug.logic("directive_att.dropped", reason="event_handler", attr=key)
                _logger.warning(
                    "Template %s, %s: dropped %s, an event handler cannot be "
                    "computed while rendering (escaping cannot make a value safe "
                    "as JavaScript); pass the value through a data-* attribute "
                    "and bind the handler in JS",
                    compile_context.ref_name or compile_context.ref,
                    compile_context.element_path,
                    key,
                )
                continue
            if name.lower() == "srcdoc":
                value_code = f"srcdoc_value({value_code})"
            code.append(indent_code(f"attrs[{name!r}] = {value_code}", level))

        _debug.pipeline("directive_att.compiled", tag=el.tag, statements=len(code) - 1)
        return code

    def _compile_directive_tag_open(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:

        el_tag = el.attrib.pop("t-tag-open", None)
        if not el_tag:
            _debug.logic("directive_tag_open.skipped", tag=el.tag)
            return []

        self._add_text(f"<{el_tag}", compile_context)
        opening = "".join(compile_context.text_concat)
        compile_context.text_concat.clear()
        closing = ">" if "t-tag-close" in el.attrib else "/>"

        if el_tag == "script":
            with_attrs = (
                " + ('' if 'nonce' in attrs else self._script_nonce_attribute())"
            )
            bare = f"{opening!r} + self._script_nonce_attribute() + {closing!r}"
        else:
            with_attrs = ""
            bare = repr(opening + closing)

        code = [
            indent_code(
                f"""
            attrs = values.pop('__qweb_attrs__', None)
            if attrs:
                yield {opening!r} + format_attributes(self._post_processing_att({el.tag!r}, attrs)){with_attrs} + {closing!r}
            else:
                yield {bare}
        """,
                level,
            )
        ]

        _debug.pipeline(
            "directive_tag_open.compiled",
            tag=el_tag,
            closed="t-tag-close" in el.attrib,
        )
        return code

    def _compile_directive_tag_close(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        el_tag = el.attrib.pop("t-tag-close", None)
        if el_tag:
            self._add_text(f"</{el_tag}>", compile_context)
        return []

    def _compile_directive_set(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:

        code = self._flush_text(compile_context, level, rstrip=self._is_t_element(el))

        varname = el.attrib.pop("t-set")
        self._check_set_varname(varname)
        self._check_set_owns_its_node(el, varname)

        value_code = self._compile_set_value(el, varname, level)
        if value_code is not None and varname == T_CALL_SLOT:
            _debug.logic("directive_set.rejected", reason="slot_from_value")
            msg = 't-set="0" should not be set from t-value or t-valuef'
            raise SyntaxError(msg)
        _debug.logic(
            "directive_set.compiled",
            varname=varname if varname[0] != "{" else "{dict}",
            mode="value" if value_code is not None else "content",
        )
        code.extend(
            value_code
            if value_code is not None
            else self._compile_set_content(el, compile_context, varname, level)
        )

        return code

    @staticmethod
    def _check_set_varname(varname: str) -> None:
        if varname == "":
            _debug.logic("directive_set.rejected", reason="empty_varname")
            msg = "t-set"
            raise KeyError(msg)
        if (
            varname != T_CALL_SLOT
            and varname[0] != "{"
            and not VARNAME_REGEXP.match(varname)
        ):
            msg = (
                "The varname can only contain alphanumeric characters and underscores."
            )
            _debug.logic(
                "directive_set.rejected", reason="invalid_varname", varname=varname
            )
            raise SyntaxError(msg)
        if "__" in varname:
            _debug.logic(
                "directive_set.rejected", reason="dunder_varname", varname=varname
            )
            raise SyntaxError(
                f"Using variable names with '__' is not allowed: {varname!r}"
            )

    @staticmethod
    def _check_set_owns_its_node(el: etree._Element, varname: str) -> None:
        if el.attrib.pop("t-inner-content", None) is None:
            msg = (
                "t-set cannot share a node with t-out, t-field, t-esc or "
                "t-raw: the node content is already claimed by the output "
                "directive"
            )
            _debug.logic(
                "directive_set.rejected", reason="shares_output_node", varname=varname
            )
            raise SyntaxError(msg)

    def _compile_set_value(
        self, el: etree._Element, varname: str, level: int
    ) -> list[str] | None:
        if "t-value" in el.attrib:
            expr = el.attrib.pop("t-value") or "None"
            _debug.logic("directive_set.value", varname=varname, mode="expr")
            return [
                indent_code(
                    f"values[{varname!r}] = {self._compile_expr(expr)}",
                    level,
                )
            ]
        if "t-valuef" in el.attrib:
            exprf = el.attrib.pop("t-valuef")
            _debug.logic("directive_set.value", varname=varname, mode="format")
            return [
                indent_code(
                    f"values[{varname!r}] = {self._compile_format(exprf)}",
                    level,
                )
            ]
        if "t-valuef.translate" in el.attrib:
            exprf = el.attrib.pop("t-valuef.translate")
            _debug.logic(
                "directive_set.value",
                varname=varname,
                mode="translate",
                editing=bool(self.env.context.get("edit_translations")),
            )
            return [
                indent_code(
                    f"values[{varname!r}] = {self._compile_translatable_format(exprf)}",
                    level,
                )
            ]
        if varname[0] == "{":
            _debug.logic("directive_set.value", varname="{dict}", mode="dict")
            return [
                self._compile_dict_merge("values", varname, level, "checked_set_values")
            ]
        return None

    def _compile_set_content(
        self,
        el: etree._Element,
        compile_context: CompileContext,
        varname: str,
        level: int,
    ) -> list[str]:
        path, xml = compile_context.element_path, compile_context.element_xml
        content = self._compile_directive(
            el, compile_context, "inner-content", 1
        ) + self._flush_text(compile_context, 1)
        if not content:
            _debug.logic("directive_set.empty_content", varname=varname)
            return [indent_code(f"values[{varname!r}] = ''", level)]

        def_name = compile_context.make_name("t_set")
        def_code = [f"def {def_name}(self, values):"]
        def_code.append(indent_code(self._get_element_marker(path, xml), 1))
        def_code.extend(content)
        compile_context.template_functions[def_name] = def_code
        _debug.pipeline(
            "directive_set.content_function",
            varname=varname,
            function=def_name,
            lines=len(content),
        )

        return [
            indent_code(
                f"""
            values[{varname!r}] = QwebContent(self, QwebCallParameters(self.env.context, {compile_context.ref!r}, {def_name}, values.copy(), 'root', 't-set', (template_options['ref'], {path!r}, {xml!r})))
        """,
                level,
            )
        ]

    def _compile_directive_value(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        _debug.logic("directive_value.rejected", tag=el.tag, reason="not_on_t_set")
        msg = "t-value must be on the same node of t-set"
        raise SyntaxError(msg)

    def _compile_directive_valuef(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        _debug.logic("directive_valuef.rejected", tag=el.tag, reason="not_on_t_set")
        msg = "t-valuef must be on the same node of t-set"
        raise SyntaxError(msg)

    def _compile_directive_inner_content(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        el.attrib.pop("t-inner-content", None)

        parent_nsmap = compile_context.nsmap
        if el.nsmap:
            compile_context.nsmap = {**parent_nsmap, **el.nsmap}

        if el.text is not None:
            self._add_text(el.text, compile_context)
        parent_path = compile_context.element_path
        parent_xml = compile_context.element_xml
        body = []
        for item in list(el):
            if isinstance(item, etree._Comment):
                _debug.logic(
                    "inner_content.comment",
                    preserved=bool(compile_context.get("preserve_comments")),
                )
                if compile_context.get("preserve_comments"):
                    self._add_text(f"<!--{item.text}-->", compile_context)
                else:
                    self._strip_pending_trailing_ws(compile_context)
                    if item.getparent() is None and item.tail is not None:
                        tail = item.tail
                        if tail.isspace():
                            tail = tail.rstrip(" \t")
                        if tail:
                            self._add_text(tail, compile_context)
                        continue
            elif isinstance(item, etree._ProcessingInstruction):
                if compile_context.get("preserve_comments"):
                    self._add_text(f"<?{item.target} {item.text}?>", compile_context)
                else:
                    self._strip_pending_trailing_ws(compile_context)
            else:
                body.extend(self._compile_node(item, compile_context, level))
            if item.tail is not None:
                self._add_text(item.tail, compile_context)
        compile_context.element_path = parent_path
        compile_context.element_xml = parent_xml
        compile_context.nsmap = parent_nsmap
        _debug.pipeline(
            "inner_content.compiled",
            tag=el.tag,
            children=len(el),
            lines=len(body),
            namespaced=bool(el.nsmap),
        )
        return body

    def _compile_directive_if(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        expr = el.attrib.pop("t-if", None)
        if expr is None:
            expr = el.attrib.pop("t-elif", None)

        if not expr or not expr.strip():
            _debug.logic("directive_if.rejected", reason="empty_expr", tag=el.tag)
            raise ValueError("t-if or t-elif expression should not be empty.")

        strip = self._rstrip_text(compile_context)
        if self._is_t_element(el) and el.text and LSTRIP_REGEXP.search(el.text):
            strip = ""
        code = self._flush_text(compile_context, level)

        code.append(indent_code(f"if {self._compile_expr(expr)}:", level))
        body = []
        if strip:
            self._add_text(strip, compile_context)
        body.extend(
            self._compile_directives(el, compile_context, level + 1)
            + self._flush_text(compile_context, level + 1, rstrip=True)
        )
        code.extend(block_code(body, level + 1))

        next_el = el.getnext()
        comments_to_remove = []
        while isinstance(next_el, etree._Comment):
            comments_to_remove.append(next_el)
            next_el = next_el.getnext()

        if next_el is not None and {"t-else", "t-elif"} & set(next_el.attrib):
            next_el.attrib["t-else-valid"] = "True"

            parent = el.getparent()
            tails = [el.tail, *(comment.tail for comment in comments_to_remove)]
            if any(tail and not tail.isspace() for tail in tails):
                _debug.logic(
                    "directive_if.rejected",
                    reason="text_before_else",
                    comments=len(comments_to_remove),
                )
                msg = "Unexpected non-whitespace characters between t-if and t-else directives"
                raise SyntaxError(msg)
            for comment in comments_to_remove:
                parent.remove(comment)
            el.tail = None

            code.append(indent_code("else:", level))
            body = []
            if strip:
                self._add_text(strip, compile_context)
            body.extend(
                self._compile_node(next_el, compile_context, level + 1)
                + self._flush_text(compile_context, level + 1, rstrip=True)
            )
            code.extend(block_code(body, level + 1))

            next_el.attrib["t-qweb-skip"] = "True"

        return code

    def _compile_directive_elif(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        if not el.attrib.pop("t-else-valid", None):
            _debug.logic("directive_elif.rejected", reason="no_preceding_if")
            msg = "t-elif directive must be preceded by t-if or t-elif directive"
            raise SyntaxError(msg)

        return self._compile_directive_if(el, compile_context, level)

    def _compile_directive_else(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        if not el.attrib.pop("t-else-valid", None):
            _debug.logic("directive_else.rejected", reason="no_preceding_if")
            msg = "t-else directive must be preceded by t-if or t-elif directive"
            raise SyntaxError(msg)
        el.attrib.pop("t-else")
        return []

    def _compile_directive_groups(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        conditions = [
            groups
            for groups in (
                el.attrib.pop("t-groups", None),
                el.attrib.pop("groups", None),
            )
            if groups is not None
        ]

        _debug.logic("directive_groups.compiled", tag=el.tag, groups=conditions)
        strip = self._rstrip_text(compile_context)
        code = self._flush_text(compile_context, level)
        test = " and ".join(
            f"self.env.user.has_groups({groups!r})" for groups in conditions
        )
        code.append(indent_code(f"if {test}:", level))
        if strip and not self._is_t_element(el):
            self._add_text(strip, compile_context)
        code.extend(
            block_code(
                [
                    *self._compile_directives(el, compile_context, level + 1),
                    *self._flush_text(compile_context, level + 1, rstrip=True),
                ],
                level + 1,
            )
        )
        return code

    def _compile_directive_foreach(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        expr_foreach = el.attrib.pop("t-foreach")
        expr_as = el.attrib.pop("t-as")

        if not expr_as:
            _debug.logic("directive_foreach.rejected", reason="missing_as")
            msg = "t-as"
            raise KeyError(msg)

        if not VARNAME_REGEXP.match(expr_as):
            _debug.logic(
                "directive_foreach.rejected", reason="invalid_as", varname=expr_as
            )
            raise ValueError(
                f"The varname {expr_as!r} can only contain alphanumeric characters and underscores."
            )

        if self._is_t_element(el):
            self._rstrip_text(compile_context)

        code = self._flush_text(compile_context, level)

        content_foreach = self._compile_directives(
            el, compile_context, level + 1
        ) + self._flush_text(compile_context, level + 1, rstrip=True)

        t_foreach = compile_context.make_name("t_foreach")
        size = compile_context.make_name("size")
        has_value = compile_context.make_name("has_value")

        code.append(
            self._compile_foreach_iterable(
                expr_foreach, expr_as, t_foreach, size, has_value, level
            )
        )
        code.append(
            self._compile_foreach_bindings(expr_as, t_foreach, size, has_value, level)
        )

        code.extend(content_foreach or [indent_code("continue", level + 1)])
        _debug.pipeline(
            "directive_foreach.compiled",
            varname=expr_as,
            numeric=expr_foreach.isdecimal(),
            body_lines=len(content_foreach),
        )

        return code

    def _compile_foreach_iterable(
        self,
        expr_foreach: str,
        expr_as: str,
        t_foreach: str,
        size: str,
        has_value: str,
        level: int,
    ) -> str:
        if expr_foreach.isdecimal():
            _debug.logic(
                "directive_foreach.iterable",
                kind="range",
                size=int(expr_foreach),
                alias=expr_as,
            )
            return indent_code(
                f"""
            values[{expr_as + "_size"!r}] = {size} = {int(expr_foreach)!r}
            {t_foreach} = range({size})
            {has_value} = False
        """,
                level,
            )
        _debug.logic("directive_foreach.iterable", kind="expr", alias=expr_as)
        return indent_code(
            f"""
        {t_foreach} = {self._compile_expr(expr_foreach)} or []
        if isinstance({t_foreach}, Sized):
            values[{expr_as + "_size"!r}] = {size} = len({t_foreach})
        elif ({t_foreach}).__class__ == int:
            values[{expr_as + "_size"!r}] = {size} = {t_foreach}
            {t_foreach} = range({size})
        else:
            values[{expr_as + "_size"!r}] = {size} = None
        {has_value} = False
        if isinstance({t_foreach}, Mapping):
            {t_foreach} = {t_foreach}.items()
            {has_value} = True
    """,
            level,
        )

    @staticmethod
    def _compile_foreach_bindings(
        expr_as: str, t_foreach: str, size: str, has_value: str, level: int
    ) -> str:
        return indent_code(
            f"""
            for index, item in enumerate({t_foreach}):
                values[{expr_as + "_index"!r}] = index
                if {has_value}:
                    values[{expr_as!r}], values[{expr_as + "_value"!r}] = item
                else:
                    values[{expr_as!r}] = values[{expr_as + "_value"!r}] = item
                values[{expr_as + "_first"!r}] = index == 0
                if {size} is not None:
                    values[{expr_as + "_last"!r}] = index + 1 == {size}
                else:
                    # Lazy iterables (generators: not Sized/int/Mapping) have no
                    # knowable last element. Assign False every iteration anyway,
                    # so a caller-provided or outer-loop ``*_last`` cannot leak
                    # into the loop body (see test_foreach_lazy_last_no_leak).
                    values[{expr_as + "_last"!r}] = False
                values[{expr_as + "_odd"!r}] = odd = index % 2
                values[{expr_as + "_even"!r}] = not odd
                values[{expr_as + "_parity"!r}] = 'odd' if odd else 'even'
        """,
            level,
        )

    def _compile_directive_as(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        if "t-foreach" not in el.attrib:
            msg = "t-as must be on the same node of t-foreach"
            raise SyntaxError(msg)
        return []

    def _compile_directive_out(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        ttype, expr = self._compile_out_target(el)

        code = self._flush_text(compile_context, level)

        path, xml = compile_context.element_path, compile_context.element_xml

        has_options = el.attrib.pop("t-consumed-options", None) is not None
        tag_open = self._compile_directive(
            el, compile_context, "tag-open", level + 1
        ) + self._flush_text(compile_context, level + 1)
        tag_close = self._compile_directive(
            el, compile_context, "tag-close", level + 1
        ) + self._flush_text(compile_context, level + 1)
        default_body = self._compile_directive(
            el, compile_context, "inner-content", level + 1
        ) + self._flush_text(compile_context, level + 1)

        if expr == T_CALL_SLOT and not has_options:
            _debug.logic("directive_out.slot_passthrough", ttype=ttype, tag=el.tag)
            text = (
                "self._compile_to_str(content)"
                if ttype == "t-raw"
                else "str(escape(self._compile_to_str(content)))"
            )
            code.append(indent_code("if True:", level))
            code.extend(tag_open)
            code.append(
                indent_code(
                    f"""
                self.env.context['_qweb_error_path_xml'][:] = (template_options['ref'], {path!r}, {xml!r})
                content = values.get({T_CALL_SLOT!r}, '')
                if isinstance(content, QwebContent):
                    yield content
                elif content is not None and content is not False:
                    yield {text}
                """,
                    level + 1,
                )
            )
            code.extend(tag_close)
            return code

        set_code, force_display_dependent = self._compile_out_set_content(
            el, ttype, expr, has_options, level
        )
        code.extend(set_code)
        code.extend(
            self._compile_out_emit(
                compile_context,
                tag_open,
                tag_close,
                default_body,
                force_display_dependent,
                path,
                xml,
                level,
            )
        )
        return code

    def _compile_out_target(self, el: etree._Element) -> tuple[str, str]:
        present = [name for name in OUTPUT_DIRECTIVES if name in el.attrib]
        if len(present) > 1:
            _debug.logic(
                "directive_out.rejected", reason="multiple_outputs", present=present
            )
            raise SyntaxError(
                f"A node can carry only one output directive, got {', '.join(present)}"
            )
        for ttype in OUTPUT_DIRECTIVES[:-1]:
            expr = el.attrib.pop(ttype, None)
            if expr is not None:
                return ttype, expr
        return "t-raw", el.attrib.pop("t-raw")

    def _compile_out_set_content(
        self,
        el: etree._Element,
        ttype: str,
        expr: str,
        has_options: bool,
        level: int,
    ) -> tuple[list[str], bool]:
        if ttype == "t-field":
            record, field_name = expr.rsplit(".", 1)
            _debug.logic("directive_out.field", field=field_name, tag=el.tag)
            return [
                indent_code(
                    f"""
                content, force_display = self._get_field({self._compile_expr(record, raise_on_missing=True)}, {field_name!r}, {expr!r}, {el.tag!r}, values.pop('__qweb_options__', {{}}), values)
                if content is not None and content is not False:
                    content = self._compile_to_str(content)
                """,
                    level,
                )
            ], True

        if expr == T_CALL_SLOT:
            code = [indent_code(f"content = values.get({T_CALL_SLOT!r}, '')", level)]
        else:
            code = [indent_code(f"content = {self._compile_expr(expr)}", level)]

        _debug.logic(
            "directive_out.content",
            tag=el.tag,
            source="slot" if expr == T_CALL_SLOT else "expr",
            widget=has_options,
            raw=ttype == "t-raw",
        )
        force_display_dependent = has_options
        if force_display_dependent:
            code.append(
                indent_code(
                    f"""
                content, force_display = self._get_widget(content, {expr!r}, {el.tag!r}, values.pop('__qweb_options__', {{}}), values)
                if content is not None and content is not False:
                    content = self._compile_to_str(content)
                """,
                    level,
                )
            )

        if ttype == "t-raw":
            code.append(
                indent_code(
                    """
                if content is not None and content is not False:
                    content = Markup(content)
                """,
                    level,
                )
            )

        return code, force_display_dependent

    def _compile_out_emit(
        self,
        compile_context: CompileContext,
        tag_open: list[str],
        tag_close: list[str],
        default_body: list[str],
        force_display_dependent: bool,
        path: str | None,
        xml: str | None,
        level: int,
    ) -> list[str]:
        code = [indent_code("if content is not None and content is not False:", level)]
        code.extend(tag_open)
        code.append(
            indent_code(
                f"""
            if content.__class__ is str:
                yield escape_str(content)
            elif isinstance(content, QwebContent):
                self.env.context['_qweb_error_path_xml'][:] = (template_options['ref'], {path!r}, {xml!r})
                yield content
            else:
                yield escape_text(self._compile_to_str(content))
        """,
                level + 1,
            )
        )
        code.extend(tag_close)

        if default_body:
            code.append(indent_code("else:", level))
            code.extend(block_code([*tag_open, *default_body, *tag_close], level + 1))
        elif force_display_dependent:
            if tag_open + tag_close:
                code.append(indent_code("elif force_display:", level))
                code.extend(tag_open + tag_close)

            code.append(
                indent_code("""else: values.pop('__qweb_attrs__', None)""", level)
            )

        _debug.logic(
            "directive_out.emitted",
            default_body=bool(default_body),
            force_display=force_display_dependent,
            wrapped=bool(tag_open),
        )
        return code

    def _compile_directive_esc(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        if compile_context.get("dev_mode"):
            _logger.warning(
                "Found deprecated directive @t-esc=%r in template %r. Replace by @t-out",
                el.get("t-esc"),
                compile_context.ref or "<unknown>",
            )
        return self._compile_directive_out(el, compile_context, level)

    def _compile_directive_raw(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        _logger.warning(
            "Found deprecated directive @t-raw=%r in template %r. Replace by "
            "@t-out, and explicitely wrap content in `Markup` if "
            "necessary (which likely is not the case)",
            el.get("t-raw"),
            compile_context.ref or "<unknown>",
        )
        return self._compile_directive_out(el, compile_context, level)

    def _compile_directive_field(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        tag_name = self._get_tag_names(el)[0]
        if tag_name in FORBIDDEN_FIELD_TAGS:
            raise ValueError(
                f"QWeb widgets do not work correctly on {tag_name!r} elements"
            )
        if tag_name == "t":
            raise ValueError(
                "t-field can not be used on a t element, provide an actual HTML node"
            )
        if "." not in (el.get("t-field") or ""):
            raise ValueError(
                "t-field must have at least a dot like 'record.field_name'"
            )

        return self._compile_directive_out(el, compile_context, level)

    def _compile_directive_call(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        expr = el.attrib.pop("t-call")

        el_tag, _prefixed = self._get_tag_names(el)
        if el_tag != "t":
            _debug.logic("directive_call.rejected", reason="not_t_element", tag=el_tag)
            raise SyntaxError(
                f"t-call must be on a <t> element (actually on <{el_tag}>)."
            )

        code = self._flush_text(compile_context, level, rstrip=True)
        path, xml = compile_context.element_path, compile_context.element_xml

        has_options = el.attrib.pop("t-consumed-options", None) is not None
        code.extend(self._compile_call_options(compile_context, level, has_options))
        code.extend(self._compile_call_content(el, compile_context, level))
        code.extend(self._compile_call_values(el, level))

        static = expr.isdecimal()
        dynamic = not static and FORMAT_REGEX.search(expr) is not None
        template = repr(int(expr)) if static else self._compile_format(expr)
        _debug.pipeline(
            "directive_call.compiled",
            target=expr[:80],
            numeric=static,
            dynamic=dynamic,
            nsmap=len(compile_context.nsmap),
        )

        code.append(indent_code(f"template = {template}", level))
        if dynamic:
            code.append(
                indent_code(
                    """
                if template.isdecimal():
                    template = int(template)
                """,
                    level,
                )
            )

        code.append(
            indent_code(
                f"yield QwebCallParameters(t_call_options, template, None, t_call_values, True, 't-call', (template_options['ref'], {path!r}, {xml!r}))",
                level,
            )
        )

        return code

    def _compile_call_options(
        self, compile_context: CompileContext, level: int, has_options: bool = True
    ) -> list[str]:
        code = [
            indent_code(
                "t_call_options = checked_call_options(values.pop('__qweb_options__', {}))"
                if has_options
                else "t_call_options = {}",
                level,
            )
        ]
        if not compile_context.nsmap:
            return code

        code.append(
            indent_code(
                f"t_call_options.update(nsmap={compile_context.nsmap!r})", level
            )
        )
        return code

    def _compile_call_content(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        path, xml = compile_context.element_path, compile_context.element_xml

        if not (list(el) or el.text):
            _debug.logic("directive_call.empty_content", tag=el.tag)
            return [indent_code(f"t_call_values = {{{T_CALL_SLOT!r}: '' }}", level)]

        is_deprecated_version = not any(
            not key.startswith("t-") for key in el.attrib
        ) and any(n.attrib.get("t-set") for n in el)

        def_name = compile_context.make_name("t_call")
        code_content = [f"def {def_name}(self, values):"]
        code_content.append(indent_code(self._get_element_marker(path, xml), 1))
        code_content.extend(
            self._compile_directive(el, compile_context, "inner-content", 1)
        )
        code_content.extend(self._flush_text(compile_context, 1, rstrip=True))

        compile_context.template_functions[def_name] = code_content
        _debug.pipeline(
            "directive_call.content_function",
            function=def_name,
            deprecated=is_deprecated_version,
            lines=len(code_content),
        )

        code = [
            indent_code(
                f"""
            t_call_content_values = values.copy()
            t_call_content = QwebContent(self, QwebCallParameters(self.env.context, {compile_context.ref!r}, {def_name}, t_call_content_values, 'root', 'inner-content', (template_options['ref'], {path!r}, {xml!r})))
            t_call_values = {{{T_CALL_SLOT!r}: t_call_content}}
        """,
                level,
            )
        ]

        if is_deprecated_version:
            code.append(
                indent_code(
                    """
                str(t_call_content)
                new_values = {k: v for k, v in t_call_content_values.items() if k != '__qweb_attrs__' and values.get(k) is not v}
                t_call_values.update(new_values)
            """,
                    level,
                )
            )
        return code

    def _compile_call_values(self, el: etree._Element, level: int) -> list[str]:
        code = []
        for key in list(el.attrib):
            if key.endswith(".f"):
                name = self._check_call_value_name(key.removesuffix(".f"))
                value = el.attrib.pop(key)
                code.append(
                    indent_code(
                        f"t_call_values[{name!r}] = {self._compile_format(value)}",
                        level,
                    )
                )
            elif key.endswith(".translate"):
                name = self._check_call_value_name(key.removesuffix(".translate"))
                value = el.attrib.pop(key)
                code.append(
                    indent_code(
                        f"t_call_values[{name!r}] = {self._compile_translatable_format(value)}",
                        level,
                    )
                )
            elif not key.startswith("t-"):
                name = self._check_call_value_name(key)
                value = el.attrib.pop(key)
                code.append(
                    indent_code(
                        f"t_call_values[{name!r}] = {self._compile_expr(value)}",
                        level,
                    )
                )
            elif key == "t-args":
                value = el.attrib.pop(key)
                code.append(
                    self._compile_dict_merge(
                        "t_call_values", value, level, "checked_call_values"
                    )
                )
        _debug.pipeline("directive_call.values_compiled", tag=el.tag, values=len(code))
        return code

    @staticmethod
    def _check_call_value_name(name: str) -> str:
        if "__" in name:
            _debug.logic("directive_call.rejected", reason="reserved", key=name)
            msg = f"t-call value {name!r} is reserved for the renderer"
            raise SyntaxError(msg)
        return name

    def _compile_directive_lang(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        if "t-call" not in el.attrib:
            msg = "t-lang is an alias of t-options-lang but only available on the same node of t-call"
            raise SyntaxError(msg)
        el.attrib["t-options-lang"] = el.attrib.pop("t-lang")
        return []

    def _compile_directive_call_assets(
        self, el: etree._Element, compile_context: CompileContext, level: int
    ) -> list[str]:
        if len(el) > 0:
            _debug.logic(
                "call_assets_rejected", reason="has_children", children=len(el)
            )
            msg = "t-call-assets cannot contain children nodes"
            raise SyntaxError(msg)

        code = self._flush_text(compile_context, level)
        xmlid = el.attrib.pop("t-call-assets")
        css = self._compile_bool(el.attrib.pop("t-css", True))
        js = self._compile_bool(el.attrib.pop("t-js", True))
        defer_load = self._compile_bool(el.attrib.pop("defer_load", False))
        lazy_load = self._compile_bool(el.attrib.pop("lazy_load", False))
        media = el.attrib.pop("media", False)
        autoprefix = self._compile_bool(el.attrib.pop("t-autoprefix", False))
        _debug.logic("call_assets_compiled", bundle=xmlid, css=css, js=js, media=media)
        code.append(
            indent_code(
                f"""
            t_call_assets_nodes = self._get_asset_nodes(
                {xmlid!r},
                css={css},
                js={js},
                debug=values.get("debug"),
                defer_load={defer_load},
                lazy_load={lazy_load},
                media={media!r},
                autoprefix={autoprefix},
                page=True,
            )
        """.strip(),
                level,
            )
        )

        code.append(
            indent_code(
                "yield from self._render_asset_nodes(t_call_assets_nodes)", level
            )
        )

        return code

    def _render_asset_nodes(
        self, nodes: Iterable[tuple[str, Mapping[str, Any] | None]]
    ) -> Iterator[str]:
        for index, (tag_name, asset_attrs) in enumerate(nodes):
            if index:
                yield "\n        "
            text_content = asset_attrs.get("text") if asset_attrs else None
            attrs = self._post_processing_att(
                tag_name,
                {k: v for k, v in asset_attrs.items() if k != "text"}
                if asset_attrs
                else {},
                is_static=True,
            )
            if tag_name == "script" or (
                tag_name == "link" and attrs.get("rel") == "modulepreload"
            ):
                nonce = self._script_nonce()
                if nonce:
                    attrs["nonce"] = nonce
            attributes = format_attributes(attrs)
            if tag_name in VOID_ELEMENTS:
                yield f"<{tag_name}{attributes}/>"
            else:
                yield f"<{tag_name}{attributes}>{text_content or ''}</{tag_name}>"

    def _script_nonce(self) -> str | None:
        if self.env.context.get("script_nonce") is False:
            return None
        nonce = request.csp_nonce if request else None
        return nonce if isinstance(nonce, str) else None

    def _script_nonce_attribute(self) -> str:
        nonce = self._script_nonce()
        return f' nonce="{nonce}"' if nonce else ""

    def _debug_trace(self, debugger: str, values: dict[str, Any]) -> None:
        if debugger:
            _debug.logic("debug_trace.rejected", debugger=debugger)
            raise ValueError(
                f"unsupported t-debug value {debugger!r}: keep it empty and "
                "configure the ``breakpoint`` builtin instead"
            )
        breakpoint()  # noqa: T100 -- Implements the explicitly requested t-debug template directive.

    def _post_processing_att(
        self, tag_name: str, atts: dict[str, Any], *, is_static: bool = False
    ) -> dict[str, Any]:
        if not is_static:
            for attr, value in atts.items():
                if (
                    value
                    and not isinstance(value, TemplateAttributeValue)
                    and str(attr).lower() in POST_PROCESSING_ATT_NAMES
                    and is_executable_url(value, tag_name)
                ):
                    _debug.logic("attribute_scheme_stripped", tag=tag_name, attr=attr)
                    atts[attr] = ""
        return atts

    def _get_post_processing_att_names(self) -> frozenset[str] | None:
        return POST_PROCESSING_ATT_NAMES

    def _get_field_converter(self, widget_type: str) -> models.BaseModel:
        model = "ir.qweb.field." + widget_type
        if model in self.env:
            return self.env[model]
        _debug.logic("field_converter_fallback", widget=widget_type)
        return self.env["ir.qweb.field"]

    def _get_field(
        self,
        record: models.BaseModel,
        field_name: str,
        expression: str,
        tag_name: str,
        field_options: dict[str, Any],
        values: dict[str, Any],
    ) -> tuple[str | Markup | bool | None, bool]:
        field = record._fields[field_name]

        field_options["tagName"] = tag_name
        field_options["expression"] = expression
        field_options["type"] = field_options.get("widget", field.type)
        inherit_branding = (
            self.env.context["inherit_branding"]
            if "inherit_branding" in self.env.context
            else self.env.context.get("inherit_branding_auto")
            and record.has_access("write")
        )
        field_options["inherit_branding"] = inherit_branding
        translate = (
            self.env.context.get("edit_translations")
            and values.get("translatable")
            and field.translate
        )
        field_options["translate"] = translate

        converter = self._get_field_converter(field_options["type"])
        content = converter.record_to_html(record, field_name, field_options)
        attributes = converter.attributes(record, field_name, field_options, values)
        self._merge_node_attributes(values, attributes)
        _debug.pipeline(
            "field_rendered",
            model=record._name,
            field=field_name,
            widget=field_options["type"],
            branding=bool(inherit_branding),
            translate=bool(translate),
            attributes=len(attributes),
        )

        return (content, inherit_branding or translate)

    def _get_widget(
        self,
        value: Any,
        expression: str,
        tag_name: str,
        field_options: dict[str, Any],
        values: dict[str, Any],
    ) -> tuple[str | Markup | bool | None, bool | None]:
        widget = field_options.get("widget")
        if not widget:
            _debug.logic("widget_rejected", reason="no_widget", expression=expression)
            msg = (
                f"t-options on the t-out/t-esc {expression!r} requires a "
                "'widget' option, e.g. t-options-widget=\"'date'\" or "
                "t-options=\"{'widget': 'date'}\""
            )
            raise ValueError(msg)
        field_options["type"] = widget
        field_options["tagName"] = tag_name
        field_options["expression"] = expression
        inherit_branding = self.env.context.get("inherit_branding")
        field_options["inherit_branding"] = inherit_branding

        if value is None or value is False:
            _debug.logic("widget_skipped", reason="no_value", expression=expression)
            content = None
        else:
            converter = self._get_field_converter(field_options["type"])
            content = converter.value_to_html(value, field_options)
        if inherit_branding:
            self._merge_node_attributes(
                values,
                {
                    "data-oe-type": field_options["type"],
                    "data-oe-expression": field_options["expression"],
                },
            )
        _debug.pipeline(
            "widget_rendered",
            widget=widget,
            tag=tag_name,
            branding=bool(inherit_branding),
            value_type=type(value).__name__,
        )

        return (content, inherit_branding)

    @staticmethod
    def _merge_node_attributes(
        values: dict[str, Any], attributes: dict[str, Any]
    ) -> None:
        node_attributes = values.get("__qweb_attrs__")
        if node_attributes is None:
            values["__qweb_attrs__"] = attributes
        else:
            node_attributes.update(attributes)


class _StandaloneCursor:
    dbname = None

    def __init__(self) -> None:
        self.cache: dict[str, Any] = {}


class _StandaloneRegistry:
    db_name = None

    def __init__(self) -> None:
        self.ormcache_lrus = {
            cache_name: LRU(cache_size)
            for cache_name, cache_size in REGISTRY_CACHES.items()
        }


class _StandaloneEnv(dict):
    def __init__(
        self,
        registry: _StandaloneRegistry | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.registry = registry if registry is not None else _StandaloneRegistry()
        self.context: dict[str, Any] = {} if context is None else dict(context)
        self.cr = _StandaloneCursor()

    def __call__(
        self,
        cr: Any = None,
        user: Any = None,
        context: dict[str, Any] | None = None,
        su: Any = None,
    ) -> _StandaloneEnv:
        return _StandaloneEnv(
            registry=self.registry,
            context=self.context if context is None else context,
        )


class _StandaloneQweb(IrQweb):
    _register = False

    @property
    def pool(self) -> _StandaloneRegistry:
        return self.env.registry

    def _get_template_info(self, id_or_xmlid: int | str) -> dict[str, Any]:
        return defaultdict(lambda: None, id=id_or_xmlid)

    def _preload_trees(
        self, refs: Sequence[int | str]
    ) -> dict[int | str, dict[str, Any]]:
        values = {}
        for ref in refs:
            tree, vid = self.env.context["load"](ref)
            values[ref] = values[vid] = {
                "tree": tree,
                "template": lazy(etree.tostring, tree, encoding="unicode"),
                "xmlid": vid,
                "ref": vid,
            }
        return values

    def _prepare_environment(self, values: dict[str, Any]) -> Self:
        values["true"] = True
        values["false"] = False
        return self

    def _get_field(self, *args: Any) -> None:
        msg = "Fields are not allowed in this rendering mode. Please use \"env['ir.qweb']._render\" method"
        raise NotImplementedError(msg)

    def _get_widget(self, *args: Any) -> None:
        msg = "Widgets are not allowed in this rendering mode. Please use \"env['ir.qweb']._render\" method"
        raise NotImplementedError(msg)

    def _get_asset_nodes(self, *args: Any) -> None:
        msg = "Assets are not allowed in this rendering mode. Please use \"env['ir.qweb']._render\" method"
        raise NotImplementedError(msg)


def render(
    template_name: str | int, values: dict[str, Any], load: Any, **options: Any
) -> Markup:
    renderer = _StandaloneQweb(_StandaloneEnv(), (), ())
    return renderer._render(
        template_name, values, load=load, minimal_qcontext=True, **options
    )
