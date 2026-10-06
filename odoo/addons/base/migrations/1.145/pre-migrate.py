from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    # the vendor modules run on integration now, and are named for it
    rename_module(cr, "google_account", "integration_google")
    rename_module(cr, "microsoft_account", "integration_microsoft")
