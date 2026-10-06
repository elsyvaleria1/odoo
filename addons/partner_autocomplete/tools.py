from lxml import etree


def set_partner_autocomplete_widgets(arch: etree._Element) -> None:
    for node in arch.xpath("//field[@name='name' or @name='vat']"):
        node.set("widget", "field_partner_autocomplete")
