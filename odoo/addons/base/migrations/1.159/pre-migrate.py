from odoo.tools.module_data import retire_empty_module


def migrate(cr, version):
    if not version:
        return
    retire_empty_module(cr, "ai_auto_install")
