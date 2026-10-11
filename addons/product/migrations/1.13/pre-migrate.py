from odoo.tools import module_data


def migrate(cr, version):
    if not version:
        return
    for model in ("product.template", "product.product"):
        module_data.rename_field(cr, model, "is_favorite", "is_featured")
