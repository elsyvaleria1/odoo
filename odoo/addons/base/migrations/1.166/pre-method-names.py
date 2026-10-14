from odoo.tools.method_data import rename_stored_model_methods

SHARED_MODEL_METHOD_RENAMES = {
    "_add_missing_default_values": "_prepare_values_with_defaults",
    "_get_vals_a_draft_reads_otherwise": "_get_values_with_unreliable_precompute_drafts",
    "_has_lines_a_create_keeps": "_has_one2many_commands_before_replacement",
    "_restore_given_values": "_restore_precompute_given_values",
    "_create_update_xmlids": "_update_created_record_xmlids",
}


def migrate(cr, version):
    if version:
        rename_stored_model_methods(
            cr,
            model_method_renames={},
            shared_method_renames=SHARED_MODEL_METHOD_RENAMES,
        )
