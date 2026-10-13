import typing
from collections.abc import Iterable
from pathlib import Path
from typing import IO

from lxml import etree

from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.xml import (
    create_xml_node,
    create_xml_node_chain,
    dict_to_xml,
    remove_control_characters,
)
from odoo.tools.files import file_path

__all__ = [
    "XsdFileResolver",
    "check_with_xsd",
    "check_with_xsd_file",
    "cleanup_xml_node",
    "dict_to_xml",
    "get_xml_value",
    "prepare_xml_signature",
]

type XmlSource = etree._Element | str | bytes

_debug = DebugLog(__name__)


def check_with_xsd(
    tree_or_str: XmlSource,
    stream: str | IO[bytes],
    *,
    resolvers: Iterable[etree.Resolver] = (),
) -> None:
    if not isinstance(tree_or_str, etree._Element):
        tree_or_str = etree.fromstring(
            tree_or_str,
            parser=etree.XMLParser(resolve_entities=False, no_network=True),
        )
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    for resolver in resolvers:
        parser.resolvers.add(resolver)
    with _debug.perf(
        "xml_utils.xsd_compiled", schema=stream if isinstance(stream, str) else None
    ):
        xsd_schema = etree.XMLSchema(etree.parse(stream, parser=parser))
    try:
        with _debug.perf(
            "xml_utils.xsd_validated",
            schema=stream if isinstance(stream, str) else None,
            root=tree_or_str.tag,
        ):
            xsd_schema.assertValid(tree_or_str)
    except etree.DocumentInvalid as xml_errors:
        _debug.logic(
            "xml_utils.document_invalid",
            schema=stream if isinstance(stream, str) else None,
            root=tree_or_str.tag,
            errors=len(xml_errors.error_log),
        )
        raise UserError("\n".join(str(e) for e in xml_errors.error_log)) from xml_errors


class XsdFileResolver(etree.Resolver):
    def __init__(self, *paths: str) -> None:
        super().__init__()
        self._paths = {Path(path).name: path for path in paths}

    @typing.override
    def resolve(
        self, system_url: str, public_id: str | None, context: object
    ) -> object:
        path = self._paths.get(system_url.rsplit("/", 1)[-1])
        _debug.logic("xml_utils.xsd_import_resolved", url=system_url, path=path)
        if path is None:
            return None
        return self.resolve_filename(path, context)


def check_with_xsd_file(tree_or_str: XmlSource, schema: str, *imports: str) -> None:
    root = file_path(schema, filter_ext=(".xsd",))
    local = [str(path) for path in Path(root).parent.glob("*.xsd")]
    imported = [file_path(path, filter_ext=(".xsd",)) for path in imports]
    check_with_xsd(tree_or_str, root, resolvers=(XsdFileResolver(*local, *imported),))


def cleanup_xml_node(
    xml_node_or_string: etree._Element | str | bytes,
    remove_blank_text: bool = True,
    remove_blank_nodes: bool = True,
    indent_level: int = 0,
    indent_space: str = "  ",
) -> etree._Element:
    xml_node = xml_node_or_string

    if isinstance(xml_node, str):
        xml_node = xml_node.encode()
    if isinstance(xml_node, bytes):
        parser = etree.XMLParser(recover=True, resolve_entities=False)
        xml_node = etree.fromstring(remove_control_characters(xml_node), parser=parser)

    def leaf_iter(
        parent_node: etree._Element | None, node: etree._Element, level: int
    ) -> None:
        for child_node in node:
            leaf_iter(node, child_node, level if level < 0 else level + 1)

        if level >= 0:
            indent = "\n" + indent_space * level
            if not node.tail or not node.tail.strip():
                node.tail = "\n" if parent_node is None else indent
            if len(node) > 0:
                if not node.text or not node.text.strip():
                    node.text = indent + indent_space
                last_child = node[-1]
                if last_child.tail == indent + indent_space:
                    last_child.tail = indent

        if parent_node is not None and len(node) == 0:
            if remove_blank_text and node.text is not None and not node.text.strip():
                node.text = ""
            if remove_blank_nodes and not (node.text or ""):
                parent_node.remove(node)

    leaf_iter(None, xml_node, indent_level)
    return xml_node


def prepare_xml_signature(source: str | bytes) -> etree._Element:
    signature = cleanup_xml_node(source, remove_blank_nodes=False, indent_level=-1)
    etree.indent(signature, space="")
    signature_object = signature.find("{http://www.w3.org/2000/09/xmldsig#}Object")
    if signature_object is None:
        raise ValueError("The XML signature template must contain a direct ds:Object")
    for element in signature_object.iter():
        if element.text == "\n":
            element.text = ""
        element.tail = ""
    return signature


def get_xml_value(
    xpath: str,
    xml_element: etree._Element,
    namespaces: dict[str, str] | None = None,
) -> str | None:
    result = xml_element.xpath(xpath, namespaces=namespaces)
    if not result:
        return None
    first = result[0]
    return first if isinstance(first, str) else first.text
