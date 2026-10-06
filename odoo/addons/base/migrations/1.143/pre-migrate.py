from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    # Twilio is the company's carrier, not an SMS provider: its module keeps
    # the account every Twilio capability uses, SMS among them
    rename_module(cr, "sms_twilio", "integration_twilio")
