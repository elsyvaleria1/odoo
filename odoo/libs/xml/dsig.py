import hashlib
from base64 import b64encode
from copy import deepcopy

from lxml import etree

from odoo.libs.debug_log import DebugLog

from .parsers import fromstring

__all__ = [
    "EXC_C14N_ALGORITHM",
    "XmlSigError",
    "canonicalize_signed_info",
    "update_reference_digests",
]


_DS_NS = "http://www.w3.org/2000/09/xmldsig#"
EXC_C14N_ALGORITHM = "http://www.w3.org/2001/10/xml-exc-c14n#"
_ENVELOPED_SIGNATURE_ALGORITHM = f"{_DS_NS}enveloped-signature"
_WSU_NS = (
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
)
# no DTD or schema declares which attribute is an ID, so the names every
# e-invoicing format in use spells it with are taken, as signxml does, and
# WS-Security's wsu:Id, which a SOAP header (DIAN's) is referenced by
_ID_XPATH = (
    "//*[@Id=$id or @ID=$id or @id=$id"
    " or @*[namespace-uri()='http://www.w3.org/XML/1998/namespace'"
    " and local-name()='id']=$id"
    f" or @*[namespace-uri()='{_WSU_NS}' and local-name()='Id']=$id]"
)

_DIGEST_ALGORITHMS = {
    f"{_DS_NS}sha1": "sha1",
    "http://www.w3.org/2001/04/xmldsig-more#sha224": "sha224",
    "http://www.w3.org/2001/04/xmlenc#sha256": "sha256",
    "http://www.w3.org/2001/04/xmldsig-more#sha384": "sha384",
    "http://www.w3.org/2001/04/xmlenc#sha512": "sha512",
}

_NSMAP = {"ds": _DS_NS}
_XML_NS = "{http://www.w3.org/XML/1998/namespace}"
_debug = DebugLog(__name__)


class XmlSigError(ValueError):
    pass


def _canonicalize(
    node: etree._Element | str,
    *,
    exclusive: bool = False,
    inclusive_ns_prefixes: list[str] | None = None,
) -> bytes:
    if isinstance(node, str):
        node = fromstring(node)
    elif not exclusive and (inherited := _inherited_xml_attributes(node)):
        node = _with_attributes(node, inherited)
    return etree.tostring(
        node,
        method="c14n",
        with_comments=False,
        exclusive=exclusive,
        inclusive_ns_prefixes=inclusive_ns_prefixes,
    )


def _inherited_xml_attributes(node: etree._Element) -> dict[str, str]:
    # inclusive C14N 1.0 carries the nearest xml:lang, xml:space, xml:base...
    # of the ancestors a subset leaves out onto its apex; lxml canonicalizes
    # the subtree as if it were a whole document and drops them
    inherited: dict[str, str] = {}
    for ancestor in node.iterancestors():
        for name, value in ancestor.attrib.items():
            if (
                name.startswith(_XML_NS)
                and name not in inherited
                and name not in node.attrib
            ):
                inherited[name] = value
    return inherited


def _with_attributes(
    node: etree._Element, attributes: dict[str, str]
) -> etree._Element:
    # the whole document is copied, as for stripping, to keep the namespaces
    # in scope that a copied subtree would drop
    copied = _follow(deepcopy(node.getroottree().getroot()), _child_indexes(node))
    copied.attrib.update(attributes)
    return copied


def _get_c14n_params_from_transforms(
    reference: etree._Element,
) -> tuple[bool, list[str]]:
    exclusive = next(
        (
            transform
            for transform in reference.findall(".//{*}Transform")
            if transform.get("Algorithm") == EXC_C14N_ALGORITHM
        ),
        None,
    )
    if exclusive is None:
        return False, []
    prefix_list = []
    inclusive_ns = exclusive.find(".//{*}InclusiveNamespaces")
    if inclusive_ns is not None and inclusive_ns.get("PrefixList"):
        prefix_list = inclusive_ns.get("PrefixList").split()
    return True, prefix_list


def _get_enveloping_signatures(
    reference: etree._Element, node: etree._Element
) -> list[etree._Element]:
    tag = f"{{{_DS_NS}}}Signature"
    own = next(reference.iterancestors(tag), None)
    if own is None:
        return list(node.iter(tag))
    if own is node or any(ancestor is node for ancestor in own.iterancestors()):
        return [own]
    return []


def _child_indexes(node: etree._Element) -> list[int]:
    indexes = []
    while (parent := node.getparent()) is not None:
        indexes.append(parent.index(node))
        node = parent
    return indexes[::-1]


def _follow(root: etree._Element, indexes: list[int]) -> etree._Element:
    for index in indexes:
        root = root[index]
    return root


def _strip_signatures(
    reference: etree._Element, node: etree._Element
) -> etree._Element:
    signatures = _get_enveloping_signatures(reference, node)
    if not signatures:
        return node
    # the whole document is copied, not the node: a copied subtree keeps
    # only the namespaces its names use, and inclusive c14n must still
    # declare those an attribute value such as xsi:type="cbc:Amount" needs
    copied_root = deepcopy(node.getroottree().getroot())
    copied_node = _follow(copied_root, _child_indexes(node))
    copies = [_follow(copied_root, _child_indexes(sig)) for sig in signatures]
    for signature in copies:
        if signature.tail:
            if (previous := signature.getprevious()) is not None:
                previous.tail = (previous.tail or "") + signature.tail
            else:
                parent = signature.getparent()
                parent.text = (parent.text or "") + signature.tail
        signature.getparent().remove(signature)
    return copied_node


def _find_by_id(root: etree._Element, uri: str) -> etree._Element:
    identifier = uri[1:]
    results = root.xpath(_ID_XPATH, id=identifier)
    _debug.logic("dsig.reference", kind="id", matches=len(results))
    if not results:
        raise XmlSigError(f"URI {uri!r} not found")
    if len(results) > 1:
        raise XmlSigError(
            f"Ambiguous reference URI {uri!r} resolved to {len(results)} nodes"
        )
    return results[0]


def _resolve_reference(uri: str, reference: etree._Element) -> bytes:
    exclusive, prefix_list = _get_c14n_params_from_transforms(reference)
    root = reference.getroottree().getroot()
    if not uri:
        node = root
    elif uri.startswith("#"):
        node = _find_by_id(root, uri)
    else:
        _debug.logic("dsig.reference", kind="unresolved")
        raise XmlSigError(f"URI {uri!r} not found")

    enveloped = not uri or any(
        transform.get("Algorithm") == _ENVELOPED_SIGNATURE_ALGORITHM
        for transform in reference.iterfind(".//{*}Transform")
    )
    _debug.logic(
        "dsig.reference",
        enveloped=enveloped,
        exclusive=exclusive,
        prefixes=len(prefix_list),
    )
    if enveloped:
        node = _strip_signatures(reference, node)
    return _canonicalize(node, exclusive=exclusive, inclusive_ns_prefixes=prefix_list)


def canonicalize_signed_info(signed_info: etree._Element) -> bytes:
    method = signed_info.find(".//{*}CanonicalizationMethod")
    exclusive = method is not None and method.get("Algorithm") == EXC_C14N_ALGORITHM
    prefix_list = []
    if exclusive:
        inclusive_ns = method.find(".//{*}InclusiveNamespaces")
        if inclusive_ns is not None and inclusive_ns.get("PrefixList"):
            prefix_list = inclusive_ns.get("PrefixList").split()
    return _canonicalize(
        signed_info, exclusive=exclusive, inclusive_ns_prefixes=prefix_list
    )


def _digest_algorithm(reference: etree._Element) -> str:
    method = reference.find("ds:DigestMethod", namespaces=_NSMAP)
    if method is None:
        raise XmlSigError(
            f"Reference {reference.get('URI', '')!r} has no <ds:DigestMethod>"
        )
    uri = method.get("Algorithm", "")
    if (algorithm := _DIGEST_ALGORITHMS.get(uri)) is None:
        raise XmlSigError(
            f"Reference {reference.get('URI', '')!r} names an unsupported "
            f"digest method {uri!r}"
        )
    return algorithm


def update_reference_digests(signed_info: etree._Element) -> None:
    for reference in signed_info.findall("ds:Reference", namespaces=_NSMAP):
        digest_value = reference.find("ds:DigestValue", namespaces=_NSMAP)
        if digest_value is None:
            raise XmlSigError(
                f"Reference {reference.get('URI', '')!r} has no <ds:DigestValue> "
                f"to fill in"
            )
        algorithm = _digest_algorithm(reference)
        with _debug.perf("dsig.digest", algorithm=algorithm) as span:
            octets = _resolve_reference(reference.get("URI", ""), reference)
            span.set(octets=len(octets))
            digest = hashlib.new(algorithm, octets).digest()
        digest_value.text = b64encode(digest).decode("ascii")
