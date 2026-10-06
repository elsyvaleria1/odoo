"""The input dialog's fields: built from the step that waits, not declared.

Not a model. The run's dialog and a step's dialog both start from a form whose
`input_fields` group is empty, and fill it in from the context's waiting step.
"""

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
