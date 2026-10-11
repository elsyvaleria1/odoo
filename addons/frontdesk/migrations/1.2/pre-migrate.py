from odoo.tools import module_data


def migrate(cr, version):
    if not version:
        return
    module_data.rename_field(cr, "frontdesk.frontdesk", "is_favorite", "is_featured")
