from odoo.tools.module_data import rename_model


def migrate(cr, version):
    rename_model(cr, "mixin.media.live", "mixin.speech.live")
