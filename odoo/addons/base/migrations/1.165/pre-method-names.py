from odoo.tools.method_data import rename_stored_model_methods

SHARED_MODEL_METHOD_RENAMES = {
    "_create_check_field_access": "_check_create_field_access_and_get_names",
    "_create_partition_values": "_partition_create_values_and_check_related_read_access",
    "_create_parent_records": "_create_or_update_parent_records",
    "_create_apply_inverses": "_apply_create_inverse_hooks",
    "_check_created": "_check_created_inverse_fields",
    "_convert_column_values": "_update_create_column_values",
    "_update_create_cache": "_update_create_cache_and_get_inverse_plan",
    "_write_check_field_access": "_check_write_field_access",
    "_write_classify_fields": "_get_write_field_plan",
    "_write_settle_protected": "_recompute_and_cache_write_fields",
    "_write_apply_inverses": "_apply_write_inverse_hooks",
}


def migrate(cr, version):
    if version:
        rename_stored_model_methods(
            cr,
            model_method_renames={},
            shared_method_renames=SHARED_MODEL_METHOD_RENAMES,
        )
