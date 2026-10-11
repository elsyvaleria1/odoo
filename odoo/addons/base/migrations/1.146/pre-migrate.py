from odoo.tools.module_data import fold_module


def migrate(cr, version):
    if not version:
        return
    fold_module(cr, "appointment_calendar_microsoft", "calendar_sync")
