from odoo.tools.method_data import rename_stored_model_methods


def migrate(cr, version):
    if not version:
        return
    rename_stored_model_methods(
        cr,
        model_method_renames={
            ("ir.egress", "check_host"): "get_permitted_host_addresses",
            ("ir.egress", "check_url"): "get_permitted_url_destination",
        },
    )
