from odoo.tools.method_data import rename_stored_model_methods

SHARED_MODEL_METHOD_RENAMES = {
    "_verb_checkpoint": "_enforce_verb_checkpoint_and_get_ids",
    "_check_verb_transitions": "_enforce_verb_transitions_and_get_moves",
    "_check_verb_creations": "_enforce_verb_creations",
    "_land_verb_transitions": "_notify_verb_transitions_landed",
}


def migrate(cr, version):
    if version:
        rename_stored_model_methods(
            cr,
            model_method_renames={},
            shared_method_renames=SHARED_MODEL_METHOD_RENAMES,
        )
