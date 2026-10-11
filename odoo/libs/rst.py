from __future__ import annotations

import io
import typing
from collections.abc import Iterator

from docutils import nodes
from docutils.core import publish_string
from docutils.transforms import Transform, writer_aux
from docutils.writers.html4css1 import Writer

from odoo.libs.web.urls import SAFE_LINK_SCHEMES, url_scheme

__all__ = [
    "SAFE_SETTINGS",
    "SafeHtmlWriter",
    "render_html",
]

SAFE_SETTINGS: typing.Final[dict[str, typing.Any]] = {
    "report_level": 3,
    "halt_level": 5,
    "raw_enabled": False,
    "file_insertion_enabled": False,
    "_disable_config": True,
}


class _DropSystemMessages(Transform):
    default_priority = 870

    def apply(self) -> None:
        for node in list(self.document.findall(nodes.system_message)):
            node.parent.remove(node)


def _is_safe_uri(uri: str) -> bool:
    scheme = url_scheme(uri)
    return not scheme or scheme in SAFE_LINK_SCHEMES


def _unwrapped(children: list[nodes.Node], dropped: set[int]) -> Iterator[nodes.Node]:
    for child in children:
        if id(child) not in dropped:
            yield child
            continue
        first = child.children[0] if child.children else None
        if isinstance(first, nodes.Element):
            first.update_basic_atts(child)
        yield from _unwrapped(child.children, dropped)


def _parents(dropped_nodes: list[nodes.Element]) -> list[nodes.Element]:
    return list({id(node.parent): node.parent for node in dropped_nodes}.values())


class _DropUnsafeUris(Transform):
    default_priority = 871

    def apply(self) -> None:
        references = [
            reference
            for reference in self.document.findall(nodes.reference)
            if not _is_safe_uri(reference.get("refuri", ""))
        ]
        dropped = {id(reference) for reference in references}
        for parent in _parents(references):
            if id(parent) in dropped:
                continue
            children = list(_unwrapped(parent.children, dropped))
            for child in children:
                if child.parent is not parent:
                    parent.setup_child(child)
            parent.children[:] = children
        images = [
            image
            for image in self.document.findall(nodes.image)
            if not _is_safe_uri(image.get("uri", ""))
        ]
        dropped = {id(image) for image in images}
        for parent in _parents(images):
            parent.children[:] = [
                child for child in parent.children if id(child) not in dropped
            ]


class SafeHtmlWriter(Writer):
    def get_transforms(self) -> list[type[Transform]]:
        return [_DropSystemMessages, _DropUnsafeUris, writer_aux.Admonitions]


def render_html(source: str) -> tuple[str, str]:
    warnings = io.StringIO()
    html = publish_string(
        source=source,
        writer=SafeHtmlWriter(),
        settings_overrides={
            **SAFE_SETTINGS,
            "embed_stylesheet": False,
            "doctitle_xform": False,
            "output_encoding": "unicode",
            "xml_declaration": False,
            "warning_stream": warnings,
        },
    )
    return html, warnings.getvalue().strip()
