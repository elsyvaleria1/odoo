from __future__ import annotations

import copy
import dataclasses
import functools
import inspect
import io
import logging
import typing
from annotationlib import Format

import docutils.core
from docutils import nodes, parsers, readers, writers

from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.rst import SAFE_SETTINGS, SafeHtmlWriter

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterator

__all__ = [
    "RST_INFO_FIELDS",
    "Param",
    "Return",
    "Signature",
    "parse_signature",
    "render_docstring",
]

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

EMPTY: typing.Final = inspect.Parameter.empty

RST_INFO_FIELDS: typing.Final[dict[str, str]] = {
    "param": "param",
    "parameter": "param",
    "arg": "param",
    "argument": "param",
    "key": "param",
    "keyword": "param",
    "type": "type",
    "raises": "raises",
    "raise": "raises",
    "except": "raises",
    "exception": "raises",
    "var": "var",
    "ivar": "var",
    "cvar": "var",
    "vartype": "vartype",
    "returns": "returns",
    "return": "returns",
    "rtype": "rtype",
    "meta": "meta",
}

NON_CALL_FIELDS: typing.Final[frozenset[str]] = frozenset({"var", "vartype", "meta"})

_PARSE_ERROR: typing.Final = '''\
Unable to parse the docstring as reStructuredText.
Want to help fix the docstrings? Check out the test_docstring linter!
"""
{}
"""
{}'''

_FRAGMENT_READER_SETTINGS: typing.Final = {
    "doctitle_xform": False,
    "docinfo_xform": False,
    "sectsubtitle_xform": False,
}


def _prepare_settings(writer_name: str, overrides: dict[str, typing.Any]) -> typing.Any:
    parser = parsers.get_parser_class("restructuredtext")()
    reader = readers.get_reader_class("standalone")(parser)
    writer = writers.get_writer_class(writer_name)()
    publisher = docutils.core.Publisher(reader=reader, parser=parser, writer=writer)
    publisher.process_programmatic_settings(None, overrides, None)
    return publisher.settings


@functools.cache
def _prepare_tree_settings() -> typing.Any:
    return _prepare_settings(
        "pseudoxml", {**SAFE_SETTINGS, **_FRAGMENT_READER_SETTINGS}
    )


@functools.cache
def _html_settings() -> typing.Any:
    return _prepare_settings("html", {**SAFE_SETTINGS, "embed_stylesheet": False})


@functools.cache
def _get_empty_root_factory() -> Callable[[], nodes.document]:
    return docutils.core.publish_doctree("").copy


def _to_doctree(docstring: str) -> nodes.document:
    settings = copy.copy(_prepare_tree_settings())
    settings.warning_stream = warnings = io.StringIO()
    doctree = docutils.core.publish_doctree(docstring, settings=settings)
    if warnings.tell():
        _debug.logic("docstring.parse_warnings", chars=len(docstring))
        _logger.warning(_PARSE_ERROR.format(docstring, warnings.getvalue()))
    return doctree


def _render_doctree_html(tree: nodes.Node) -> str:
    if isinstance(tree, nodes.document):
        document, part = tree, "html_body"
    else:
        document, part = _get_empty_root_factory()(), "body"
        document.append(tree)
    writer = SafeHtmlWriter()
    docutils.core.publish_from_doctree(
        document, writer=writer, settings=_html_settings()
    )
    return writer.parts[part].strip()


def _render_children_html(tree: nodes.Element) -> str:
    return "".join(_render_doctree_html(child) for child in tree.children)


class _InfoField(typing.NamedTuple):
    kind: str | None
    name: str
    body: nodes.Element
    raw: str


def _iter_info_fields(doctree: nodes.document) -> Iterator[_InfoField]:
    field_lists = [node for node in doctree if isinstance(node, nodes.field_list)]
    for field_list in field_lists:
        for field in field_list:
            field_name, field_body = field.children
            raw = str(field_name[0])
            kind, _, name = raw.partition(" ")
            yield _InfoField(RST_INFO_FIELDS.get(kind), name.strip(), field_body, raw)
        doctree.remove(field_list)


def _stringify_annotation(annotation: typing.Any) -> str | None:
    if annotation is EMPTY:
        return None
    if isinstance(annotation, str):
        return annotation
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation)


ParamKind = typing.Literal[
    "POSITIONAL_ONLY",
    "POSITIONAL_OR_KEYWORD",
    "VAR_POSITIONAL",
    "KEYWORD_ONLY",
    "VAR_KEYWORD",
]


@dataclasses.dataclass(slots=True)
class Param:
    name: str
    kind: ParamKind
    default: typing.Any
    annotation: str | None
    doc: str | None

    @classmethod
    def from_inspect(cls, parameter: inspect.Parameter) -> Param:
        return cls(
            name=parameter.name,
            kind=typing.cast("ParamKind", parameter.kind.name),
            default=parameter.default,
            annotation=_stringify_annotation(parameter.annotation),
            doc=None,
        )

    def as_dict(self) -> dict[str, typing.Any]:
        d: dict[str, typing.Any] = {
            "name": self.name,
            "kind": self.kind,
            "default": self.default,
            "annotation": self.annotation,
            "doc": self.doc,
        }
        if self.kind == "POSITIONAL_OR_KEYWORD":
            del d["kind"]
        if self.annotation is None:
            del d["annotation"]
        if self.doc is None:
            del d["doc"]
        if self.default is EMPTY:
            del d["default"]
        else:
            try:
                json_dumps(self.default)
            except TypeError, ValueError:
                del d["default"]
        return d


@dataclasses.dataclass(slots=True)
class Return:
    annotation: str | None
    doc: str | None

    def as_dict(self) -> dict[str, typing.Any]:
        d: dict[str, typing.Any] = {}
        if self.annotation is not None:
            d["annotation"] = self.annotation
        if self.doc is not None:
            d["doc"] = self.doc
        return d


@dataclasses.dataclass(slots=True)
class Signature:
    parameters: dict[str, Param]
    return_: Return
    api: list[str]
    raise_: dict[str, str]
    doc: str | None

    def as_dict(self) -> dict[str, typing.Any]:
        d: dict[str, typing.Any] = {
            "signature": self.stringify(annotation=False),
            "parameters": {
                (p := param.as_dict()).pop("name"): p
                for param in self.parameters.values()
            },
        }
        if return_dict := self.return_.as_dict():
            d["return"] = return_dict
        if self.api:
            d["api"] = self.api
        if self.raise_:
            d["raise"] = self.raise_
        if self.doc is not None:
            d["doc"] = self.doc
        return d

    def stringify(
        self,
        annotation: bool = True,
        default: bool = True,
        return_annotation: bool = True,
    ) -> str:
        rendered: list[str] = []
        previous: str | None = None
        starred = False
        for name, param in self.parameters.items():
            if previous == "POSITIONAL_ONLY" and param.kind != "POSITIONAL_ONLY":
                rendered.append("/")
            if param.kind == "VAR_POSITIONAL":
                starred = True
            elif param.kind == "KEYWORD_ONLY" and not starred:
                rendered.append("*")
                starred = True

            text = name
            if param.kind == "VAR_POSITIONAL":
                text = f"*{name}"
            elif param.kind == "VAR_KEYWORD":
                text = f"**{name}"
            if annotation and param.annotation:
                text += f": {param.annotation}"
                if default and param.default is not EMPTY:
                    text += f" = {param.default!r}"
            elif default and param.default is not EMPTY:
                text += f"={param.default!r}"
            rendered.append(text)
            previous = param.kind
        if previous == "POSITIONAL_ONLY":
            rendered.append("/")

        out = f"({', '.join(rendered)})"
        if return_annotation and self.return_.annotation:
            out += f" -> {self.return_.annotation}"
        return out


def render_docstring(text: str) -> str:
    return _render_doctree_html(_to_doctree(inspect.cleandoc(text)))


def parse_signature(
    method: Callable[..., typing.Any],
    *,
    docstring: str | None = None,
    normalize_return: Callable[[str | None], str | None] | None = None,
) -> Signature:
    isign = inspect.signature(method, annotation_format=Format.STRING)

    parameters = list(isign.parameters.values())
    if parameters and parameters[0].name in ("self", "cls"):
        isign = isign.replace(parameters=parameters[1:])

    return_annotation = _stringify_annotation(isign.return_annotation)
    if normalize_return is not None:
        return_annotation = normalize_return(return_annotation)

    signature = Signature(
        parameters={
            param_name: Param.from_inspect(param)
            for param_name, param in isign.parameters.items()
        },
        return_=Return(return_annotation, doc=None),
        api=[],
        raise_={},
        doc=None,
    )

    if documentation := (docstring if docstring is not None else method.__doc__):
        _enhance_signature_using_docstring(signature, documentation)

    return signature


def _enhance_signature_using_docstring(signature: Signature, docstring: str) -> None:
    doctree = _to_doctree(inspect.cleandoc(docstring))

    fields = 0
    unmatched = 0
    for field in _iter_info_fields(doctree):
        fields += 1
        if (
            field.kind in ("param", "type")
            and field.name.rpartition(" ")[2].strip() not in signature.parameters
        ):
            unmatched += 1
        match (field.kind, field.name):
            case (None, _):
                _logger.warning(
                    _PARSE_ERROR.format(docstring, f"cannot parse {field.raw}")
                )
            case (kind, _) if kind in NON_CALL_FIELDS:
                pass
            case ("param", annotated_name) if " " in annotated_name:
                annotation, _, name = annotated_name.rpartition(" ")
                if param := signature.parameters.get(name.strip()):
                    if not param.annotation:
                        param.annotation = annotation.strip()
                    param.doc = _render_children_html(field.body)
            case ("param", name):
                if param := signature.parameters.get(name):
                    param.doc = _render_children_html(field.body)
            case ("type", name):
                if not field.body.children:
                    _logger.warning(
                        _PARSE_ERROR.format(
                            docstring, f"empty :type: field {field.raw}"
                        )
                    )
                elif (param := signature.parameters.get(name)) and not param.annotation:
                    param.annotation = field.body.children[0].astext().strip()
            case ("returns", ""):
                signature.return_.doc = _render_children_html(field.body)
            case ("rtype", ""):
                if not field.body.children:
                    _logger.warning(
                        _PARSE_ERROR.format(
                            docstring, f"empty :rtype: field {field.raw}"
                        )
                    )
                elif not signature.return_.annotation:
                    signature.return_.annotation = (
                        field.body.children[0].astext().strip()
                    )
            case ("raises", exception):
                signature.raise_[exception] = _render_children_html(field.body)
            case _:
                _logger.warning(
                    _PARSE_ERROR.format(docstring, f"cannot parse {field.raw}")
                )

    _debug.logic(
        "docstring.signature_enhanced",
        fields=fields,
        unmatched=unmatched,
        params=len(signature.parameters),
    )
    signature.doc = _render_doctree_html(doctree)
