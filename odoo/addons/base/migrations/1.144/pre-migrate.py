from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    rename_module(cr, "appointment_google_calendar", "appointment_calendar_google")
    rename_module(
        cr, "appointment_microsoft_calendar", "appointment_calendar_microsoft"
    )
    rename_module(cr, "google_calendar", "calendar_google")
    rename_module(cr, "microsoft_calendar", "calendar_microsoft")
    rename_module(cr, "google_gmail", "mail_google")
    rename_module(cr, "microsoft_outlook", "mail_microsoft")
