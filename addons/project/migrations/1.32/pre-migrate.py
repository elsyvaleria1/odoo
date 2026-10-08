from odoo.tools.module_data import rename_model


def migrate(cr, version):
    if not version:
        return
    rename_model(cr, "mixin.project.pm", "mixin.project.column")
