from odoo.tools.module_data import fold_module


def migrate(cr, version):
    if not version:
        return
    # what the Outlook appointment bridge did, calendar_sync does for every
    # provider
    fold_module(cr, "appointment_calendar_microsoft", "calendar_sync")
