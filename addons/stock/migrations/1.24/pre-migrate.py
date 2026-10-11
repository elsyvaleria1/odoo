from odoo.tools import module_data


def migrate(cr, version):
    if not version:
        return
    module_data.rename_field(cr, "stock.quant", "is_favorite", "is_featured")
