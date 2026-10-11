from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    rename_module(cr, "google_address_autocomplete", "address_autocomplete_google")
