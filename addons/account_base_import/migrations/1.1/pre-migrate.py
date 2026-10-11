from odoo.tools.module_data import rename_model

RENAMED = (("account.import.summary", "wizard.account.import.summary"),)


def migrate(cr, version):
    if not version:
        return
    for old, new in RENAMED:
        rename_model(cr, old, new)
