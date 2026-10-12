import codecs
import re
from collections.abc import Iterable
from typing import overload

from lxml import etree

__all__ = [
    "create_xml_node",
    "create_xml_node_chain",
    "remove_control_characters",
]


_C0_CONTROLS = r"\x00-\x08\x0b\x0c\x0e-\x1f"
_NOT_XML_CHARACTER_RE = re.compile(f"[{_C0_CONTROLS}\\ud800-\\udfff\\ufffe\\uffff]")
_NOT_XML_UTF8_RE = re.compile(
    f"[{_C0_CONTROLS}]".encode()
    + rb"|\xef\xbf[\xbe\xbf]"
    + rb"|\xed[\xa0-\xbf][\x80-\xbf]"
    + rb"|[\xf5-\xff]"
)
_BYTE_ORDER_MARKS = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
_UNMARKED_WIDE_STARTS = (
    (b"<\x00\x00\x00", "utf-32-le"),
    (b"\x00\x00\x00<", "utf-32-be"),
    (b"<\x00?\x00", "utf-16-le"),
    (b"\x00<\x00?", "utf-16-be"),
)
_DECLARED_ENCODING_RE = re.compile(
    rb"""\s*<\?xml\s[^>]*?\bencoding\s*=\s*["']([A-Za-z][\w.:-]*)["']"""
)
_BYTEWISE_CODECS = frozenset({"utf-8", "ascii"})


def _sniff_encoding(data: bytes) -> tuple[bytes, str | None]:
    for mark, codec in _BYTE_ORDER_MARKS:
        if data.startswith(mark):
            return mark, codec
    for start, codec in _UNMARKED_WIDE_STARTS:
        if data.startswith(start):
            return b"", codec
    match = _DECLARED_ENCODING_RE.match(data)
    if match is None:
        return b"", "utf-8"
    try:
        codec = codecs.lookup(match[1].decode("ascii")).name
    except LookupError:
        return b"", None
    if codec.startswith(("utf-16", "utf-32")):
        return b"", "utf-8"
    return b"", codec


@overload
def remove_control_characters(node: str) -> str: ...
@overload
def remove_control_characters(node: bytes) -> bytes: ...
def remove_control_characters(node: str | bytes) -> str | bytes:
    if isinstance(node, str):
        return _NOT_XML_CHARACTER_RE.sub("", node)
    mark, codec = _sniff_encoding(node)
    if codec is None:
        return node
    if codec in _BYTEWISE_CODECS:
        return _NOT_XML_UTF8_RE.sub(b"", node)
    text = node[len(mark) :].decode(codec, "ignore")
    return mark + _NOT_XML_CHARACTER_RE.sub("", text).encode(codec)


def create_xml_node_chain(
    first_parent_node: etree._Element,
    nodes_list: Iterable[str],
    last_node_value: str | None = None,
) -> list[etree._Element]:
    res = []
    current_node = first_parent_node
    for tag in nodes_list:
        current_node = etree.SubElement(current_node, tag)
        res.append(current_node)

    if last_node_value is not None:
        current_node.text = last_node_value
    return res


def create_xml_node(
    parent_node: etree._Element,
    node_name: str,
    node_value: str | None = None,
) -> etree._Element:
    return create_xml_node_chain(parent_node, [node_name], node_value)[0]
