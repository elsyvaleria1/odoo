from odoo.tools.module_data import drop_views


def migrate(cr, version):
    if not version:
        return
    drop_views(
        cr,
        "website_sale_autocomplete",
        ["res_config_settings_view_form_inherit_autocomplete_googleplaces"],
    )
