from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    # a module is named for what it extends (calendar, mail), not the vendor;
    # the vendor modules become integration_google / integration_microsoft
    # once they run on integration. The appointment bridges go first: their
    # names contain the calendars' and rename_module rewrites stored text.
    rename_module(cr, "appointment_google_calendar", "appointment_calendar_google")
    rename_module(
        cr, "appointment_microsoft_calendar", "appointment_calendar_microsoft"
    )
    rename_module(cr, "google_calendar", "calendar_google")
    rename_module(cr, "microsoft_calendar", "calendar_microsoft")
    rename_module(cr, "google_gmail", "mail_google")
    rename_module(cr, "microsoft_outlook", "mail_microsoft")
