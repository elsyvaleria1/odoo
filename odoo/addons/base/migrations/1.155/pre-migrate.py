from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    rename_module(cr, "stock_barcode_voice", "stock_barcode_voice_command")
    rename_module(cr, "stock_voice", "stock_voice_command")
    rename_module(cr, "mail_voice", "mail_voice_command")
    rename_module(cr, "voice_ai", "voice_command_ml")
    rename_module(cr, "voice", "voice_command")
