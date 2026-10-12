import itertools
from collections.abc import Iterator

import lxml.html
from lxml import etree
from markupsafe import Markup, escape

from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


def parse_body_fragments(body: str) -> list[etree._Element | str]:
    try:
        return lxml.html.fragments_fromstring(body)
    except ValueError:
        _debug.logic("body_parsed_as_bytes", length=len(body))
        return lxml.html.fragments_fromstring(body.encode("utf-8"))


def iter_fragment_elements(
    fragments: list[etree._Element | str], tag: str | None = None
) -> Iterator[etree._Element]:
    nodes = (f for f in fragments if not isinstance(f, str))
    if tag is None:
        return itertools.chain.from_iterable(node.iter() for node in nodes)
    return itertools.chain.from_iterable(node.iter(tag) for node in nodes)


def render_body_fragments(fragments: list[etree._Element | str]) -> Markup:
    return Markup(
        "".join(
            str(escape(fragment))
            if isinstance(fragment, str)
            else etree.tostring(
                fragment, pretty_print=False, encoding="unicode", with_tail=True
            )
            for fragment in fragments
        )
    )
