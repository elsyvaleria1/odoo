from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    rename_module(cr, "sms_twilio", "integration_twilio")
