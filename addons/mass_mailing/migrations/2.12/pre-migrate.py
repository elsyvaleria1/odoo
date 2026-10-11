from odoo.tools import module_data


def migrate(cr, version):
    if not version:
        return
    module_data.rename_field(cr, "mailing.mailing", "is_favorite", "is_template")
    module_data.rename_field(cr, "mailing.mailing", "date_favorite", "date_template")
