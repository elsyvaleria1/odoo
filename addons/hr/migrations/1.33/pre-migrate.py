from odoo.tools import module_data


def migrate(cr, version):
    if not version:
        return
    module_data.rename_field(cr, "hr.employee", "country_id", "nationality_country_id")
