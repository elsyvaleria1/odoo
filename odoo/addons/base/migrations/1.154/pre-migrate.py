from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    rename_module(cr, "approval_ai_telegram", "approval_telegram_ml")
    rename_module(cr, "extract_ai", "extract_ml")
    rename_module(cr, "speech_ai", "speech_ml")
