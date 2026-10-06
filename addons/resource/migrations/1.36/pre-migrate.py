from odoo.tools import module_data


def migrate(cr, version):
    if not version:
        return
    module_data.rename_field(
        cr, "resource.resource", "resource_type", "type", values={"user": "human"}
    )
