from lxml import etree

INPUT_CONTEXT_KEY = "automation_input_line_id"


def add_input_fields(arch, fields) -> None:
    group = arch.find(".//group[@name='input_fields']")
    for field in fields:
        node = etree.SubElement(group, "field", name=field.name, required="1")
        if field.ttype == "many2many":
            node.set("widget", "many2many_tags")
        if field.ttype in ("many2one", "many2many"):
            node.set("options", "{'no_create': True}")


def add_input_form(arch) -> None:
    group = arch.find(".//group[@name='input_fields']")
    etree.SubElement(group, "field", name="action_id", invisible="1")
    etree.SubElement(group, "field", name="input_values", nolabel="1", colspan="2")
