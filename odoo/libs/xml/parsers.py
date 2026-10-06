from lxml import etree, objectify

__all__ = ["fromstring"]

_strict_parser = etree.XMLParser(resolve_entities=False)

etree.set_default_parser(_strict_parser)

_objectify_parser = etree.XMLParser(resolve_entities=False, remove_blank_text=True)
_objectify_parser.set_element_class_lookup(objectify.ObjectifyElementClassLookup())
objectify.set_default_parser(_objectify_parser)


def fromstring(text: str | bytes, base_url: str | None = None) -> etree._Element:
    return etree.fromstring(text, parser=_strict_parser, base_url=base_url)
