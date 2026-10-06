from odoo.tools import module_data


def migrate(cr, version):
    if not version:
        return
    # the first held nationality, not an address country: the row keeps its id,
    # so its tracking history follows the name
    module_data.rename_field(cr, "hr.employee", "country_id", "nationality_country_id")
