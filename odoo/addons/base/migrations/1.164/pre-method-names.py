from odoo.tools.method_data import rename_stored_model_methods

SHARED_MODEL_METHOD_RENAMES = {
    "_access_company_anchor": "_get_company_anchor_path",
    "_anchors_before_write": "_get_anchor_values_before_write",
    "_check_anchor_moves": "_check_anchor_move_access",
    "_get_company_check_candidates": "_get_company_check_groups",
}


def migrate(cr, version):
    if version:
        rename_stored_model_methods(
            cr,
            model_method_renames={},
            shared_method_renames=SHARED_MODEL_METHOD_RENAMES,
        )
